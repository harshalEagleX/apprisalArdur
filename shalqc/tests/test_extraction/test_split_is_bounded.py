"""Splitting must recover fields WITHOUT becoming the run's wall clock.

Run 19 is the counter-example this file exists to prevent returning. The split
path worked — it recovered `market` and `contract_history`, the two sections run
18 lost entirely — and it cost **1,566s of a 1,667s run** in one logical call,
while nine grid calls behind it died of read timeouts waiting for the keys it
held. Output tokens FELL 15% while wall clock rose 2.8x, which is the proof that
the run was not token-bound at all: ~90% of it was stall.

Four independent defects compounded, each pinned below:

  1. **No deadline.** The recursion was unbounded in time. A section that kept
     timing out spawned 1+2+4+8 attempts and every one was allowed the full read
     timeout.
  2. **Sequential halves.** The two halves are independent — they transcribe
     different fields from the same images — but ran one after the other, so the
     section's wall clock was the SUM of the split tree instead of its depth.
  3. **Full ceiling on every half.** Halving the field set while keeping
     `max_tokens` leaves each half just as able to run the clock out as the whole
     was, so the split converged on fields but never on time.
  4. **Unbounded depth.** Each level doubles the calls AND re-uploads the page
     images to all of them — measured at ~3,000 extra input tokens per split,
     14 splits, +73% input for -15% output.

Run 20, with all four fixed: 327.2s, slowest call 299.7s, splits 14 -> 4, input
tokens 103,915 -> 82,669 while reading MORE fields.
"""
from __future__ import annotations

import time

from app.extraction.vision import resilient as R
from app.extraction.vision.provider import VisionResponse


class _AlwaysTruncates:
    """Forces the maximum amount of splitting, and records what it was asked."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.calls = 0
        self.ceilings: list[int] = []
        self.start_offsets: list[float] = []
        self._t0 = time.monotonic()

    def transcribe(self, images, instruction, schema, *, max_tokens=4000,
                   effort="low", tier=None, budget_s=None):
        self.calls += 1
        self.ceilings.append(max_tokens)
        self.start_offsets.append(time.monotonic() - self._t0)
        time.sleep(self.delay)
        return VisionResponse(data={}, truncated=True, error="timed out")


def _fields(n: int) -> dict:
    return {f"f{i}": {} for i in range(n)}


def test_split_depth_is_bounded():
    """16 fields at depth<=2 is 1+2+4 = 7 calls. Unbounded it is 15, and every
    one of them re-uploads the page images."""
    p = _AlwaysTruncates()
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec")
    assert p.calls == 7, f"expected 7 calls at depth<=2, got {p.calls}"


def test_each_split_level_halves_the_ceiling():
    """The ceiling is what the read timeout is racing. A half-sized ask that
    keeps the full ceiling has not become any likelier to finish in time."""
    p = _AlwaysTruncates()
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec")
    # 6000 -> 3000 -> floored at _MIN_CEILING rather than 1500, because a half
    # under the reasoning floor returns empty rather than short.
    assert sorted(set(p.ceilings), reverse=True) == [6000, 3000, R._MIN_CEILING]


def test_a_halved_ceiling_never_falls_below_the_reasoning_floor():
    """A split must shrink the ask, not strangle it.

    Run 24 set the section ceiling to 3,000 chasing a latency target. `site` and
    `contract_history` truncated, split, and their halves inherited 1,500 — under
    the measured `out = 515 + 159 x N` floor — so both returned ZERO fields having
    spent four calls each. A ceiling below the floor does not shorten the answer,
    it empties it.
    """
    p = _AlwaysTruncates()
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec")
    # The caller's own ask is honoured; only the HALVES are floored.
    assert p.ceilings[0] == 6000
    assert min(p.ceilings) >= R._MIN_CEILING


def test_sibling_halves_run_concurrently():
    """Independent work must overlap. Serialised, the section's wall clock is the
    SUM of the split tree; in run 19 that made one section 94% of the run."""
    p = _AlwaysTruncates(delay=0.30)
    t0 = time.monotonic()
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec")
    elapsed = time.monotonic() - t0

    # 7 calls x 0.30s serial = 2.1s. Three levels overlapped is ~0.9s.
    assert elapsed < 1.5, f"splits appear serialised: {elapsed:.2f}s for 7 calls"

    # Siblings at the same level start together, not one after the other.
    level2 = sorted(p.start_offsets)[1:3]
    assert abs(level2[0] - level2[1]) < 0.15, f"level-2 siblings staggered: {level2}"


def test_deadline_bounds_the_whole_split_tree():
    """The budget covers every call beneath the section, not each call in it."""
    p = _AlwaysTruncates(delay=0.30)
    t0 = time.monotonic()
    res = R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                                max_tokens=6000, label="sec",
                                deadline=time.monotonic() + 0.35)
    elapsed = time.monotonic() - t0

    assert elapsed < 1.2, f"deadline not enforced: {elapsed:.2f}s"
    assert res.missing_fields, "abandoned fields must be reported, never silent"


def test_a_split_is_not_started_when_its_halves_cannot_finish(monkeypatch):
    """Run 24's regression. With the deadline close, the halves inherited a few
    seconds, gave up before posting ("call budget 4s spent"), and the section
    returned NOTHING having spent four calls. Keeping the partial read is
    strictly better."""
    monkeypatch.setattr(R, "_MIN_VIABLE_CALL_S", 45.0)
    p = _AlwaysTruncates(delay=0.01)
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec",
                          deadline=time.monotonic() + 5.0)
    assert p.calls == 1, f"split into unviable halves: {p.calls} calls"


def test_a_split_IS_started_when_there_is_time(monkeypatch):
    monkeypatch.setattr(R, "_MIN_VIABLE_CALL_S", 0.01)
    p = _AlwaysTruncates(delay=0.01)
    R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                          max_tokens=6000, label="sec",
                          deadline=time.monotonic() + 30.0)
    assert p.calls == 7


def test_deadline_is_checked_before_spending_not_after():
    """A half that starts one second before the deadline still runs a full read
    timeout, so the check has to gate entry rather than report afterwards."""
    p = _AlwaysTruncates(delay=0.05)
    res = R.transcribe_complete(p, [], "x", _fields(16), lambda f: {},
                                max_tokens=6000, label="sec",
                                deadline=time.monotonic() - 1.0)
    assert p.calls == 0, "spent a call despite an already-expired deadline"
    assert res.timed_out is True
    assert len(res.missing_fields) == 16


def test_a_healthy_call_never_splits_or_pays_the_deadline():
    """The escalation must cost nothing when the model answers first time."""

    class _Ok:
        calls = 0

        def transcribe(self, images, instruction, schema, *, max_tokens=4000,
                       effort="low", tier=None):
            type(self).calls += 1
            return VisionResponse(data={"f0": {"value": "x"}})

    p = _Ok()
    res = R.transcribe_complete(p, [], "x", _fields(8), lambda f: {},
                                max_tokens=6000, label="sec")
    assert p.calls == 1
    assert res.splits == 0
    assert res.timed_out is False


def test_partial_results_survive_a_deadline():
    """Whatever landed before the deadline must be kept — a bounded section
    returns what it read, it does not discard it."""

    class _FirstHalfWorks:
        def __init__(self):
            self.calls = 0

        def transcribe(self, images, instruction, schema, *, max_tokens=4000,
                       effort="low", tier=None):
            self.calls += 1
            if self.calls == 1:
                return VisionResponse(data={}, truncated=True, error="timed out")
            if self.calls == 2:
                return VisionResponse(data={"f0": {"value": "kept"}})
            time.sleep(0.4)
            return VisionResponse(data={}, truncated=True, error="timed out")

    p = _FirstHalfWorks()
    res = R.transcribe_complete(p, [], "x", _fields(8), lambda f: {},
                                max_tokens=6000, label="sec",
                                deadline=time.monotonic() + 60.0)
    assert res.data.get("f0") == {"value": "kept"}
