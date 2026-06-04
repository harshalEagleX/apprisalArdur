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
from app.qc.result import QCReport, RuleResult, RuleStatus

# our 5-state status -> the lowercase status string Java normalizes/stores
_STATUS = {
    RuleStatus.PASS: "pass",
    RuleStatus.FAIL: "fail",
    RuleStatus.VERIFY: "verify",
    RuleStatus.HOLD: "hold",
    RuleStatus.NOT_APPLICABLE: "not_applicable",
    RuleStatus.SKIPPED: "skipped",
}
_SEVERITY = {
    RuleStatus.HOLD: "BLOCKING",
    RuleStatus.FAIL: "HIGH",
    RuleStatus.VERIFY: "MEDIUM",
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
    evidence_strs: List[str] = [
        f"{e.document}: {e.value}"
        f" ({e.confidence * 100:.0f}%{', p' + str(e.page) if e.page else ''})"
        for e in r.evidence if e.value
    ]
    is_review = r.status in _REVIEW
    return {
        "rule_id": r.rule_id,
        "rule_name": r.section.replace("_", " ").title() + f" — {r.rule_id}",
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
        "evidence": evidence_strs,
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
