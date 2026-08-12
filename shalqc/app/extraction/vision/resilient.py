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
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.extraction.vision.provider import VisionProvider, VisionResponse
from app.extraction.vision.render import RenderedPage

__version__ = "rsl-1.0.0"

logger = logging.getLogger(__name__)

# Stop splitting here. Below a handful of fields the reasoning tax dominates and
# further splitting adds calls without shrinking the per-call output.
_MIN_SPLIT = 3
# Absolute ceiling for one call. Output generates SERIALLY, so a ceiling is also
# a duration: at the rate a contended call actually achieves, 12k tokens is
# minutes of wall clock and cannot finish inside any sane read timeout. Nothing
# raises a ceiling any more — see the split note below — so this is a cap on what
# a CALLER may ask for, not a level anything escalates to.
_HARD_MAX_TOKENS = 6_500


class CompletionResult:
    """Merged data plus an honest account of what it took to get it."""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.calls: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.splits: int = 0
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

    def summary(self) -> Dict[str, Any]:
        return {"calls": self.calls, "splits": self.splits, "retries": self.retries,
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
) -> CompletionResult:
    """Transcribe `fields` from `images`, splitting rather than losing anything.

    `schema_for` builds the JSON schema for a subset of `fields`, so the split
    halves are structurally identical to the whole — the model never sees a
    different contract, only a shorter one.
    """
    result = result or CompletionResult()
    if not fields:
        return result

    ceiling = int(min(max_tokens, _HARD_MAX_TOKENS))
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
    if truncated and len(fields) > _MIN_SPLIT:
        names = list(fields)
        mid = len(names) // 2
        halves = [{n: fields[n] for n in names[:mid]},
                  {n: fields[n] for n in names[mid:]}]
        logger.info("vision(%s): still truncated — splitting %d fields into %d + %d",
                    label, len(names), len(halves[0]), len(halves[1]))
        result.splits += 1
        for i, half in enumerate(halves):
            transcribe_complete(
                provider, images, instruction, half, schema_for,
                max_tokens=max_tokens, effort=effort,
                label=f"{label}/{i + 1}", depth=depth + 1, result=result)
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
