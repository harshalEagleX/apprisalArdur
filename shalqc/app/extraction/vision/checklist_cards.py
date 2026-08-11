"""
extraction.vision.checklist_cards (ckc-1.0.0) — vision answers -> reviewer cards.

The 3.6 checklist is answered by looking at pages (`checklist_vision`), but the
reviewer, the Java service and the frontend already speak one language:
`ReviewerCard`. Emitting the same type means the 3.6 path needs no new UI, no new
DTO and no new endpoint — a 3.6 order lands in the existing queue beside a 2.6
one and a reviewer cannot tell which pipeline produced it.

Two mappings carry all the judgement, and both are deliberate:

**Status.** PASS -> SATISFIED, FAIL -> NOT_SATISFIED, VERIFY -> REVIEW. Nothing
maps to NOT_APPLICABLE: this pipeline never decides an AMC question does not
apply, because that decision needs the order context (transaction type, form
type) that lives outside these pages.

**Group, i.e. what reaches the reviewer's queue.** A FAIL becomes
`recommended_reject` ONLY when the catalog marks the item rejectable; otherwise it
is `please_verify`. That gate exists because the AMC's checklist mixes hard reject
criteria with informational questions, and treating the second kind as a reject
is what produced the false-rejection problem this project was built to remove.

Visual items get `manual_visual` rather than `please_verify` when they could not
be settled — it tells the reviewer "open the photos", which is a different and
much faster action than "check this value".
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.extraction.vision.checklist_vision import FAIL, PASS, VERIFY, ChecklistAnswer

__version__ = "ckc-1.0.0"

logger = logging.getLogger(__name__)

_STATUS = {PASS: "SATISFIED", FAIL: "NOT_SATISFIED", VERIFY: "REVIEW"}


def _group(answer: ChecklistAnswer, rejectable: bool, visual: bool) -> str:
    if answer.status == PASS:
        return "looks_good"
    if answer.status == FAIL:
        return "recommended_reject" if rejectable else "please_verify"
    return "manual_visual" if visual else "please_verify"


def to_cards(answers: List[ChecklistAnswer], catalog_items: List[Dict[str, Any]],
             ) -> List[Dict[str, Any]]:
    """One reviewer card per checklist answer, in ReviewerCard shape."""
    by_rule = {i.get("rule_id"): i for i in catalog_items}
    cards: List[Dict[str, Any]] = []

    for a in answers:
        item = by_rule.get(a.rule_id, {})
        visual = item.get("binding") == "visual"
        # `reject_as` non-empty is the catalog's own marker that the AMC wrote
        # rejection wording for this item — i.e. it is rejectable. Absent wording
        # means the question is informational, and a finding on it belongs in the
        # verify lane, not the reject lane.
        rejectable = bool(item.get("reject_as"))
        status = _STATUS.get(a.status, "REVIEW")

        evidence = [{
            "label": f"page {p}" if a.pages else "observed",
            "value": None, "quote": e, "page": (a.pages[0] if a.pages else None),
            "bbox": None,
            # The model cited the page it read but not a rectangle on it, so the
            # card can scroll to the page and no further. Claiming a bbox we did
            # not measure would send the reviewer to the wrong part of the page,
            # which is worse than sending them to the top of the right one.
            "location_quality": "page" if a.pages else "none",
            "source": "vision", "source_badge": "VISION", "confidence": 0.0,
        } for e, p in zip(a.evidence, (a.pages or [None]) * len(a.evidence))]

        cards.append({
            "item_id": a.rule_id,
            "group": _group(a, rejectable, visual),
            "section": a.section,
            "status": status,
            "item_name": (item.get("item") or a.question)[:90],
            "check_text": a.question,
            "description": a.question,
            "reject_text": (item.get("reject_as") or [None])[0],
            "headline": a.observed[:140] or a.reason,
            "expected": "as required by the checklist item",
            "found": a.observed or "nothing conclusive visible",
            "reviewer_line": a.reason,
            "evidence": evidence,
            "primary_location": ({"page": a.pages[0], "bbox": None,
                                  "label": a.section, "location_quality": "page"}
                                 if a.pages else None),
            "values": {"answer": a.answer, "pages_examined": a.pages},
            "confidence": 0.0,
            # Tells the UI this was decided by looking, not by comparing text —
            # the reviewer's verification action is "open the page", not "check
            # the extracted value".
            "judgeable": "visual",
            "decided_by": "vision:gemma",
            "guardrails": ([] if a.evidence else ["no visible evidence cited"]),
            "severity": "rejectable" if (rejectable and a.status == FAIL)
                        else "informational",
        })
    return cards


def summarize(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Queue-shaped counts: what a reviewer will actually be handed."""
    groups: Dict[str, int] = {}
    for c in cards:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
    return {
        "total": len(cards),
        "by_group": groups,
        # The queue is what is NOT looks_good — the number that decides whether
        # this order costs a reviewer two minutes or twenty.
        "queue": sum(n for g, n in groups.items() if g != "looks_good"),
    }
