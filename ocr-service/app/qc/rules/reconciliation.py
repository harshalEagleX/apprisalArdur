"""
Reconciliation + Cost-approach rules (R-1, R-2, CA-1, CA-2 / checklist 88-93).
"""

from __future__ import annotations

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import match_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


# ---- R-1 indicated value (SCA) == appraised/market value ------------------

@rule(id="R-1", num="89", section="reconciliation", phase=3, name="SCA value matches market value")
def r1_value_match(ctx: QCContext):
    sca = ctx.appraisal.value("indicated_value_sca")
    final = ctx.appraisal.value("appraised_value")
    ev = [ctx.appraisal.evidence("indicated_value_sca"), ctx.appraisal.evidence("appraised_value")]
    if not sca or not final:
        return RuleResult(rule_id="R-1", checklist_num="89", section="reconciliation",
                          status=RuleStatus.VERIFY,
                          message="The indicated value (sales comparison) or final opinion of value could not be read; please verify they reconcile.",
                          fields_involved=["indicated_value_sca", "appraised_value"], evidence=ev, confidence=0.5)
    mr = match_currency(sca, final)
    if mr.verdict == "match":
        return RuleResult(rule_id="R-1", checklist_num="89", section="reconciliation",
                          status=RuleStatus.PASS,
                          fields_involved=["indicated_value_sca", "appraised_value"], evidence=ev)
    # Reconciliation value fields are extraction-sensitive — only hard-FAIL when
    # both reads are confident; otherwise route to human review.
    low_conf = min(ctx.appraisal.confidence("indicated_value_sca"),
                   ctx.appraisal.confidence("appraised_value")) < ctx.structured_conf
    status = RuleStatus.VERIFY if low_conf else RuleStatus.FAIL
    return RuleResult(rule_id="R-1", checklist_num="89", section="reconciliation",
                      status=status, message=qc_config.template("R-1-mismatch"),
                      fields_involved=["indicated_value_sca", "appraised_value"],
                      template_id="R-1-mismatch", evidence=ev, confidence=0.6)


# ---- R-2 As-Is / Subject-To box checked -----------------------------------

@rule(id="R-2", num="91", section="reconciliation", phase=3, name="As-Is / Subject-To checked")
def r2_asis(ctx: QCContext):
    val = ctx.appraisal.value("appraisal_subject_to")
    ev = [ctx.appraisal.evidence("appraisal_subject_to")]
    if val and str(val).strip():
        return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                          status=RuleStatus.PASS, fields_involved=["appraisal_subject_to"], evidence=ev)
    return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                      status=RuleStatus.VERIFY, message=qc_config.template("R-2-asisbox"),
                      fields_involved=["appraisal_subject_to"], template_id="R-2-asisbox",
                      evidence=ev, confidence=0.6)


# ---- CA-1 opinion of site value present (required in every report) --------

@rule(id="CA-1", num="92", section="cost_approach", phase=1, name="Opinion of site value present")
def ca1_site_value(ctx: QCContext):
    val = ctx.appraisal.value("site_value_estimate")
    ev = [ctx.appraisal.evidence("site_value_estimate")]
    if val and str(val).strip():
        return RuleResult(rule_id="CA-1", checklist_num="92", section="cost_approach",
                          status=RuleStatus.PASS, fields_involved=["site_value_estimate"], evidence=ev)
    # site value is commonly omitted; surface for review rather than hard-fail
    return RuleResult(rule_id="CA-1", checklist_num="92", section="cost_approach",
                      status=RuleStatus.VERIFY, message=qc_config.template("CA-1-sitevalue"),
                      fields_involved=["site_value_estimate"], template_id="CA-1-sitevalue",
                      evidence=ev, confidence=0.6)


# ---- CA-2 remaining economic life >= 30 (FHA/USDA/VA only) ----------------

@rule(id="CA-2", num="93", section="cost_approach", phase=8,
      applies_when=lambda ctx: ctx.loan_type in ("fha", "usda", "va"),
      name="Remaining economic life >= 30 (FHA/VA)")
def ca2_econ_life(ctx: QCContext):
    from app.qc.matching import normalize_currency
    val = normalize_currency(ctx.appraisal.value("remaining_economic_life"))
    ev = [ctx.appraisal.evidence("remaining_economic_life")]
    minimum = qc_config.semantic("remaining_economic_life_min", 30)
    if val is None:
        return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                          status=RuleStatus.VERIFY,
                          message="The remaining economic life could not be read; please verify it meets the FHA/USDA/VA minimum.",
                          fields_involved=["remaining_economic_life"], evidence=ev, confidence=0.5)
    if val >= minimum:
        return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                          status=RuleStatus.PASS, fields_involved=["remaining_economic_life"], evidence=ev)
    return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                      status=RuleStatus.VERIFY, message=qc_config.template("CA-2-life"),
                      fields_involved=["remaining_economic_life"], template_id="CA-2-life",
                      evidence=ev, confidence=0.7)
