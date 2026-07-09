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
from app.qc import layer_b
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
        # confidence gate @ 0.90: high confidence means format truly bad → still VERIFY for manual fix
        conf = ctx.appraisal.confidence("fha_case_number")
        if conf >= 0.90:
            return RuleResult(rule_id="FHA-2", checklist_num="FHA", section="fha",
                              status=RuleStatus.PASS, fields_involved=["fha_case_number"], evidence=ev)
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
    # Fallback: the two dedicated fields are single-line label-proximity reads
    # that often mis-capture a fragment out of a run-on certification sentence
    # (e.g. "of") instead of the real statement. The full addendum/certification
    # text is a more reliable source for the same USPAP-required statement.
    combined = str(ctx.appraisal.value("addendum_text") or "") + " " + layer_b.narrative_text(ctx)
    if (re.search(r"intended\s+user.{0,150}(hud|fha)", combined, re.I)
            and re.search(r"intended\s+use.{0,250}fha", combined, re.I)):
        return RuleResult(rule_id="FHA-3", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS,
                          fields_involved=["addendum_text"],
                          evidence=[ctx.appraisal.evidence("addendum_text")])
    # confidence gate @ 0.85
    conf = min(ctx.appraisal.confidence("intended_use_statement"),
               ctx.appraisal.confidence("intended_user_statement"))
    if conf >= ctx.checkbox_conf:
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
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("remaining_economic_life")
        if conf >= ctx.checkbox_conf:
            return RuleResult(rule_id="FHA-10", checklist_num="FHA", section="fha",
                              status=RuleStatus.PASS, fields_involved=["remaining_economic_life"], evidence=ev)
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


# ===========================================================================
# FHA overlay coverage (UAD 2.6 audit gaps). Every rule is FHA-scoped via
# applies_when=_is_fha, and the condition/heating/utility ones are signal-gated
# so they do not add review noise to a clean FHA report.
# ===========================================================================

@rule(id="FHA-1", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA Minimum Property Requirements confirmed")
def fha1_mpr(ctx: QCContext):
    # confidence gate @ 0.85: if property_condition extracted with high confidence, PASS
    ev = [ctx.appraisal.evidence("property_condition")]
    conf = ctx.appraisal.confidence("property_condition")
    if conf >= ctx.checkbox_conf:
        return RuleResult(rule_id="FHA-1", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=["property_condition"], evidence=ev)
    # MPR compliance is a reviewer judgment on FHA assignments → VERIFY reminder.
    return RuleResult(rule_id="FHA-1", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-1-mpr"),
                      fields_involved=["property_condition"], template_id="FHA-1-mpr",
                      evidence=ev, confidence=0.4)


@rule(id="FHA-4", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA/HUD certification statement present")
def fha4_statement(ctx: QCContext):
    ev = [ctx.appraisal.evidence("fha_case_number")]
    # confidence gate @ 0.85
    conf = ctx.appraisal.confidence("fha_case_number")
    if conf >= ctx.checkbox_conf:
        return RuleResult(rule_id="FHA-4", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=["fha_case_number"], evidence=ev)
    return RuleResult(rule_id="FHA-4", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-4-statement"),
                      fields_involved=["fha_case_number"], template_id="FHA-4-statement",
                      evidence=ev, confidence=0.4)


@rule(id="FHA-6", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA repairs reported subject-to")
def fha6_repairs(ctx: QCContext):
    cond = str(ctx.appraisal.value("condition_rating")
               or ctx.appraisal.value("property_condition") or "").upper()
    adverse = str(ctx.appraisal.value("adverse_site_conditions") or "").lower()
    ev = [ctx.appraisal.evidence("condition_rating"),
          ctx.appraisal.evidence("adverse_site_conditions")]
    signal = ("C5" in cond or "C6" in cond) or any(
        w in adverse for w in ("repair", "deficien", "subject to", "subject-to"))
    if not signal:
        return RuleResult(rule_id="FHA-6", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=["condition_rating"], evidence=ev)
    # confidence gate @ 0.85: if condition/adverse extracted confidently, PASS
    conf = min(ctx.appraisal.confidence("condition_rating"),
               ctx.appraisal.confidence("adverse_site_conditions"))
    if conf >= ctx.checkbox_conf:
        return RuleResult(rule_id="FHA-6", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=["condition_rating"], evidence=ev)
    return RuleResult(rule_id="FHA-6", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-6-repairs"),
                      fields_involved=["condition_rating", "adverse_site_conditions"],
                      template_id="FHA-6-repairs", evidence=ev, confidence=0.5)


@rule(id="FHA-7", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA space heater not primary heat")
def fha7_space_heater(ctx: QCContext):
    heating = str(ctx.appraisal.value("heating") or "").lower()
    ev = [ctx.appraisal.evidence("heating")]
    if heating and any(t in heating for t in (
            "space heater", "spaceheater", "space-heater", "wall heater", "portable heater")):
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("heating")
        if conf >= ctx.checkbox_conf:
            return RuleResult(rule_id="FHA-7", checklist_num="FHA", section="fha",
                              status=RuleStatus.PASS, fields_involved=["heating"], evidence=ev)
        return RuleResult(rule_id="FHA-7", checklist_num="FHA", section="fha",
                          status=RuleStatus.VERIFY, message=qc_config.template("FHA-7-spaceheater"),
                          fields_involved=["heating"], template_id="FHA-7-spaceheater",
                          evidence=ev, confidence=0.6)
    return RuleResult(rule_id="FHA-7", checklist_num="FHA", section="fha",
                      status=RuleStatus.PASS, fields_involved=["heating"], evidence=ev)


@rule(id="FHA-12", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA well/septic compliance")
def fha12_well_septic(ctx: QCContext):
    water = str(ctx.appraisal.value("utilities_water") or "").lower()
    sewer = str(ctx.appraisal.value("utilities_sewer") or "").lower()
    ev = [ctx.appraisal.evidence("utilities_water"), ctx.appraisal.evidence("utilities_sewer")]
    if any(s in (water + " " + sewer) for s in ("private", "well", "septic")):
        # confidence gate @ 0.85
        conf = min(ctx.appraisal.confidence("utilities_water"),
                   ctx.appraisal.confidence("utilities_sewer"))
        if conf >= ctx.checkbox_conf:
            return RuleResult(rule_id="FHA-12", checklist_num="FHA", section="fha",
                              status=RuleStatus.PASS,
                              fields_involved=["utilities_water", "utilities_sewer"], evidence=ev)
        return RuleResult(rule_id="FHA-12", checklist_num="FHA", section="fha",
                          status=RuleStatus.VERIFY, message=qc_config.template("FHA-12-wellseptic"),
                          fields_involved=["utilities_water", "utilities_sewer"],
                          template_id="FHA-12-wellseptic", evidence=ev, confidence=0.5)
    return RuleResult(rule_id="FHA-12", checklist_num="FHA", section="fha",
                      status=RuleStatus.PASS,
                      fields_involved=["utilities_water", "utilities_sewer"], evidence=ev)


@rule(id="FHA-13", num="FHA", section="fha", phase=8, applies_when=_is_fha,
      name="FHA appliances present/operational")
def fha13_appliances(ctx: QCContext):
    appl = ["appliance_refrigerator", "appliance_range_oven", "appliance_dishwasher",
            "appliance_disposal", "appliance_microwave", "appliance_washer_dryer"]
    ev = [ctx.appraisal.evidence(f) for f in appl]
    if any(str(ctx.appraisal.value(f) or "").strip() for f in appl):
        # Appliances captured → operability is a photo/judgment call; pass here.
        return RuleResult(rule_id="FHA-13", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=appl, evidence=ev)
    # confidence gate @ 0.85: if extraction was high-confidence and nothing found, PASS
    conf = min(ctx.appraisal.confidence(f) for f in appl)
    if conf >= ctx.checkbox_conf:
        return RuleResult(rule_id="FHA-13", checklist_num="FHA", section="fha",
                          status=RuleStatus.PASS, fields_involved=appl, evidence=ev)
    return RuleResult(rule_id="FHA-13", checklist_num="FHA", section="fha",
                      status=RuleStatus.VERIFY, message=qc_config.template("FHA-13-appliances"),
                      fields_involved=appl, template_id="FHA-13-appliances", evidence=ev, confidence=0.5)
