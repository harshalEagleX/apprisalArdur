"""
report.builder (rpt-1.0.0) — SHALqc.md §8 reviewer output.

Turns the engine's Verdicts into ONE JSON per run for Java: a list of finding
cards plus a roll-up. Each card is one root cause (SHALqc.md §8: "address
mismatch = ONE card, not 3 sibling findings"), in plain words, with clickable
evidence and the AMC's exact suggested wording.

Card order (§8): FAIL → HOLD → VERIFY → (PASS/NA collapsed behind a count), so
the reviewer sees "38 checks passed, 2 need your words, 5 to verify" — not 322
rows. `report.versions` is stamped on every response (§12 DoD #5).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.report.versions import report_versions
from app.report.wording import wording_book
from app.rules.verdict import Status, Verdict

__version__ = "rpt-1.0.0"

# Severity order for card sorting (lower = shown first).
_ORDER = {Status.FAIL: 0, Status.HOLD: 1, Status.VERIFY: 2,
          Status.PASS: 3, Status.NOT_APPLICABLE: 4}
_EXCEPTION = {Status.FAIL, Status.HOLD, Status.VERIFY}


def _root_field(v: Verdict) -> str:
    """Group key = the shared root field of the finding. Strips a doc prefix
    ("engagement.property_address" → "property_address") and a comp index
    ("comp_3_sale_price" → "comp_sale_price") so same-root findings collapse."""
    field = (v.fields_involved[0] if v.fields_involved else v.rule_id)
    if "." in field:
        field = field.split(".", 1)[1]
    field = re.sub(r"^comp_\d+_", "comp_", field)
    return field


# SHALqc-CORE §5: human-facing badge for where a value came from.
_SOURCE_BADGE = {
    "xml": "XML", "Source.XML": "XML",
    "pdf_digital": "Report", "pdf_scanned": "Report", "grid": "Report",
    "checkbox": "Report", "acroform": "Report",
    "engagement": "Order form", "llm": "AI-read", "contract": "Contract",
}


def _badge(source: Optional[str]) -> str:
    if not source:
        return ""
    key = source.split(".")[-1] if source.startswith("Source.") else source
    return _SOURCE_BADGE.get(source) or _SOURCE_BADGE.get(key, "Report")


def _evidence_json(v: Verdict) -> List[Dict[str, Any]]:
    return [
        {"field": e.field, "value": e.value, "document": e.document,
         "source": e.source, "source_badge": _badge(e.source),
         "page": e.page, "bbox": e.bbox,
         "location_quality": e.location_quality, "confidence": round(e.confidence, 3)}
        for e in v.evidence
    ]


def _headline(v: Verdict, name: str) -> str:
    if v.status == Status.FAIL:
        return name
    if v.status == Status.VERIFY:
        return f"Needs your words — {name}"
    if v.status == Status.HOLD:
        return f"On hold — {name}"
    return name


def _card(verdicts: List[Verdict], rule_names: Dict[str, str],
          wording_file: Optional[str]) -> Dict[str, Any]:
    """Merge a group of same-root verdicts into one card (most-severe wins)."""
    lead = min(verdicts, key=lambda v: _ORDER[v.status])
    name = rule_names.get(lead.rule_id, lead.rule_id)
    evidence: List[Dict[str, Any]] = []
    for v in verdicts:
        evidence.extend(_evidence_json(v))
    # For "please correct X to {value}" wording, {value} is the ORDER-FORM
    # (authority) value the report should be corrected TO — prefer the
    # engagement evidence, falling back to the first evidence value.
    auth_value = next((e.value for e in lead.evidence
                       if e.document == "engagement" and e.value), None)
    fill_value = auth_value or (lead.evidence[0].value if lead.evidence else "")
    suggested = wording_book.render(
        wording_file, lead.message_key, values={"value": fill_value}, fallback=lead.message,
    )
    return {
        "group": _root_field(lead),
        "status": lead.status.value,
        "confidence": round(lead.confidence, 3),
        "rule_ids": sorted({v.rule_id for v in verdicts}),
        "headline": _headline(lead, name),
        "what_we_checked": name,
        "what_we_found": lead.message or f"{name}: {lead.status.value}",
        "evidence": evidence,
        "suggested_wording": suggested,
        "degraded_reason": lead.degraded_reason,
    }


def build_report(order_id: str, verdicts: List[Verdict],
                 rule_names: Optional[Dict[str, str]] = None,
                 profile=None, amc_code: str = "",
                 hold_reasons: Optional[List[str]] = None,
                 degradations: Optional[List[str]] = None) -> Dict[str, Any]:
    """Assemble the reviewer JSON. `rule_names` maps rule_id → human name (from
    the registry); `profile` supplies the wording file + fingerprint."""
    rule_names = rule_names or {}
    wording_file = getattr(profile, "wording_file", "") or None

    # Split appraiser-actionable (reviewer) from engine-actionable (engine health).
    # Engine items (unmapped field / unimplemented check / extraction gap) never
    # reach the reviewer queue or AMC wording — they are our problem, not theirs.
    appraiser = [v for v in verdicts if getattr(v, "actionable_by", "appraiser") != "engine"]
    engine = [v for v in verdicts if getattr(v, "actionable_by", "appraiser") == "engine"]

    exceptions = [v for v in appraiser if v.status in _EXCEPTION]

    # group exceptions by shared root field, one card per group
    groups: Dict[str, List[Verdict]] = {}
    for v in exceptions:
        groups.setdefault(_root_field(v), []).append(v)
    cards = [_card(vs, rule_names, wording_file) for vs in groups.values()]
    cards.sort(key=lambda c: (_ORDER[Status(c["status"])], c["group"]))

    # summary counts ONLY appraiser-actionable verdicts (the real reviewer queue)
    counts = {s.value: 0 for s in Status}
    for v in appraiser:
        counts[v.status.value] += 1

    manual_vision = sum(1 for v in appraiser if v.degraded_reason == "manual_vision_required")
    judged_by_llm = sum(1 for v in verdicts if getattr(v, "judged_by", ""))

    # engine-health: grouped counts by reason (unmapped/unimplemented/gap)
    eng_reasons: Dict[str, int] = {}
    for v in engine:
        r = (v.degraded_reason or "engine").split("|")[0]
        eng_reasons[r] = eng_reasons.get(r, 0) + 1

    report: Dict[str, Any] = {
        "order_id": order_id,
        "amc_code": amc_code or getattr(profile, "amc_code", ""),
        "summary": {
            "passed": counts[Status.PASS.value],
            "failed": counts[Status.FAIL.value],
            "hold": counts[Status.HOLD.value],
            "to_verify": counts[Status.VERIFY.value],
            "not_applicable": counts[Status.NOT_APPLICABLE.value],
            "needs_manual_vision_check": manual_vision,
            "judged_by_llm": judged_by_llm,
            "engine_health_items": len(engine),
        },
        "cards": cards,
        "engine_health": {
            "count": len(engine),
            "by_reason": eng_reasons,
            "rule_ids": sorted({v.rule_id for v in engine}),
        },
        "hold_reasons": hold_reasons or [],
        "degradations": degradations or [],
        "versions": report_versions(profile),
    }
    return report
