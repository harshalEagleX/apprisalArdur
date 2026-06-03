"""
Improvement section rules (I-1, I-7, I-9, quality, I-11 / checklist 40-52).
Presence/format (Phase 1) + a conformity judgment (Phase 3, VERIFY).
"""

from __future__ import annotations

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


# ---- I-1 general description present ---------------------------------------

@rule(id="I-1", num="40", section="improvements", phase=1, name="General description present")
def i1_general(ctx: QCContext):
    have = any(ctx.appraisal.value(f) for f in ("design_style", "year_built"))
    ev = [ctx.appraisal.evidence("design_style"), ctx.appraisal.evidence("year_built")]
    if have:
        return RuleResult(rule_id="I-1", checklist_num="40", section="improvements",
                          status=RuleStatus.PASS, fields_involved=["design_style", "year_built"], evidence=ev)
    return RuleResult(rule_id="I-1", checklist_num="40", section="improvements",
                      status=RuleStatus.FAIL, message=qc_config.template("I-1-gendesc"),
                      fields_involved=["design_style", "year_built"],
                      template_id="I-1-gendesc", evidence=ev)


# ---- I-7 above-grade room count present ------------------------------------

@rule(id="I-7", num="48", section="improvements", phase=1, name="Above-grade room count present")
def i7_rooms(ctx: QCContext):
    fields = ["total_rooms", "bedrooms", "baths", "gla"]
    missing = [f for f in fields if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in fields]
    if not missing:
        return RuleResult(rule_id="I-7", checklist_num="48", section="improvements",
                          status=RuleStatus.PASS, fields_involved=fields, evidence=ev)
    status = RuleStatus.VERIFY if len(missing) < len(fields) else RuleStatus.FAIL
    return RuleResult(rule_id="I-7", checklist_num="48", section="improvements",
                      status=status, message=qc_config.template("I-7-roomcount"),
                      fields_involved=missing, template_id="I-7-roomcount",
                      evidence=ev, confidence=0.7)


# ---- I-9 condition rating UAD format (C1-C6) -------------------------------

@rule(id="I-9", num="50", section="improvements", phase=1, name="Condition rating UAD format")
def i9_condition(ctx: QCContext):
    return H.format_regex(ctx, "I-9", "50", "improvements", "condition_rating",
                          r"^C[1-6]$", "I-9-condition", label="Condition")


# ---- I-Q quality rating UAD format (Q1-Q6) --------------------------------

@rule(id="I-Q", num="66", section="improvements", phase=1, name="Quality rating UAD format")
def iq_quality(ctx: QCContext):
    return H.format_regex(ctx, "I-Q", "66", "improvements", "quality_rating",
                          r"^Q[1-6]$", "I-Q-quality", label="Quality")


# ---- I-11 conformity to neighborhood (No → commentary) --------------------

@rule(id="I-11", num="52", section="improvements", phase=3, name="Conforms to neighborhood")
def i11_conform(ctx: QCContext):
    val = ctx.appraisal.value("conforms_to_neighborhood")
    ev = [ctx.appraisal.evidence("conforms_to_neighborhood")]
    if val is None:
        return RuleResult(rule_id="I-11", checklist_num="52", section="improvements",
                          status=RuleStatus.SKIPPED, message="conformity not extracted", evidence=ev)
    truthy = str(val).strip().lower() in {"true", "yes", "1", "x"}
    if truthy:
        return RuleResult(rule_id="I-11", checklist_num="52", section="improvements",
                          status=RuleStatus.PASS, fields_involved=["conforms_to_neighborhood"], evidence=ev)
    return RuleResult(rule_id="I-11", checklist_num="52", section="improvements",
                      status=RuleStatus.VERIFY, message=qc_config.template("I-11-conform"),
                      fields_involved=["conforms_to_neighborhood"],
                      template_id="I-11-conform", evidence=ev, confidence=0.7)
