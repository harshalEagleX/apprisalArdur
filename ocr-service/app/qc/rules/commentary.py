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
# Two-tier check:
#   Tier 1 (deterministic): blank / too-short / canned phrases
#   Tier 2 (Groq, only when Tier 1 passes): is the narrative PROPERTY-SPECIFIC?
#   A generic sentence that happens not to match any canned phrase still fails
#   the quality bar the engagement letter and USPAP require.

def _groq_specific(text: str, question: str) -> bool:
    """Return True when Groq judges the text as sufficiently specific."""
    try:
        from app.extraction.llm_groq import assess_text
        return bool(assess_text(text, question))
    except Exception:
        return True   # if Groq unavailable, don't penalise (P-6)


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
    # Groq quality gate: a narrative that passes the canned-phrase filter can still
    # be generic ("The subject is in a stable residential neighborhood.") — ask the
    # model whether it contains property-specific facts.
    specific = _groq_specific(
        a.text,
        "Does this neighborhood description contain property-SPECIFIC facts — named "
        "streets, landmarks, or area names that identify the actual neighborhood, "
        "proximity to amenities, or local market characteristics — rather than only "
        "generic statements that could apply to any residential neighborhood?",
    )
    if not specific:
        return _verify("N-6", "24", "neighborhood", field, "N-6-generic", {}, ev, conf=0.6)
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
    # Groq quality gate: market conditions commentary must cite actual market data
    # (DOM, absorption rate, price trends, months supply, etc.), not just re-state
    # the checkbox answers in prose form.
    substantive = _groq_specific(
        a.text,
        "Does this market conditions commentary cite SPECIFIC market data or metrics — "
        "such as days on market, absorption rate, months supply, median price trend, "
        "or specific price/volume figures — rather than only restating the checkbox "
        "answers in prose ('property values are stable, demand/supply is in balance')?",
    )
    if not substantive:
        return _verify("N-7", "25", "neighborhood", field, "N-7-generic", {}, ev, conf=0.6)
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
