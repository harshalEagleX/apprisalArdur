"""TogetherPool token accounting + the retry classification for local backpressure.

2026-07-18 investigation: 17% of item-judgements were coming back REVIEW
`llm_unavailable`, which the run log reported as "provider trouble". Instrumenting
a cold ESNC-0006152 run showed ZERO provider errors — no 429, no 5xx, no timeout,
no truncation. Every loss was `pool_exhausted`: acquire() reserved the full
max_tokens ceiling (~10,831 est. tokens/call), never refunded the unspent part,
and a 120k/min budget therefore behaved like ~11 calls/min against ~28 batches.
Batches that merely queued were reported as dead calls.

These tests pin the two behaviours that fix it.
"""

from app.llm.client import _is_retryable
from app.llm.together_pool import TogetherPool


def _pool(keys=("k1",), tpm=10_000, inflight=2):
    return TogetherPool(list(keys), tpm_budget_per_key=tpm, max_inflight_per_key=inflight)


def test_unused_reservation_is_refunded_on_release():
    """The core fix: hold the full ceiling while the call is in flight (that is
    what the provider counts), then refund what it did not actually cost."""
    p = _pool(tpm=10_000)
    key = p.acquire(8_000, timeout=1.0)
    assert key is not None
    # the whole ceiling is debited up front — a second big call must not fit
    assert p.acquire(8_000, timeout=0.1) is None
    p.release(key, reserved=8_000, actual=1_000)
    # 7,000 refunded → the same call now fits without waiting for a refill
    assert p.acquire(8_000, timeout=0.1) is not None


def test_release_without_usage_keeps_the_conservative_debit():
    """A transport error carries no usage block; the debit must stand rather than
    refund tokens the provider may well have charged for."""
    p = _pool(tpm=10_000)
    key = p.acquire(8_000, timeout=1.0)
    p.release(key)
    assert p.acquire(8_000, timeout=0.1) is None


def test_refund_never_exceeds_the_budget_ceiling():
    p = _pool(tpm=10_000)
    key = p.acquire(1_000, timeout=1.0)
    p.release(key, reserved=1_000, actual=0)
    st = p._states[0]
    assert st.available <= st.tpm_budget


def test_actual_above_reserved_refunds_nothing():
    """An under-estimate must not turn into a negative refund (a silent credit)."""
    p = _pool(tpm=10_000)
    key = p.acquire(5_000, timeout=1.0)
    before = p._states[0].available
    p.release(key, reserved=5_000, actual=9_000)
    assert p._states[0].available <= before + 1e-6


def test_capacity_reflects_real_concurrency():
    """judge_v2 sizes its worker pool from this — 10 lanes against 4 real slots
    left 6 threads that could only sit in acquire() and expire."""
    assert _pool(keys=("k1", "k2"), inflight=2).capacity == 4


def test_pool_exhausted_is_retryable():
    """It means OUR bucket had no budget — the request was never sent. That is
    exactly the condition a retry is for, and treating it as a dead call is what
    manufactured the `llm_unavailable` cards."""
    assert _is_retryable("pool_exhausted")


def test_provider_error_classification_is_unchanged():
    assert _is_retryable("http_429")
    assert _is_retryable("http_503")
    assert _is_retryable("transport:connection reset")
    # a timeout is handled by shrinking the batch (judge_v2._split_for_retry),
    # not by repeating the same slow call here
    assert not _is_retryable("timeout:read operation timed out")
    assert not _is_retryable("truncated_length")


# ── judge_v2 retry sizing ────────────────────────────────────────────────────

def test_failed_batches_are_halved_before_retry():
    """Once local starvation was fixed, the residual losses were read timeouts on
    the LARGEST batches. Resending an identical oversized call mostly bought a
    second timeout, so the retry halves it instead."""
    from app.language.judge_v2 import _split_for_retry
    packets = list(range(8))
    out = _split_for_retry([("subject#0", packets)])
    assert [len(ps) for _sec, ps in out] == [4, 4]
    assert [p for _sec, ps in out for p in ps] == packets      # nothing dropped


def test_single_item_chunks_pass_through_untouched():
    from app.language.judge_v2 import _split_for_retry
    assert _split_for_retry([("subject#0", ["only"])]) == [("subject#0", ["only"])]


def test_lanes_are_bounded_by_pool_capacity():
    from app.language.judge_v2 import _lanes_for

    class _C:
        _pool = TogetherPool(["k1", "k2"], tpm_budget_per_key=1, max_inflight_per_key=2)

    # 4 real slots → a small ready-queue on top, never the old flat 10
    assert _lanes_for(_C(), n_batches=25) <= 8
    assert _lanes_for(_C(), n_batches=2) == 2      # never more lanes than batches


def test_over_budget_request_is_clamped_not_unsatisfiable():
    """`available` can never exceed `tpm_budget`, so an estimate larger than the
    whole budget would spin until timeout and fail every time — turning a too-small
    TOGETHER_TPM_BUDGET_PER_KEY into a total judge outage rather than a slowdown."""
    p = _pool(tpm=5_000)
    assert p.acquire(50_000, timeout=0.2) is not None
