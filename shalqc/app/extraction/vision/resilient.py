"""
extraction.vision.resilient (rsl-1.0.0) — a call that cannot lose a field.

**Truncation is the only failure mode here that destroys data silently.** A 5xx
is retried, a refusal is recorded, a bad JSON parse is visible. But a reasoning
model that exhausts `max_tokens` mid-deliberation returns an EMPTY body with a
200 status: full latency paid, full tokens billed, every field in that call
gone, and nothing in the response says so. Measured on real runs, that single
mode cost whole sections and comparables repeatedly (23 -> 81 -> 160 fields as
the ceiling rose, with nothing else changed).

So this module makes completion structural rather than hoped for:

    1. Ask for the whole field set.
    2. Truncated? Retry once with a larger ceiling — usually the request was
       merely under-budgeted.
    3. Still truncated? SPLIT the field set in half and recurse on each half.
       Half the fields need roughly half the reasoning, so the split converges;
       and because the halves are unioned afterwards, **no field is dropped to
       make the call fit.**
    4. Merge.

The escalation costs nothing on a healthy call — it only fires when the model
actually ran out of room. That is the point: pay for resilience where it is
needed, not everywhere.

Splitting is safe for extraction in a way it would NOT be for judgment: each
field is transcribed from the same image independently, so asking for a subset
changes nothing about what any one field's answer should be. (Contrast the comp
grid, where a PARTIAL read manufactures findings — hence verify.verify_comp_set
gating on completeness.)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.extraction.vision.provider import VisionProvider, VisionResponse
from app.extraction.vision.render import RenderedPage

__version__ = "rsl-1.0.0"

logger = logging.getLogger(__name__)

# Stop splitting here. Below a handful of fields the reasoning tax dominates and
# further splitting adds calls without shrinking the per-call output.
_MIN_SPLIT = 3
# How many times one section may halve. Each level doubles the calls AND
# re-uploads the page images to every one of them: run 19 paid ~3,000 extra
# input tokens per split, 14 splits, +73% input for -15% output. Past two levels
# the field set is small enough that a call still failing is not too big — it is
# unreadable, and re-splitting only buys more prefill. Beyond this the region is
# reported UNREAD, which is a fact a reviewer can act on.
_MAX_SPLIT_DEPTH = 2
# Absolute ceiling for one call. Output generates SERIALLY, so a ceiling is also
# a duration: at the rate a contended call actually achieves, 12k tokens is
# minutes of wall clock and cannot finish inside any sane read timeout. Nothing
# raises a ceiling any more — see the split note below — so this is a cap on what
# a CALLER may ask for, not a level anything escalates to.
_HARD_MAX_TOKENS = 6_500
# Floor for a halved ceiling, sized from the MEASURED output need rather than
# guessed: fitting run 14's clean section calls gives `out = 515 + 159 x N`, so
# even a 3-field half needs ~1,000 tokens and a 12-field one needs ~2,400.
#
# 700 was far too low and the failure is silent. Run 24 set the section ceiling
# to 3,000 to chase a latency target; `site` and `contract_history` truncated,
# split, and their halves inherited 1,500 — below the reasoning floor — so both
# returned ZERO fields having spent four calls. A ceiling under the floor does
# not produce a shorter answer, it produces an empty one.
_MIN_CEILING = 2_500
# Wall-clock budget for ONE logical section, covering every split beneath it.
#
# Run 19 is why this exists. `market` split three times and ran **1,566s of a
# 1,667s run** — 94% of the wall clock in one logical call, while nine grid calls
# behind it died of read timeouts waiting for the keys it was holding. Splitting
# is recursive and SEQUENTIAL, so a section that keeps timing out spawns 1+2+4+8
# serial attempts and each one is allowed to run the full read timeout. Nothing
# bounded the total.
#
# A section that cannot be read in this long will not become readable with more
# time; it will only go on starving every other call in the pool. Returning what
# landed, plus an honest list of what did not, is strictly better than holding
# the whole order hostage.
_SECTION_DEADLINE_S = 240.0
# Least time in which a split half can plausibly complete: the request overhead
# plus enough decode to clear the reasoning floor. Below this a split produces
# two calls that abandon before posting, so the section spends four calls to
# return nothing.
_MIN_VIABLE_CALL_S = 45.0


class CompletionResult:
    """Merged data plus an honest account of what it took to get it."""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.calls: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.splits: int = 0
        self.timed_out: bool = False
        self.retries: int = 0
        self.started_at: float = 0.0
        self.ended_at: float = 0.0
        self.errors: List[str] = []
        self.missing_fields: List[str] = []

    @property
    def ok(self) -> bool:
        return bool(self.data) and not self.missing_fields

    def absorb(self, resp: VisionResponse) -> None:
        self.calls += 1
        self.input_tokens += resp.input_tokens or 0
        self.output_tokens += resp.output_tokens or 0
        if resp.started_at and (not self.started_at or resp.started_at < self.started_at):
            self.started_at = resp.started_at
        if resp.ended_at > self.ended_at:
            self.ended_at = resp.ended_at

    def absorb_child(self, child: "CompletionResult") -> None:
        """Fold a concurrently-run split half back into the parent."""
        _merge(self.data, child.data)
        self.calls += child.calls
        self.input_tokens += child.input_tokens
        self.output_tokens += child.output_tokens
        self.splits += child.splits
        self.retries += child.retries
        self.timed_out = self.timed_out or child.timed_out
        self.errors.extend(child.errors)
        self.missing_fields.extend(
            n for n in child.missing_fields if n not in self.data)
        if child.started_at and (not self.started_at
                                 or child.started_at < self.started_at):
            self.started_at = child.started_at
        if child.ended_at > self.ended_at:
            self.ended_at = child.ended_at

    def summary(self) -> Dict[str, Any]:
        return {"calls": self.calls, "splits": self.splits, "retries": self.retries,
                "timed_out": self.timed_out,
                "fields": len(self.data), "missing": self.missing_fields,
                "errors": self.errors[:4]}


def transcribe_complete(
    provider: VisionProvider,
    images: List[RenderedPage],
    instruction: str,
    fields: Dict[str, Any],
    schema_for: Callable[[Dict[str, Any]], Dict[str, Any]],
    *,
    max_tokens: int,
    effort: str = "low",
    label: str = "call",
    depth: int = 0,
    result: Optional[CompletionResult] = None,
    deadline: Optional[float] = None,
) -> CompletionResult:
    """Transcribe `fields` from `images`, splitting rather than losing anything.

    `schema_for` builds the JSON schema for a subset of `fields`, so the split
    halves are structurally identical to the whole — the model never sees a
    different contract, only a shorter one.

    `deadline` is an absolute `time.monotonic()` value bounding the WHOLE tree of
    splits, not each call in it. Without it the recursion is unbounded in time —
    see `_SECTION_DEADLINE_S`.
    """
    result = result or CompletionResult()
    if not fields:
        return result

    if deadline is None:
        deadline = time.monotonic() + _SECTION_DEADLINE_S

    # Check BEFORE spending, not after. A split half that starts one second
    # before the deadline still runs a full read timeout.
    if time.monotonic() >= deadline:
        result.timed_out = True
        result.missing_fields.extend(n for n in fields if n not in result.data)
        logger.warning("vision(%s): section deadline reached — %d field(s) "
                       "abandoned so the rest of the order can proceed",
                       label, len(fields))
        return result

    ceiling = int(min(max_tokens, _HARD_MAX_TOKENS))
    # Hand the section's REMAINING time down, so the call cannot outlive the
    # deadline that admitted it. The provider carries its own 300s budget, and
    # without this the two never meet: run 22 admitted a call just inside a 240s
    # section deadline, the call then spent the provider's full allowance, and
    # the section finished at 301.2s inside its own 240s bound.
    # Clamped: a call admitted just inside the deadline computes a tiny or
    # NEGATIVE remaining, and a negative budget makes the provider give up
    # before posting while still counting as an attempt. Run 27 logged
    # "-32s left", "-42s left", "-73s left" — the ladder was being entered
    # after its own deadline had passed.
    remaining = max(0.0, deadline - time.monotonic())
    try:
        resp = provider.transcribe(images, instruction, schema_for(fields),
                                   max_tokens=ceiling, effort=effort,
                                   budget_s=remaining)
    except TypeError:
        # A provider that predates the budget parameter (or a test double).
        resp = provider.transcribe(images, instruction, schema_for(fields),
                                   max_tokens=ceiling, effort=effort)
    result.absorb(resp)

    if resp.ok and resp.data:
        _merge(result.data, resp.data)
        return result

    err = str(resp.error or "").lower()
    truncated = (resp.truncated or "truncat" in err or "max_tokens" in err
                 # A read timeout on a generating call is the SAME problem as a
                 # truncation — the answer was too long to finish — and needs the
                 # same response. Treating it as a transport fault is why the
                 # `market` section returned zero fields with splits=0.
                 or "timed out" in err or "timeout" in err)

    # ── SPLIT. Never raise the ceiling. ───────────────────────────────────────
    #
    # Raising max_tokens on truncation is backwards, and run 18 shows the doom
    # loop it creates: a bigger ceiling needs MORE seconds to generate, and the
    # read timeout is fixed, so each retry is likelier to time out than the
    # attempt before it. The old escalation doubled 2,400→4,800, 4,600→9,200,
    # 6,500→12,000 and made failure certain. `market` and `contract_history` —
    # the two longest-narrative sections, therefore the highest ceilings — died
    # first and took 41 fields with them, including the contract analysis
    # sentence that carries the single biggest finding on the order.
    #
    # Halving the ask instead halves the tokens to generate AND the time to
    # generate them, so it converges on the one thing a fixed timeout can
    # accommodate. There is no case where a call that could not finish in the
    # time available is helped by being asked for more.
    # A split is only worth starting if its halves can actually finish. Once the
    # section deadline is close, the halves inherit a few seconds, give up before
    # posting ("call budget 4s spent"), and the section returns NOTHING having
    # spent four calls — which is strictly worse than keeping the partial read.
    # Run 24 lost `site` (18 fields) and `contract_history` (22) exactly this way.
    time_to_split = (deadline - time.monotonic()) >= _MIN_VIABLE_CALL_S
    if truncated and not time_to_split and len(fields) > _MIN_SPLIT:
        logger.info("vision(%s): %.0fs left — too little to split into viable "
                    "halves, keeping what landed", label, deadline - time.monotonic())
    if truncated and time_to_split and len(fields) > _MIN_SPLIT and depth < _MAX_SPLIT_DEPTH:
        names = list(fields)
        mid = len(names) // 2
        halves = [{n: fields[n] for n in names[:mid]},
                  {n: fields[n] for n in names[mid:]}]
        # HALVE THE CEILING WITH THE FIELDS. Half the fields need roughly half
        # the output, and the ceiling is what the read timeout is racing — leave
        # it at full size and each half is just as able to run the clock out as
        # the whole was. Run 19 split `market` three times and every descendant
        # still carried the parent's ceiling, which is why splitting recovered
        # the fields but not the wall clock.
        half_ceiling = max(_MIN_CEILING, int(max_tokens // 2))
        logger.info("vision(%s): still truncated — splitting %d fields into %d + %d "
                    "(ceiling %d -> %d)", label, len(names), len(halves[0]),
                    len(halves[1]), max_tokens, half_ceiling)
        result.splits += 1

        # RUN THE HALVES CONCURRENTLY. They are independent — each transcribes
        # its own fields from the same images — so serialising them multiplied
        # the section's wall clock by the size of the split tree for no benefit.
        # In run 19 that turned `market` into 1,566s of a 1,667s run.
        #
        # This is only safe because the provider now enforces a GLOBAL in-flight
        # limit. Nested pools without that gate is exactly the double-counting
        # that put 16 calls on 4 keys and timed out nine grid calls; here the
        # halves queue on the same gate as everything else and simply overlap
        # their stalls instead of adding them.
        sub: List[CompletionResult] = [CompletionResult(), CompletionResult()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(transcribe_complete, provider, images, instruction,
                            half, schema_for, max_tokens=half_ceiling,
                            effort=effort, label=f"{label}/{i + 1}",
                            depth=depth + 1, result=sub[i], deadline=deadline)
                for i, half in enumerate(halves)
            ]
            for f in futures:
                try:
                    f.result()
                except Exception as exc:  # pragma: no cover - defensive
                    result.errors.append(f"{label}: split failed: {exc}")
        for s in sub:
            result.absorb_child(s)
        return result

    # ── nothing left to try: record exactly what was lost ────────────────────
    if resp.error:
        result.errors.append(f"{label}: {resp.error}")
    missing = [n for n in fields if n not in result.data]
    result.missing_fields.extend(missing)
    if missing:
        logger.warning("vision(%s): %d field(s) unresolved after retry and split",
                       label, len(missing))
    return result


def _merge(into: Dict[str, Any], new: Dict[str, Any]) -> None:
    """Union of results. A later non-empty value fills an earlier gap; a value
    already present is never overwritten, so the first (largest-context) read
    wins over a narrower re-read of the same field."""
    for key, val in (new or {}).items():
        if val in (None, "", [], {}):
            continue
        if isinstance(val, dict) and val.get("value") in (None, ""):
            # A provenance wrapper with no value carries nothing.
            if key not in into:
                into[key] = val
            continue
        into.setdefault(key, val)
