"""
Map a QCReport into the JSON shape the Java backend's PythonQCResponse /
PythonRuleResult records expect (the /qc/process contract).

The Java side already has fully-built QCResult / QCRuleResult entities and the
reviewer/admin UI; this is the adapter that lets the new app/qc engine feed them.
Field names here match the @JsonProperty names in
common/dto/python/PythonQCResponse.java and PythonRuleResult.java exactly.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.qc.context import QCContext
from app.qc.registry import all_rules
from app.qc.result import QCReport, RuleResult, RuleStatus

# rule_id -> the engine's human-readable rule name (the @rule(name=...) label),
# built lazily once the rule registry is populated. The reviewer UI shows this as
# the rule's title, so it must be a real description, not "Section — ID".
_RULE_NAMES: Dict[str, str] = {}


def _rule_display_name(rule_id: str, section: str) -> str:
    if not _RULE_NAMES:
        for spec in all_rules():
            _RULE_NAMES[spec.rule_id] = spec.name or ""
    name = _RULE_NAMES.get(rule_id, "")
    # Use the engine's descriptive label when it's a real human phrase (has a
    # space and isn't just the function name); else fall back to "Section — ID".
    if name and " " in name:
        return name
    return section.replace("_", " ").title() + f" — {rule_id}"


# our 5-state status -> the lowercase status string Java normalizes/stores
_STATUS = {
    RuleStatus.PASS: "pass",
    RuleStatus.FAIL: "fail",
    RuleStatus.VERIFY: "verify",
    RuleStatus.HOLD: "hold",
    RuleStatus.NOT_APPLICABLE: "not_applicable",
    RuleStatus.SKIPPED: "skipped",
}
# Severity vocabulary MUST match what the reviewer UI styles: BLOCKING |
# STANDARD | ADVISORY. Emitting anything else (e.g. HIGH/MEDIUM) makes the badge
# render the raw token with fallback styling and breaks the BLOCKING-gated
# acknowledgement flow. HOLD = escalate = BLOCKING; everything else is STANDARD
# until severity becomes a real per-rule attribute rather than status-derived.
_SEVERITY = {
    RuleStatus.HOLD: "BLOCKING",
    RuleStatus.FAIL: "STANDARD",
    RuleStatus.VERIFY: "STANDARD",
}
_REVIEW = {RuleStatus.FAIL, RuleStatus.VERIFY, RuleStatus.HOLD}


def _doc_value(r: RuleResult, doc: str) -> Optional[str]:
    for e in r.evidence:
        if e.document == doc and e.value:
            return e.value
    return None


def _rule_to_json(r: RuleResult) -> Dict:
    appraisal_value = _doc_value(r, "appraisal")
    engagement_value = _doc_value(r, "engagement") or _doc_value(r, "contract")
    page = next((e.page for e in r.evidence if e.page), 0)
    # Structured, document-tagged evidence. This is the authoritative record of
    # WHICH document each value came from (appraisal | engagement | contract |
    # ...). The flattened appraisal_value/engagement_value fields below collapse
    # engagement and contract into one slot and lose that attribution; the
    # reviewer UI must use this list, not those, to label sources correctly.
    evidence: List[Dict] = [
        {
            "document": e.document,
            "value": e.value,
            "confidence": round(e.confidence, 3),
            "page": e.page,
            "method": e.method,
        }
        for e in r.evidence if e.value
    ]
    is_review = r.status in _REVIEW
    return {
        "rule_id": r.rule_id,
        "rule_name": _rule_display_name(r.rule_id, r.section),
        # Authoritative section from the engine (UI groups on this). Sent as an
        # explicit field so Java/UI never re-derive it from the rule-id prefix.
        "section": r.section.upper(),
        "status": _STATUS.get(r.status, "skipped"),
        "message": r.message or r.status.value,
        "severity": _SEVERITY.get(r.status, "STANDARD"),
        "action_item": r.message if is_review else "No reviewer action required.",
        "details": {"checklist_num": r.checklist_num, "template_id": r.template_id,
                    "fields": r.fields_involved},
        "appraisal_value": appraisal_value,
        "engagement_value": engagement_value,
        "confidence": round(r.confidence, 3),
        "extracted_value": appraisal_value,
        "expected_value": engagement_value,
        "verify_question": r.message if r.status == RuleStatus.VERIFY else "",
        "rejection_text": r.message if is_review else "",
        "evidence": evidence,
        "review_required": is_review,
        "target_field": r.fields_involved[0] if r.fields_involved else None,
        "source_page": page,
        "bbox_x": None, "bbox_y": None, "bbox_w": None, "bbox_h": None,
    }


def report_to_python_qc_response(
    report: QCReport, ctx: QCContext, *,
    processing_time_ms: int = 0, document_id: str = "", job_id: str = "",
    model_provider: str = "ollama", text_model: str = "", vision_model: str = "",
    file_hash: str = "",
) -> Dict:
    """Build the PythonQCResponse dict from a QCReport + context."""
    counts = report.counts()
    rule_results = [_rule_to_json(r) for r in report.results]

    # extracted appraisal fields for the reviewer UI
    extracted_fields: Dict[str, str] = {}
    field_confidence: Dict[str, float] = {}
    for name, r in (ctx.appraisal._by_name.items() if ctx.appraisal.present else []):
        if r.found and r.value:
            extracted_fields[name] = str(r.value)
            field_confidence[name] = round(r.effective_confidence, 3)

    missing = []
    if not ctx.has_engagement:
        missing.append("engagement_letter")
    if ctx.transaction_type == "purchase" and not ctx.has_contract:
        missing.append("sales_contract")

    action_items = [r["action_item"] for r in rule_results if r["review_required"]]

    return {
        "success": True,
        "processing_time_ms": processing_time_ms,
        "total_pages": 0,
        "extraction_method": "layered_parallel+qc",
        "extracted_fields": extracted_fields,
        "field_confidence": field_confidence,
        "total_rules": len(report.results),
        "passed": counts.get("PASS", 0),
        "failed": counts.get("FAIL", 0),
        "verify": counts.get("VERIFY", 0) + counts.get("HOLD", 0),
        "document_id": document_id,
        "processing_job_id": job_id,
        "cache_hit": False,
        "file_hash": file_hash,
        "model_provider": model_provider,
        "model_name": text_model,
        "vision_model": vision_model,
        "supporting_document_missing": bool(missing),
        "missing_supporting_documents": missing,
        "rule_results": rule_results,
        "action_items": action_items,
        "suggestions": [],
        "processing_notices": [],
    }
