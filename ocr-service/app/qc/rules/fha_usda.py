"""
FHA / USDA conditional overlay rules.

These fire ONLY when the engagement letter's loan type is FHA (FHA-*) or USDA
(USDA-*). On a conventional file they are recorded as NOT_APPLICABLE by the
engine's applicability gating, so reviewers see them greyed rather than missing.
loan_type comes from the engagement letter (the authority).
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import match_text, normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _is_fha(ctx: QCContext) -> bool:
    return ctx.loan_type == "fha"


def _is_usda(ctx: QCContext) -> bool:
    return ctx.loan_type == "usda"


def _is_fha_va(ctx: QCContext) -> bool:
    return ctx.loan_type in ("fha", "va")


# ---- FHA-2 case number present + format + matches order form --------------

@rule(id="FHA-2", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA case number format + match")
def fha2_case(ctx: QCContext):
    val = ctx.appraisal.value("fha_case_number")
    eng = ctx.engagement.value("fha_case_number")
    ev = [ctx.appraisal.evidence("fha_case_number"), ctx.engagement.evidence("fha_case_number")]
    if not val:
        return RuleResult(rule_id="FHA-2", checklist_num="FHA", section="fha",
                          status=RuleStatus.FAIL, message=qc_config.template("FHA-2-case"),
                          fields_involved=["fha_case_number"], template_id="FHA-2-case", evidence=ev)
    if not re.search(r"\d{3}-\d{7}", val):
        return RuleResult(rule_id="FHA-2", checklist_num="FHA", section="fha",
                          status=RuleStatus.VERIFY, message=qc_config.template("FHA-2-case"),
                          fields_involved=["fha_case_number"], template_id="FHA-2-case",
                          evidence=ev, confidence=0.7)
    if eng:
        mr = match_text(re.sub(r"\D", "", val), re.sub(r"\D", "", eng))
        if mr.verdict == "mismatch":
            return RuleResult(rule_id="FHA-2", checklist_num="FHA", section="fha",
                              status=RuleStatus.VERIFY,
                              message=qc_config.template("FHA-2-match", a=val, b=eng),
                              fields_involved=["fha_case_number"], template_id="FHA-2-match",
                              evidence=ev, confidence=0.7)
    return RuleResult(rule_id="FHA-2", checklist_num="FHA", section="fha",
                      status=RuleStatus.PASS, fields_involved=["fha_case_number"], evidence=ev)


# ---- FHA-3 intended use + user statements present -------------------------

@rule(id="FHA-3", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA intended use/user statements")
def fha3_intended(ctx: QCContext):
    use = ctx.appraisal.value("intended_use_statement")
    user = ctx.appraisal.value("intended_user_statement")
    ev = [ctx.appraisal.evidence("intended_use_statement"),
          ctx.appraisal.evidence("intended_user_statement")]
    if (use and "fha" in use.lower()) and (user and "hud" in user.lower()):
        return RuleResult(rule_id="FHA-3", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS,
                          fields_involved=["intended_use_statement", "intended_user_statement"], evidence=ev)
    return RuleResult(rule_id="FHA-3", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-3-intended"),
                      fields_involved=["intended_use_statement", "intended_user_statement"],
                      template_id="FHA-3-intended", evidence=ev, confidence=0.6)


# ---- FHA-10 remaining economic life >= 30 ---------------------------------

@rule(id="FHA-10", num="FHA", section="fha", phase=8, applies_when=_is_fha_va,
      name="FHA remaining economic life >= 30")
def fha10_econ_life(ctx: QCContext):
    val = normalize_currency(ctx.appraisal.value("remaining_economic_life"))
    ev = [ctx.appraisal.evidence("remaining_economic_life")]
    minimum = qc_config.semantic("remaining_economic_life_min", 30)
    if val is None:
        return RuleResult(rule_id="FHA-10", checklist_num="FHA", section="fha",
                          status=RuleStatus.VERIFY, message=qc_config.template("FHA-10-life"),
                          fields_involved=["remaining_economic_life"], template_id="FHA-10-life",
                          evidence=ev, confidence=0.6)
    if val >= minimum:
        return RuleResult(rule_id="FHA-10", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=["remaining_economic_life"], evidence=ev)
    return RuleResult(rule_id="FHA-10", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-10-life"),
                      fields_involved=["remaining_economic_life"], template_id="FHA-10-life",
                      evidence=ev, confidence=0.7)


# ---- USDA-1 cost approach required ----------------------------------------

@rule(id="USDA-1", num="USDA", section="usda", phase=8, applies_when=_is_usda,
      name="USDA cost approach required")
def usda1_cost(ctx: QCContext):
    used = str(ctx.appraisal.value("is_cost_approach_used") or "").lower() in {"true", "yes", "1", "x"}
    site = ctx.appraisal.value("site_value_estimate")
    ev = [ctx.appraisal.evidence("is_cost_approach_used"), ctx.appraisal.evidence("site_value_estimate")]
    if used or site:
        return RuleResult(rule_id="USDA-1", checklist_num="USDA", section="usda",
                          status=RuleStatus.PASS,
                          fields_involved=["is_cost_approach_used", "site_value_estimate"], evidence=ev)
    return RuleResult(rule_id="USDA-1", checklist_num="USDA", section="usda",
                      status=RuleStatus.FAIL, message=qc_config.template("USDA-1-cost"),
                      fields_involved=["is_cost_approach_used"], template_id="USDA-1-cost", evidence=ev)


# ---- ADD-4 1004MC required for FHA/USDA -----------------------------------

@rule(id="ADD-4", num="ADD", section="addendum", phase=8,
      applies_when=lambda ctx: ctx.loan_type in ("fha", "usda"),
      name="1004MC required for FHA/USDA")
def add4_mc(ctx: QCContext):
    # presence signal: any market-conditions field extracted
    mc_fields = ["market_conditions_commentary", "mc_median_sale_price", "mc_months_supply"]
    have = any(ctx.appraisal.value(f) for f in mc_fields)
    ev = [ctx.appraisal.evidence("market_conditions_commentary")]
    if have:
        return RuleResult(rule_id="ADD-4", checklist_num="ADD", section="addendum",
                          status=RuleStatus.PASS, fields_involved=mc_fields, evidence=ev)
    return RuleResult(rule_id="ADD-4", checklist_num="ADD", section="addendum",
                      status=RuleStatus.VERIFY, message=qc_config.template("ADD-4-mc"),
                      fields_involved=mc_fields, template_id="ADD-4-mc", evidence=ev, confidence=0.6)
