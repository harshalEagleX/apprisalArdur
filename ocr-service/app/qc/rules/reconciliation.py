"""
Reconciliation + Cost/Income-approach rules (R-1, R-2, CA-1..CA-3, IA-1, MF-1
/ checklist 88-93).
"""

from __future__ import annotations

import re

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.matching import match_currency, normalize_currency
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _res(rule_id, num, section, status, message="", fields=None, evidence=None,
         template_id=None, confidence=1.0) -> RuleResult:
    return RuleResult(rule_id=rule_id, checklist_num=num, section=section,
                      status=status, message=message, fields_involved=fields or [],
                      evidence=evidence or [], template_id=template_id,
                      confidence=confidence)


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
    out = []
    # multiple approaches developed → final must sit within their range; only
    # SCA developed → exact match (the classic R-1)
    others = [normalize_currency(ctx.appraisal.value(f))
              for f in ("indicated_value_cost_approach", "indicated_value_income_approach")]
    others = [v for v in others if v and v > 10_000]
    sca_n, final_n = normalize_currency(sca), normalize_currency(final)
    if others and sca_n and final_n:
        lo, hi = min([sca_n] + others), max([sca_n] + others)
        if lo <= final_n <= hi:
            out.append(_res("R-1", "89", "reconciliation", RuleStatus.PASS,
                            fields=["indicated_value_sca", "appraised_value"], evidence=ev))
        else:
            out.append(_res("R-1", "89", "reconciliation", RuleStatus.VERIFY,
                            message=qc_config.template("R-1-range", value=int(final_n),
                                                       a=int(lo), b=int(hi)),
                            fields=["indicated_value_sca", "indicated_value_cost_approach",
                                    "appraised_value"],
                            template_id="R-1-range", evidence=ev, confidence=0.7))
        return out
    mr = match_currency(sca, final)
    if mr.verdict == "match":
        return _res("R-1", "89", "reconciliation", RuleStatus.PASS,
                    fields=["indicated_value_sca", "appraised_value"], evidence=ev)
    # Reconciliation value fields are extraction-sensitive — only hard-FAIL when
    # both reads are confident; otherwise route to human review.
    low_conf = min(ctx.appraisal.confidence("indicated_value_sca"),
                   ctx.appraisal.confidence("appraised_value")) < ctx.structured_conf
    status = RuleStatus.VERIFY if low_conf else RuleStatus.FAIL
    return _res("R-1", "89", "reconciliation", status,
                message=qc_config.template("R-1-mismatch"),
                fields=["indicated_value_sca", "appraised_value"],
                template_id="R-1-mismatch", evidence=ev, confidence=0.6)


# ---- R-1b reconciliation commentary names the primary approach --------------

_WEIGHT_TERMS = re.compile(r"(most weight|greatest weight|primary (emphasis|approach)|"
                           r"weight(ed)? (was )?(given|placed)|emphasis (was )?(given|placed)|"
                           r"best (reflects|indicator)|relied (up)?on)", re.I)


@rule(id="R-1b", num="90", section="reconciliation", phase=5,
      name="Reconciliation names the weighted approach")
def r1b_weight(ctx: QCContext):
    text = (ctx.appraisal.value("final_reconciliation_comment") or "").strip()
    ev = [ctx.appraisal.evidence("final_reconciliation_comment")]
    if len(text) < 40:
        # no substantive reconciliation narrative extracted — reviewer confirms
        return _res("R-1b", "90", "reconciliation", RuleStatus.VERIFY,
                    message=qc_config.template("R-1-weight"),
                    fields=["final_reconciliation_comment"],
                    template_id="R-1-weight", evidence=ev, confidence=0.5)
    if _WEIGHT_TERMS.search(text) and re.search(r"sales comparison|cost approach|income approach",
                                                text, re.I):
        return _res("R-1b", "90", "reconciliation", RuleStatus.PASS,
                    fields=["final_reconciliation_comment"], evidence=ev)
    # keyword miss — let the LLM judge paraphrases before bothering a reviewer
    addressed = None
    try:
        from app.extraction.llm_groq import assess_text
        addressed = assess_text(
            text, "Does this appraisal reconciliation commentary identify which valuation "
                  "approach was given the most weight AND explain why?")
    except Exception:
        addressed = None
    if addressed:
        return _res("R-1b", "90", "reconciliation", RuleStatus.PASS,
                    fields=["final_reconciliation_comment"], evidence=ev)
    return _res("R-1b", "90", "reconciliation", RuleStatus.VERIFY,
                message=qc_config.template("R-1-weight"),
                fields=["final_reconciliation_comment"],
                template_id="R-1-weight", evidence=ev, confidence=0.6)


# ---- R-2b value == contract price exactly (appraisal-bias advisory) ---------

@rule(id="R-2b", num="88", section="reconciliation", phase=3,
      applies_when=lambda ctx: ctx.transaction_type == "purchase",
      name="Value equals contract price (bias advisory)")
def r2b_bias(ctx: QCContext):
    value = normalize_currency(ctx.appraisal.value("appraised_value"))
    price = normalize_currency(ctx.appraisal.value("contract_price"))
    ev = [ctx.appraisal.evidence("appraised_value"), ctx.appraisal.evidence("contract_price")]
    if not value or not price:
        return _res("R-2b", "88", "reconciliation", RuleStatus.NOT_APPLICABLE,
                    message="Value or contract price not available for the bias check.")
    if value == price:
        # advisory: value-to-price alignment is the most common indicator of
        # appraisal influence — a reviewer confirms independent support
        return _res("R-2b", "88", "reconciliation", RuleStatus.VERIFY,
                    message=qc_config.template("R-2-bias"),
                    fields=["appraised_value", "contract_price"],
                    template_id="R-2-bias", evidence=ev, confidence=0.7)
    return _res("R-2b", "88", "reconciliation", RuleStatus.PASS,
                fields=["appraised_value", "contract_price"], evidence=ev)


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


# ---- CA-3 cost approach arithmetic + depreciation reasonableness ------------

def _ca_developed(ctx: QCContext) -> bool:
    """The cost approach is treated as developed when its indicated value or
    cost-new figure was extracted; otherwise the CA-3 checks are N/A."""
    return bool(normalize_currency(ctx.appraisal.value("indicated_value_cost_approach"))
                or normalize_currency(ctx.appraisal.value("cost_new_improvements")))


@rule(id="CA-3", num="92b", section="cost_approach", phase=3, applies_when=_ca_developed,
      name="Cost approach arithmetic and depreciation")
def ca3_arithmetic(ctx: QCContext):
    site = normalize_currency(ctx.appraisal.value("site_value_estimate"))
    depr_cost = normalize_currency(ctx.appraisal.value("depreciated_cost_improvements"))
    indicated = normalize_currency(ctx.appraisal.value("indicated_value_cost_approach"))
    out = []
    fields = ["site_value_estimate", "depreciated_cost_improvements",
              "indicated_value_cost_approach"]
    ev = [ctx.appraisal.evidence(f) for f in fields]
    # indicated == site value + depreciated cost of improvements (within $100)
    if site and depr_cost and indicated:
        if abs(indicated - (site + depr_cost)) <= 100:
            out.append(_res("CA-3", "92b", "cost_approach", RuleStatus.PASS,
                            fields=fields, evidence=ev))
        else:
            status = RuleStatus.FAIL
            if min(ctx.appraisal.confidence(f) for f in fields) < ctx.structured_conf:
                status = RuleStatus.VERIFY
            out.append(_res("CA-3", "92b", "cost_approach", status,
                            message=qc_config.template("CA-3-arith", value=int(indicated),
                                                       a=int(site), b=int(depr_cost)),
                            fields=fields, template_id="CA-3-arith",
                            evidence=ev, confidence=0.7))
    # depreciation reasonableness vs the age-life baseline:
    # expected % ≈ effective age / (effective age + remaining economic life)
    cost_new = normalize_currency(ctx.appraisal.value("cost_new_improvements"))
    depr = normalize_currency(ctx.appraisal.value("total_depreciation"))
    eff_age = normalize_currency(ctx.appraisal.value("effective_age"))
    rel = normalize_currency(ctx.appraisal.value("remaining_economic_life"))
    if cost_new and depr is not None and eff_age is not None and rel and (eff_age + rel) > 0:
        stated_pct = depr / cost_new * 100.0
        expected_pct = eff_age / (eff_age + rel) * 100.0
        band = qc_config.semantic("depreciation_band_pp", 15.0)
        ev2 = [ctx.appraisal.evidence("total_depreciation"),
               ctx.appraisal.evidence("effective_age"),
               ctx.appraisal.evidence("remaining_economic_life")]
        if abs(stated_pct - expected_pct) > band:
            out.append(_res("CA-3", "92b", "cost_approach", RuleStatus.VERIFY,
                            message=qc_config.template("CA-3-depr"),
                            fields=["total_depreciation", "effective_age",
                                    "remaining_economic_life"],
                            template_id="CA-3-depr", evidence=ev2, confidence=0.6))
        else:
            out.append(_res("CA-3", "92b", "cost_approach", RuleStatus.PASS,
                            fields=["total_depreciation"], evidence=ev2))
    return out


# ---- IA-1 income approach rent vs subject rent schedule (1007) --------------

@rule(id="IA-1", num="94", section="income_approach", phase=3,
      name="Income approach rent matches rent schedule")
def ia1_rent_match(ctx: QCContext):
    ia_rent = normalize_currency(ctx.appraisal.value("income_approach_monthly_rent"))
    schedule = normalize_currency(ctx.appraisal.value("indicated_monthly_market_rent"))
    ev = [ctx.appraisal.evidence("income_approach_monthly_rent"),
          ctx.appraisal.evidence("indicated_monthly_market_rent")]
    fields = ["income_approach_monthly_rent", "indicated_monthly_market_rent"]
    if ia_rent is None or schedule is None:
        # the income approach / rent schedule is not in play on most SFR files
        return _res("IA-1", "94", "income_approach", RuleStatus.NOT_APPLICABLE,
                    message="Income approach / rent schedule not developed.")
    if abs(ia_rent - schedule) <= 5:
        return _res("IA-1", "94", "income_approach", RuleStatus.PASS,
                    fields=fields, evidence=ev)
    status = RuleStatus.FAIL
    if min(ctx.appraisal.confidence(f) for f in fields) < ctx.structured_conf:
        status = RuleStatus.VERIFY
    return _res("IA-1", "94", "income_approach", status,
                message=qc_config.template("IA-1-rent", a=int(ia_rent), b=int(schedule)),
                fields=fields, template_id="IA-1-rent", evidence=ev, confidence=0.7)


# ---- MF-1 multi-family requires the income approach -------------------------

def _is_multi_unit(ctx: QCContext) -> bool:
    if ctx.form_type == "1025":
        return True
    units = normalize_currency(ctx.appraisal.value("units_count"))
    return bool(units and 2 <= units <= 4)


@rule(id="MF-1", num="95", section="income_approach", phase=3, applies_when=_is_multi_unit,
      name="Multi-family requires income approach")
def mf1_income_required(ctx: QCContext):
    developed = (str(ctx.appraisal.value("is_income_approach_used") or "").lower()
                 in {"true", "yes", "1", "x"}
                 or normalize_currency(ctx.appraisal.value("income_approach_monthly_rent")))
    ev = [ctx.appraisal.evidence("is_income_approach_used"),
          ctx.appraisal.evidence("income_approach_monthly_rent")]
    if developed:
        return _res("MF-1", "95", "income_approach", RuleStatus.PASS,
                    fields=["is_income_approach_used"], evidence=ev)
    return _res("MF-1", "95", "income_approach", RuleStatus.VERIFY,
                message=qc_config.template("MF-1-income"),
                fields=["is_income_approach_used", "income_approach_monthly_rent"],
                template_id="MF-1-income", evidence=ev, confidence=0.7)


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
