"""
llm.together_pool (pool-1.0.0) — per-key token-bucket + in-flight governor for
the (single-provider, Together-only) LLM subsystem.

2026-07-13: replaces the Together→Groq failover chain. The chain reacted to a
429/413 AFTER sending a request the provider's tier couldn't take; this stops
the request from being SENT in the first place when a key doesn't have the
budget, by tracking each key's remaining tokens-per-minute allowance and
in-flight request count locally. Picking the key with the most headroom (not
strict round-robin) means a burst of calls spreads itself across keys instead
of queueing behind whichever key happens to be next.

Not a distributed rate limiter — state is per-process (per-worker), which
matches the deployment model (each worker owns whole orders end-to-end, all
sharing the process-local pool instance).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

__version__ = "pool-1.0.0"

_CHARS_PER_TOKEN = 4.0  # rough estimate — good enough for a budget reservation,
                        # not an exact tokenizer match.


def estimate_tokens(system: str, user: str, max_tokens: int) -> float:
    """Estimate the token cost of one call: prompt tokens (rough chars/4) plus
    the FULL requested output budget (max_tokens) — reserved up front, since
    the provider counts the requested ceiling against tokens-per-minute
    quotas even before generation finishes."""
    prompt_chars = len(system) + len(user)
    return prompt_chars / _CHARS_PER_TOKEN + max_tokens


@dataclass
class _KeyState:
    key: str
    tpm_budget: float
    available: float
    last_refill: float
    max_inflight: int
    inflight: int = 0

    def refill_locked(self) -> None:
        """Caller must hold the pool lock. Leaky-bucket refill proportional to
        elapsed wall time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        if elapsed > 0:
            self.available = min(self.tpm_budget, self.available + elapsed / 60.0 * self.tpm_budget)


class TogetherPool:
    """Pick a Together API key with enough token budget AND a free in-flight
    slot; debit the estimate before sending, credit the in-flight slot back
    on release. `acquire()` blocks briefly (polling) if every key is
    momentarily saturated — a real burst drains in well under a second once
    any key's bucket refills, rather than failing the call outright."""

    def __init__(self, keys: List[str], tpm_budget_per_key: float, max_inflight_per_key: int) -> None:
        self._lock = threading.Lock()
        now = time.monotonic()
        self._states = [
            _KeyState(key=k, tpm_budget=tpm_budget_per_key, available=tpm_budget_per_key,
                      last_refill=now, max_inflight=max_inflight_per_key)
            for k in keys
        ]

    @property
    def num_keys(self) -> int:
        return len(self._states)

    def acquire(self, estimated_tokens: float, timeout: float = 20.0) -> Optional[str]:
        """Return a key with capacity for `estimated_tokens`, or None if no key
        freed up within `timeout` seconds (the pool is genuinely saturated —
        the caller should treat this like any other call failure, not retry
        indefinitely).

        A request larger than a key's ENTIRE budget is clamped to that budget
        rather than being made unsatisfiable: `available` can never exceed
        `tpm_budget`, so an unclamped over-budget estimate would spin until the
        timeout and fail 100% of the time — turning a misconfigured (too small)
        TOGETHER_TPM_BUDGET_PER_KEY into a total judge outage instead of a
        slowdown. Sending it and letting the provider's own 429 govern is the
        strictly better failure mode.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                candidates = sorted(self._states, key=lambda s: -s.available)
                for st in candidates:
                    st.refill_locked()
                    want = min(estimated_tokens, st.tpm_budget)
                    if st.available >= want and st.inflight < st.max_inflight:
                        st.available -= want
                        st.inflight += 1
                        return st.key
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def release(self, key: str, reserved: Optional[float] = None,
                actual: Optional[float] = None) -> None:
        """Free the in-flight slot and REFUND the over-reservation.

        2026-07-18 (unjudged-loss investigation): the debit used to be
        permanent, decaying back only via the per-minute refill. That looked
        "safe" but was the direct cause of the 17% unjudged rate. `acquire()`
        reserves the FULL requested `max_tokens` (correct while the call is in
        flight — the provider counts the ceiling against TPM), but a judge batch
        asks for a 2500-token reasoning headroom + ~600/item and then actually
        spends ~1000 completion tokens. Measured on a cold ESNC-0006152 run:
        10,831 tokens reserved per call against a real cost near 4,500 — so a
        120k/min budget behaved like ~11 calls/min while the batches needed ~28.
        Six batches then timed out in `acquire()` and were reported as provider
        failures they never were (zero 429s, zero 5xx, zero timeouts on that run).

        Holding the full reservation for the DURATION of the call keeps the
        429-safety; refunding the unused part the moment the real `usage` is
        known is what stops the bucket from throttling on tokens nobody spent.
        Called with no figures (or an unknown `actual`) it degrades to the old
        behaviour — free the slot, keep the debit.
        """
        with self._lock:
            for st in self._states:
                if st.key == key:
                    st.inflight = max(0, st.inflight - 1)
                    if reserved is not None and actual is not None:
                        refund = max(0.0, float(reserved) - float(actual))
                        if refund:
                            st.refill_locked()
                            st.available = min(st.tpm_budget, st.available + refund)
                    return

    @property
    def capacity(self) -> int:
        """Total concurrent in-flight slots across every key. Callers size their
        worker pool from this: threads beyond it cannot make a call, they can
        only sit in `acquire()` and expire (see judge_v2._lanes_for)."""
        return sum(st.max_inflight for st in self._states) or 1
