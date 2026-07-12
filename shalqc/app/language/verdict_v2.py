"""
language.verdict_v2 — the v2 verdict vocabulary + reviewer-card mapping (§4.2/§5).

The judge speaks a NEW five-word vocabulary that talks about the *check*, not the
appraiser:

  SATISFIED        data clearly meets the check
  NOT_SATISFIED    data clearly violates the check (a reject *recommendation*)
  REVIEW           ambiguous / partial / a human call
  NOT_APPLICABLE   the check's precondition is absent in this report
  CANNOT_EVALUATE  the data needed is not in the packet at all

Hard rules encoded here (final_shalqccore.md §5):
  * The engine NEVER finalizes. NOT_SATISFIED is a recommendation; the reviewer's
    click is the decision of record.
  * EVERY item becomes a reviewer card — nothing is hidden — EXCEPT
    CANNOT_EVALUATE(source=engine), which goes to the Ops tab (extraction_gaps),
    never blaming the appraiser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StatusV2(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CANNOT_EVALUATE = "CANNOT_EVALUATE"


ALLOWED_STATUSES = {s.value for s in StatusV2}

# Reviewer card group per status (final_shalqccore.md §5).
CARD_GROUP = {
    StatusV2.NOT_SATISFIED: "recommended_reject",
    StatusV2.REVIEW: "please_verify",
    StatusV2.SATISFIED: "looks_good",
    StatusV2.NOT_APPLICABLE: "not_applicable",
    StatusV2.CANNOT_EVALUATE: "please_verify",   # source=report only; engine → ops
}

# Card ordering (lower shown first) — reject recommendations at the top.
CARD_ORDER = {
    "recommended_reject": 0,
    "please_verify": 1,
    "manual_visual": 2,
    "looks_good": 3,
    "not_applicable": 4,
}


@dataclass
class JudgeVerdict:
    """One validated verdict for one checklist item. `guardrails` records any
    validator degradation (§4.4) so judge quality is measurable per week."""

    item_id: str
    status: StatusV2
    check_text: str = ""
    section: str = ""
    expected: str = ""
    found: str = ""
    reviewer_line: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    suggest_reject_wording: Optional[str] = None
    confidence: float = 0.0
    # "report" (the report lacks the data → reviewer checks by eye) or "engine"
    # (extraction failed to read a value the XML/PDF actually carries → Ops tab).
    # Only meaningful for CANNOT_EVALUATE.
    source: str = "report"
    # "text" (LLM-judged) | "visual" (manual, never sent to LLM) | "unbound"
    judgeable: str = "text"
    guardrails: List[str] = field(default_factory=list)
    # who rendered it: "judge_v2" | "precompiled" | "fallback:<reason>"
    decided_by: str = "judge_v2"
    # the slim packet's located values, so a fallback card is still reviewable.
    values: Dict[str, Any] = field(default_factory=dict)

    def card_group(self) -> str:
        if self.judgeable == "visual":
            return "manual_visual"
        if self.status == StatusV2.CANNOT_EVALUATE and self.source == "engine":
            return "ops"  # extraction_gaps, not a reviewer card
        return CARD_GROUP[self.status]
