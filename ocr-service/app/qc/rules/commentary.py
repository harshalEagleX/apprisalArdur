"""
Commentary / NLP rules (N-6, N-7, ADD-1, reconciliation terms / checklist 24,25,90,118).

Deterministic canned-phrase + specificity checks (app.qc.commentary). All emit
VERIFY (advisory) per the agreed model — a reviewer confirms narrative quality.
Phase 5.
"""

from __future__ import annotations

from app.qc.commentary import analyze_commentary, reconciliation_forbidden_terms
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _verify(rule_id, num, section, field, template_id, msg_kwargs, ev, conf=0.6):
    return RuleResult(rule_id=rule_id, checklist_num=num, section=section,
                      status=RuleStatus.VERIFY,
                      message=qc_config.template(template_id, **msg_kwargs),
                      fields_involved=[field], template_id=template_id,
                      evidence=ev, confidence=conf)


def _pass(rule_id, num, section, field, ev):
    return RuleResult(rule_id=rule_id, checklist_num=num, section=section,
                      status=RuleStatus.PASS, fields_involved=[field], evidence=ev)


# ---- N-6 neighborhood description present + specific ----------------------

@rule(id="N-6", num="24", section="neighborhood", phase=5, name="Neighborhood description specific")
def n6_description(ctx: QCContext):
    field = "neighborhood_description"
    a = analyze_commentary(ctx.appraisal.value(field))
    ev = [ctx.appraisal.evidence(field)]
    if a.blank or a.too_short:
        return _verify("N-6", "24", "neighborhood", field, "N-6-blank", {}, ev)
    if a.canned_hits:
        return _verify("N-6", "24", "neighborhood", field, "N-6-canned",
                       {"hits": ", ".join(a.canned_hits[:3])}, ev)
    return _pass("N-6", "24", "neighborhood", field, ev)


# ---- N-7 market conditions completed, not "see 1004MC" --------------------

@rule(id="N-7", num="25", section="neighborhood", phase=5, name="Market conditions completed")
def n7_market(ctx: QCContext):
    field = "market_conditions_commentary"
    a = analyze_commentary(ctx.appraisal.value(field))
    ev = [ctx.appraisal.evidence(field)]
    if a.defers_to_form:
        return _verify("N-7", "25", "neighborhood", field, "N-7-see1004mc", {}, ev, conf=0.75)
    if a.blank or a.too_short:
        return _verify("N-7", "25", "neighborhood", field, "N-7-blank", {}, ev)
    return _pass("N-7", "25", "neighborhood", field, ev)


# ---- ADD-1 no canned commentary in key narratives ------------------------

_NARRATIVES = {
    "sales_comparison_summary": "Sales Comparison summary",
    "final_reconciliation_comment": "Reconciliation commentary",
}


@rule(id="ADD-1", num="118", section="addendum", phase=5, name="No canned commentary")
def add1_canned(ctx: QCContext):
    out = []
    for field, label in _NARRATIVES.items():
        a = analyze_commentary(ctx.appraisal.value(field))
        ev = [ctx.appraisal.evidence(field)]
        if a.blank:
            continue  # presence handled elsewhere; only flag canned text here
        if a.canned_hits:
            out.append(_verify("ADD-1", "118", "addendum", field, "ADD-1-canned",
                               {"field": label, "hits": ", ".join(a.canned_hits[:3])}, ev))
        else:
            out.append(_pass("ADD-1", "118", "addendum", field, ev))
    return out


# ---- Reconciliation forbidden terms (checklist row 90) --------------------

@rule(id="RECON-T", num="90", section="reconciliation", phase=5, name="Reconciliation forbidden terms")
def recon_terms(ctx: QCContext):
    field = "final_reconciliation_comment"
    hits = reconciliation_forbidden_terms(ctx.appraisal.value(field))
    ev = [ctx.appraisal.evidence(field)]
    if hits:
        return _verify("RECON-T", "90", "reconciliation", field, "RECON-terms",
                       {"hits": ", ".join(hits)}, ev, conf=0.7)
    return _pass("RECON-T", "90", "reconciliation", field, ev)
