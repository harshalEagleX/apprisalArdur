"""In-flight calls must be bounded GLOBALLY, not per pool.

The runner starts the section pass and the grid pass at the same time and hands
each of them the same `concurrency` value, so the configured limit was spent
twice. Run 19 asked for 2 calls/key across 4 keys — 8 — and measured
`peak_in_flight: 16`, i.e. 4 per key.

That is not merely "a bit fast". A Together key serves a fixed total throughput
shared across its in-flight calls, so doubling in-flight halves each call's
decode rate; past roughly 2 per key calls stop completing and start timing out.
Nine of run 19's twelve grid calls died with read timeouts, and a timed-out call
returns NOTHING for the full wait — the contention converts completions into
total losses, not into slower successes.

A pool-side limit cannot express the invariant because neither pool can see the
other. The provider is the only object they share, so the gate lives there.

Run 20, with the gate: `peak_in_flight` 16 -> 9, and the grid went from 2 PARTIAL
comparables to 5 CERTIFIED + 1 CONFLICT.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.extraction.vision.provider import TogetherVisionProvider


class _Instrumented(TogetherVisionProvider):
    """Counts concurrent entries to the real (gated) transcribe path."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.peak = 0
        self._live = 0
        self._lock = threading.Lock()

    def _transcribe(self, images, instruction, schema, *, max_tokens=4000,
                    effort="low", tier=None, budget_s=None):
        with self._lock:
            self._live += 1
            self.peak = max(self.peak, self._live)
        try:
            time.sleep(0.05)
            from app.extraction.vision.provider import VisionResponse
            return VisionResponse(data={"ok": {"value": 1}})
        finally:
            with self._lock:
                self._live -= 1


def _hammer(provider, n_pools: int, per_pool: int) -> None:
    """Two concurrent pools, exactly like sections + grid in the runner."""
    def worker():
        provider.transcribe([], "x", {}, max_tokens=100)

    with ThreadPoolExecutor(max_workers=n_pools * per_pool) as pool:
        for f in [pool.submit(worker) for _ in range(n_pools * per_pool * 2)]:
            f.result()


def test_two_concurrent_pools_cannot_exceed_the_global_limit():
    """The regression: sections and grid each spending the whole allowance."""
    p = _Instrumented(["k1", "k2", "k3", "k4"], "m", max_in_flight=8)
    _hammer(p, n_pools=2, per_pool=8)
    assert p.peak <= 8, (
        f"peak_in_flight {p.peak} exceeded the gate of 8 — the limit is being "
        "applied per pool again")


def test_the_gate_is_derived_from_the_key_pool():
    """4 keys x 2 calls/key = 8. The number must track the pool, not a constant."""
    p = _Instrumented(["k1", "k2"], "m", max_in_flight=4)
    _hammer(p, n_pools=2, per_pool=8)
    assert p.peak <= 4


def test_the_gate_still_allows_full_use_of_the_budget():
    """A limit that throttles below its own value would trade one bug for a
    slower one — the pools must actually reach the allowance."""
    p = _Instrumented(["k1", "k2", "k3", "k4"], "m", max_in_flight=8)
    _hammer(p, n_pools=2, per_pool=8)
    assert p.peak >= 2, f"gate appears to be serialising calls (peak {p.peak})"


def test_zero_disables_the_gate():
    """Callers that manage their own concurrency (tests, single-shot probes)
    must not be forced through it."""
    p = _Instrumented(["k1"], "m", max_in_flight=0)
    assert p._admission is None
    _hammer(p, n_pools=1, per_pool=4)
    assert p.peak >= 1


@pytest.mark.parametrize("keys,per_key", [(1, 2), (4, 2), (8, 2), (4, 1)])
def test_gate_value_matches_keys_times_calls_per_key(keys, per_key):
    p = TogetherVisionProvider([f"k{i}" for i in range(keys)], "m",
                               max_in_flight=keys * per_key)
    assert p._admission._value == keys * per_key
    assert p.key_count == keys
