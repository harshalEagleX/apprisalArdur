"""
Map a QCReport into the JSON shape the Java backend's PythonQCResponse /
PythonRuleResult records expect (the /qc/process contract).

The Java side already has fully-built QCResult / QCRuleResult entities and the
reviewer/admin UI; this is the adapter that lets the new app/qc engine feed them.
Field names here match the @JsonProperty names in
common/dto/python/PythonQCResponse.java and PythonRuleResult.java exactly.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.qc.context import QCContext
from app.qc.registry import all_rules
from app.qc.result import QCReport, RuleResult, RuleStatus

# Version of the PythonQCResponse wire CONTRACT (dict shape + nested payloads).
# Bump on any structural change so consumers can detect drift. See usage below.
CONTRACT_SCHEMA_VERSION = "1.0"

# rule_id -> the engine's human-readable rule name (the @rule(name=...) label),
# built lazily once the rule registry is populated. The reviewer UI shows this as
# the rule's title, so it must be a real description, not "Section — ID".
_RULE_NAMES: Dict[str, str] = {}

# Cached rule-engine version stamp: the semantic QC_RULESET_VERSION plus a short
# fingerprint of the registered rule ids, so the stamp changes when rules are
# added/removed. Computed once the registry is populated.
_RULE_ENGINE_VERSION: Optional[str] = None


def _rule_engine_version() -> str:
    """`{QC_RULESET_VERSION}+{fingerprint}` — the version stamped on every result
    so two runs are comparable and a flag delta is attributable to a rule change."""
    global _RULE_ENGINE_VERSION
    if _RULE_ENGINE_VERSION is None:
        import hashlib
        from app import config
        ids = sorted(spec.rule_id for spec in all_rules())
        fp = hashlib.sha1("|".join(ids).encode()).hexdigest()[:8] if ids else "00000000"
        _RULE_ENGINE_VERSION = f"{config.QC_RULESET_VERSION}+{fp}"
    return _RULE_ENGINE_VERSION


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


_COMP_FIELD = re.compile(r"(?:^|_)comp_(\d+)_")

# Fields that name a specific SOURCE of an otherwise-subject value, so a
# cross-source check (e.g. SCA-17 GLA) shows which source each value came from.
_SOURCE_LABELS = {
    "subject_grid_gla": "SCA grid",
    "gla": "Improvements",
    "sketch_living_area": "Sketch",
}


def _primary_evidence(r: RuleResult):
    """Pick the one evidence whose location drives the reviewer's click-to-scroll.
    The viewer scrolls the appraisal report, so prefer an appraisal evidence that
    has a precise field box, then any evidence with a box, then any with a page
    (appraisal preferred). Returns None when nothing carries a location."""
    ev = r.evidence
    return (
        next((e for e in ev if e.bbox and e.document == "appraisal"), None)
        or next((e for e in ev if e.bbox), None)
        or next((e for e in ev if e.page and e.document == "appraisal"), None)
        or next((e for e in ev if e.page), None)
    )


def _comparable_label(field: Optional[str], document: str) -> Optional[str]:
    """Which property/source a piece of evidence belongs to, for the reviewer
    panel: a named source for known cross-source fields, "Comp N" for a
    comparable field, "Subject" for any other appraisal field, and None for
    contract/engagement evidence (the document label is enough)."""
    if field:
        if field in _SOURCE_LABELS:
            return _SOURCE_LABELS[field]
        m = _COMP_FIELD.search(field)
        if m:
            return f"Comp {int(m.group(1))}"
    if document == "appraisal":
        return "Subject"
    return None


_CROSS_DOC_SECTIONS = frozenset({"global", "cross_document", "semantic"})


def _rule_scope(r: RuleResult) -> str:
    """Classify a rule result as per_document, cross_document, or semantic.

    per_document  — rule reads a single document only (most UAD rules)
    cross_document — rule compares values ACROSS appraisal/engagement/contract
    semantic       — rule uses LLM-based narrative/semantic analysis
    """
    if r.section in _CROSS_DOC_SECTIONS:
        return r.section if r.section in ("semantic",) else "cross_document"
    docs = {e.document for e in r.evidence if e.document}
    if len(docs) > 1:
        return "cross_document"
    return "per_document"


def _rule_to_json(r: RuleResult) -> Dict:
    appraisal_value = _doc_value(r, "appraisal")
    engagement_value = _doc_value(r, "engagement") or _doc_value(r, "contract")
    # The location that drives click-to-scroll: page + (when located) the precise
    # normalized field box. Falls back to page-only, then nothing.
    primary = _primary_evidence(r)
    page = primary.page if primary and primary.page else 0
    box = primary.bbox if primary else None
    is_review = r.status in _REVIEW
    # Guarantee: a rule the reviewer must act on ALWAYS scrolls somewhere. When a
    # derived/LLM value (e.g. sale_type, adverse_site_conditions) couldn't be
    # located on any page, fall back to the report's first page — the URAR form
    # page that carries the subject/contract/site/improvements sections. Page-level
    # only (no box), so it never highlights the wrong line.
    if is_review and not page:
        page = 1
    # Structured, document-tagged evidence. This is the authoritative record of
    # WHICH document each value came from (appraisal | engagement | contract |
    # ...). The flattened appraisal_value/engagement_value fields below collapse
    # engagement and contract into one slot and lose that attribution; the
    # reviewer UI must use this list, not those, to label sources correctly.
    # `bbox` is the per-evidence normalized field box (None when unlocated), so a
    # multi-field rule can make each side independently clickable later.
    evidence: List[Dict] = [
        {
            "document": e.document,
            "comparable": _comparable_label(e.field, e.document),
            "value": e.value,
            "confidence": round(e.confidence, 3),
            "page": e.page,
            "bbox": e.bbox,
            "method": e.method,
        }
        for e in r.evidence if e.value
    ]
    return {
        "rule_id": r.rule_id,
        "rule_name": _rule_display_name(r.rule_id, r.section),
        # Authoritative section from the engine (UI groups on this). Sent as an
        # explicit field so Java/UI never re-derive it from the rule-id prefix.
        "section": r.section.upper(),
        # scope: "per_document" | "cross_document" | "semantic" — lets Java
        # distinguish transaction-level findings from per-document ones (VF-4).
        "scope": _rule_scope(r),
        "status": _STATUS.get(r.status, "skipped"),
        "message": r.message or r.status.value,
        "severity": _SEVERITY.get(r.status, "STANDARD"),
        "action_item": r.message if is_review else "No reviewer action required.",
        "reasoning": r.reasoning or "",
        "details": {"checklist_num": r.checklist_num, "template_id": r.template_id,
                    "fields": r.fields_involved, "reasoning": r.reasoning or ""},
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
        "bbox_x": box["x"] if box else None,
        "bbox_y": box["y"] if box else None,
        "bbox_w": box["w"] if box else None,
        "bbox_h": box["h"] if box else None,
    }


# NOTE: pipeline stages are identified ONLY by their stable key (e.g. "subject_llm").
# The human display name is NOT produced or persisted here — it is derived from the
# key at render time by the frontend (frontend/lib/stageLabels.ts), so a wording
# change updates every view, historical and new, with no database backfill. The
# matching plain-language progress messages live in transaction.py (_emit).


def _section_label(section: str) -> str:
    return section.replace("_", " ").title()


def _aggregate_llm(report: QCReport) -> Dict[str, Dict]:
    """Sum the captured Groq calls by span (rule id or stage name). Returns
    {span: {calls, inference_ms, throttle_wait_ms, rate_limited}}."""
    by_span: Dict[str, Dict] = {}
    for c in report.llm_calls:
        span = c.span or "(unattributed)"
        agg = by_span.setdefault(span, {"calls": 0, "inference_ms": 0.0,
                                        "throttle_wait_ms": 0.0, "rate_limited": 0})
        agg["calls"] += 1
        agg["inference_ms"] += c.inference_ms
        agg["throttle_wait_ms"] += c.throttle_wait_ms
        agg["rate_limited"] += 1 if c.rate_limited else 0
    return by_span


def _build_timings(report: QCReport, total_ms: int) -> Dict:
    """Aggregate the engine's measured per-rule timings and the orchestrator's
    measured stage timings into a human-readable breakdown. All numbers are real
    perf_counter measurements — nothing here is estimated or proxied."""
    llm_by_span = _aggregate_llm(report)

    # per-rule, slowest first — wall-clock ms plus any Groq cost the rule incurred
    rules = sorted(
        (
            {
                "rule_id": t.rule_id,
                "rule_name": _rule_display_name(t.rule_id, t.section),
                "section": t.section.upper(),
                "status": t.status,
                "ms": round(t.ms, 3),
                "confidence": round(t.confidence, 3),
                "llm_calls": llm_by_span.get(t.rule_id, {}).get("calls", 0),
                "llm_ms": round(llm_by_span.get(t.rule_id, {}).get("inference_ms", 0.0), 3),
                "throttle_ms": round(llm_by_span.get(t.rule_id, {}).get("throttle_wait_ms", 0.0), 3),
            }
            for t in report.rule_timings
        ),
        key=lambda d: d["ms"], reverse=True,
    )

    # per-section roll-up
    sec_ms: Dict[str, float] = {}
    sec_count: Dict[str, int] = {}
    for t in report.rule_timings:
        sec_ms[t.section] = sec_ms.get(t.section, 0.0) + t.ms
        sec_count[t.section] = sec_count.get(t.section, 0) + 1
    rule_engine_ms = sum(sec_ms.values())
    sections = sorted(
        (
            {
                "section": s.upper(),
                "label": _section_label(s),
                "ms": round(ms, 3),
                "rule_count": sec_count[s],
                "pct_of_rules": round(ms / rule_engine_ms * 100, 1) if rule_engine_ms else 0.0,
            }
            for s, ms in sec_ms.items()
        ),
        key=lambda d: d["ms"], reverse=True,
    )

    # pipeline stages (extraction phases + rule evaluation) — each stage's Groq
    # inference vs throttle-wait split, when the stage made LLM calls
    stage_total = sum(report.stage_ms.values()) or 1.0
    stages = sorted(
        (
            {
                "stage": name,            # stable key; display name derived at render time
                "ms": round(ms, 3),
                "pct_of_pipeline": round(ms / stage_total * 100, 1),
                "llm_calls": llm_by_span.get(name, {}).get("calls", 0),
                "inference_ms": round(llm_by_span.get(name, {}).get("inference_ms", 0.0), 3),
                "throttle_wait_ms": round(llm_by_span.get(name, {}).get("throttle_wait_ms", 0.0), 3),
            }
            for name, ms in report.stage_ms.items()
        ),
        key=lambda d: d["ms"], reverse=True,
    )

    # corpus-level LLM summary for this run
    total_calls = sum(a["calls"] for a in llm_by_span.values())
    total_inference = sum(a["inference_ms"] for a in llm_by_span.values())
    total_throttle = sum(a["throttle_wait_ms"] for a in llm_by_span.values())
    rate_limit_hits = sum(a["rate_limited"] for a in llm_by_span.values())
    llm = {
        "total_calls": total_calls,
        "total_inference_ms": round(total_inference, 3),
        "total_throttle_wait_ms": round(total_throttle, 3),
        "rate_limit_hits": rate_limit_hits,
    }

    return {
        "total_ms": total_ms,
        "rule_engine_ms": round(rule_engine_ms, 3),
        "measured_pipeline_ms": round(sum(report.stage_ms.values()), 3),
        "rule_count": len(report.rule_timings),
        "stages": stages,
        "sections": sections,
        "rules": rules,
        "llm": llm,
        "slowest_stage": stages[0] if stages else None,
        "slowest_section": sections[0] if sections else None,
        "slowest_rule": rules[0] if rules else None,
    }


def report_to_python_qc_response(
    report: QCReport, ctx: QCContext, *,
    processing_time_ms: int = 0, document_id: str = "", job_id: str = "",
    model_provider: str = "groq", text_model: str = "", vision_model: str = "",
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

    # Explicit blocking signal computed at the source of truth: any HOLD rule
    # blocks the report. Emitting it here (rather than re-deriving it from the
    # verify count in the UI) lets every client — reviewer UI, API, future
    # automation — honour the blocking contract identically (remediation E1).
    blocking_rules = [r.rule_id for r in report.results if r.status == RuleStatus.HOLD]

    return {
        # Version of the PythonQCResponse CONTRACT shape (not the ruleset). Bump
        # whenever a field is added/removed/retyped in this dict or in the nested
        # rule_results/evidence/timings payloads, so the Java side (and any future
        # consumer) can detect a contract change instead of silently misreading a
        # drifted payload. Independent of rule_engine_version (rule LOGIC) and
        # EXTRACTION_LAYER_VERSION (extraction behaviour).
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "success": True,
        "processing_time_ms": processing_time_ms,
        "total_pages": 0,
        "extraction_method": "layered_parallel+qc",
        "extracted_fields": extracted_fields,
        "field_confidence": field_confidence,
        "total_rules": len(report.results),
        "rule_engine_version": _rule_engine_version(),
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
        "blocking": bool(blocking_rules),
        "blocking_rules": blocking_rules,
        "rule_results": rule_results,
        "action_items": action_items,
        "suggestions": [],
        "processing_notices": [],
        "timings": _build_timings(report, processing_time_ms),
    }
