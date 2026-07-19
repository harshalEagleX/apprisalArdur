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
    # P7: a card the system could not judge (LLM unavailable / empty packet) is a
    # SYSTEM-degradation item, not a property finding — sorted just below genuine
    # verify items and rendered as its own section so it never pollutes the
    # please_verify queue, while still counting toward `review` (order can't auto-pass).
    "needs_data": 2,
    "manual_visual": 3,
    "looks_good": 4,
    "not_applicable": 5,
    # PART 1.1: informational items carry no rejection authority — they sort last
    # and are pulled OUT of the reviewer queue entirely (see run.build_language_report).
    "informational": 6,
    # P6: unbindable checks — an admin/authoring backlog, also pulled OUT of the queue.
    "unauthored": 7,
}


@dataclass
class JudgeVerdict:
    """One validated verdict for one checklist item. `guardrails` records any
    validator degradation (§4.4) so judge quality is measurable per week."""

    item_id: str
    status: StatusV2
    check_text: str = ""
    section: str = ""
    # reviewer-facing description: the checklist's short name + the AMC's reject
    # wording (always carried, not only on NOT_SATISFIED, so the card can show it).
    item_name: str = ""
    reject_text: Optional[str] = None
    expected: str = ""
    found: str = ""
    reviewer_line: str = ""
    # located evidence, each entry: {label, value, quote?, page, bbox,
    # location_quality, source, source_badge, confidence} — page/bbox drive the
    # frontend document auto-scroll when the reviewer clicks the card.
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    # the single best {page, bbox} to jump the document to on card click.
    primary_location: Optional[Dict[str, Any]] = None
    suggest_reject_wording: Optional[str] = None
    confidence: float = 0.0
    # binding provenance carried from the compiled item (so the reviewer/Java see
    # how the check was bound and whether a human should trust it).
    bound_by: str = ""
    binder_confidence: float = 0.0
    bound_labels: List[str] = field(default_factory=list)
    # link to the stored raw LLM exchange for this item (llm_interactions.id).
    llm_interaction_id: Optional[str] = None
    # "report" (the report lacks the data → reviewer checks by eye) or "engine"
    # (extraction failed to read a value the XML/PDF actually carries → Ops tab).
    # Only meaningful for CANNOT_EVALUATE.
    source: str = "report"
    # PART 1.1: "rejectable" (AMC gave this check reject authority) | "informational"
    # (descriptive guidance — its verdict never becomes a reviewer VERIFY/reject card).
    severity: str = "informational"
    # "text" (LLM-judged) | "visual" (manual, never sent to LLM) | "unbound"
    judgeable: str = "text"
    guardrails: List[str] = field(default_factory=list)
    # 2026-07-18 (user directive): a check can have BOTH a text/value aspect and a
    # photo/sketch aspect — "verify condition rating matches the photos", "photos of
    # all outbuildings are required". Forcing such a check wholly into `visual`
    # would throw away a working automated check; leaving it wholly to the judge
    # lets a machine assert something about an image it cannot see. So the text
    # aspect is judged and reported as normal, and this flag rides alongside so the
    # reviewer is also told to confirm the photos by eye.
    photo_verification_required: bool = False
    # who rendered it: "judge_v2" | "precompiled" | "fallback:<reason>"
    decided_by: str = "judge_v2"
    # the slim packet's located values, so a fallback card is still reviewable.
    values: Dict[str, Any] = field(default_factory=dict)

    # A verdict that would otherwise noise the reviewer queue but carries no reject
    # authority: an informational item the judge could not clear (REVIEW /
    # CANNOT_EVALUATE) or "recommended reject" it (NOT_SATISFIED — but with no
    # reject_text there is nothing to reject on). PART 1.1: demote, never surface.
    _NOISE_STATUSES = frozenset({
        StatusV2.REVIEW, StatusV2.CANNOT_EVALUATE, StatusV2.NOT_SATISFIED})

    def card_group(self) -> str:
        if self.judgeable == "visual":
            return "manual_visual"
        if self.status == StatusV2.CANNOT_EVALUATE and self.source == "engine":
            return "ops"  # extraction_gaps, not a reviewer card
        # PART 1.1 + user directive 2026-07-17: an informational item (no AMC reject
        # authority) that is HARMLESS — SATISFIED / NOT_APPLICABLE — collapses into the
        # informational section. But one whose verdict is NOT_SATISFIED / REVIEW /
        # CANNOT_EVALUATE is a REAL finding the reviewer must act on, so it is PROMOTED
        # to its normal actionable group (please_verify / recommended_reject) rather
        # than hidden — the reviewer sees every failing/uncertain check in the queue.
        if self.severity != "rejectable" and self.status not in self._NOISE_STATUSES:
            return "informational"
        # P6: a rejectable check the binder never managed to bind to any field
        # (bound_by="unbound", confidence 0) is a config/authoring gap, not a
        # property finding — re-judging it will not help; a human must author the
        # binding. Route it to the UNAUTHORED admin backlog (like ops/extraction_gaps),
        # out of the reviewer queue — but only for noise statuses; a harmless
        # SATISFIED/NOT_APPLICABLE unbound item stays where it is.
        if self.bound_by == "unbound" and self.status in self._NOISE_STATUSES:
            return "unauthored"
        # P7: a rejectable item the system could not judge (LLM unavailable / empty
        # packet) is a system-degradation card — its own group, kept in the queue and
        # counted as review (blocks auto-pass) but never mixed into please_verify.
        if (self.decided_by or "").startswith("fallback:"):
            return "needs_data"
        return CARD_GROUP[self.status]
