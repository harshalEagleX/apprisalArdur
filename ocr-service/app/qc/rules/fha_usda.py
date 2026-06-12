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


# ---- FHA-5 primary comps within 12 months -----------------------------------

@rule(id="FHA-5", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA primary comps within 12 months")
def fha5_comp_dates(ctx: QCContext):
    from app.qc.rules.sales_comparison import _effective_ym, _parse_uad_date
    eff = _effective_ym(ctx)
    if eff is None:
        return RuleResult(rule_id="FHA-5", checklist_num="FHA", section="fha",
                          status=RuleStatus.VERIFY,
                          message="The effective date could not be read; please verify comps 1-3 sold within 12 months.",
                          fields_involved=["effective_date"], confidence=0.5)
    out = []
    for i in (1, 2, 3):
        raw = ctx.appraisal.value(f"comp_{i}_sale_date") or ""
        ev = [ctx.appraisal.evidence(f"comp_{i}_sale_date")]
        d = _parse_uad_date(raw)
        ym = d.get("s") or d.get("c")
        if not ym:
            continue  # SCA-8 surfaces unreadable comp dates
        months = (eff[0] - ym[0]) * 12 + (eff[1] - ym[1])
        if months > 12:
            # FHA hard requirement for the three primary comparables
            out.append(RuleResult(rule_id="FHA-5", checklist_num="FHA", section="fha",
                                  status=RuleStatus.FAIL,
                                  message=qc_config.template("FHA-5-comps", comp=i),
                                  fields_involved=[f"comp_{i}_sale_date"],
                                  template_id="FHA-5-comps", evidence=ev))
        else:
            out.append(RuleResult(rule_id="FHA-5", checklist_num="FHA", section="fha",
                                  status=RuleStatus.PASS,
                                  fields_involved=[f"comp_{i}_sale_date"], evidence=ev))
    return out


# ---- USDA-1 cost approach required (per-field corrections) -------------------

_USDA_COST_FIELDS = {
    "site_value_estimate": "Opinion of Site Value",
    "cost_new_improvements": "Cost New of Improvements",
    "total_depreciation": "Depreciation",
    "indicated_value_cost_approach": "Indicated Value by Cost Approach",
}


@rule(id="USDA-1", num="USDA", section="usda", phase=8, applies_when=_is_usda,
      name="USDA cost approach required")
def usda1_cost(ctx: QCContext):
    missing = [label for f, label in _USDA_COST_FIELDS.items()
               if not ctx.appraisal.value(f)]
    ev = [ctx.appraisal.evidence(f) for f in _USDA_COST_FIELDS]
    if not missing:
        return RuleResult(rule_id="USDA-1", checklist_num="USDA", section="usda",
                          status=RuleStatus.PASS,
                          fields_involved=list(_USDA_COST_FIELDS), evidence=ev)
    if len(missing) == len(_USDA_COST_FIELDS):
        return RuleResult(rule_id="USDA-1", checklist_num="USDA", section="usda",
                          status=RuleStatus.FAIL, message=qc_config.template("USDA-1-cost"),
                          fields_involved=list(_USDA_COST_FIELDS),
                          template_id="USDA-1-cost", evidence=ev)
    # partially developed — name the specific blanks for correction
    return RuleResult(rule_id="USDA-1", checklist_num="USDA", section="usda",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("USDA-1-fields", value=", ".join(missing)),
                      fields_involved=list(_USDA_COST_FIELDS),
                      template_id="USDA-1-fields", evidence=ev)


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
