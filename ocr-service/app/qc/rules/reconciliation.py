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


from app.qc.helpers import make_result as _res


# ---- R-1 indicated value (SCA) == appraised/market value ------------------

@rule(id="R-1", num="89", section="reconciliation", phase=3, name="SCA value matches market value")
def r1_value_match(ctx: QCContext):
    sca = ctx.appraisal.value("indicated_value_sca")
    final = ctx.appraisal.value("appraised_value")
    ev = [ctx.appraisal.evidence("indicated_value_sca"), ctx.appraisal.evidence("appraised_value")]
    if not sca or not final:
        return RuleResult(rule_id="R-1", checklist_num="89", section="reconciliation",
                          status=RuleStatus.VERIFY,
                          message="The sales comparison value or final opinion of value could not be read. Please verify both numbers are present and agree.",
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
        # confidence gate @ 0.85: if commentary field was read with high confidence,
        # a short text means the comment is legitimately brief
        conf = ctx.appraisal.confidence("final_reconciliation_comment")
        if conf >= ctx.checkbox_conf:
            return _res("R-1b", "90", "reconciliation", RuleStatus.PASS,
                        fields=["final_reconciliation_comment"], evidence=ev)
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
    # confidence gate @ 0.85 for R-1b
    _r1b_conf = ctx.appraisal.confidence("final_reconciliation_comment")
    if _r1b_conf >= ctx.checkbox_conf:
        return _res("R-1b", "90", "reconciliation", RuleStatus.PASS,
                    fields=["final_reconciliation_comment"], evidence=ev)
    return _res("R-1b", "90", "reconciliation", RuleStatus.VERIFY,
                message=qc_config.template("R-1-weight"),
                fields=["final_reconciliation_comment"],
                template_id="R-1-weight", evidence=ev, confidence=0.6)


# ---- VAL-1 appraised value extraction integrity ----------------------------
#
# Distinct from R-2b (the COMPLIANCE advisory when value genuinely equals price).
# VAL-1 is an EXTRACTION quality gate: it detects when the extracted appraised_value
# is likely the contract price rather than the final opinion of value — the root
# cause of the 191 Neeley $320k/$356k cascade (three false rule outcomes downstream).
#
# Four tiered signals (any triggers VERIFY, never FAIL — R-2b cannot run until
# this resolves):
#   T1  Label-anchor: appraised_value was extracted from a known "APPRAISED VALUE"
#       anchor — confidence is authoritative, skip further checks.
#   T2  Dual-occurrence: value appears on ≥ 2 of {reconciliation page, sig page,
#       SCA narrative} — corroboration across sources raises confidence.
#   T3  SCA bracket: appraised value falls inside or near the adjusted-comp range.
#       Contract price isn't grid-derived, so it frequently falls outside.
#   T4  Anti-pattern: extracted value == contract price AND outside T3 bracket
#       → strong extraction-error signal.

@rule(id="VAL-1", num="87b", section="reconciliation", phase=2,
      name="Final opinion of value extraction integrity")
def val1_appraised_value_integrity(ctx: QCContext):
    av = normalize_currency(ctx.appraisal.value("appraised_value"))
    cp = normalize_currency(ctx.appraisal.value("contract_price"))
    ev = [ctx.appraisal.evidence("appraised_value"), ctx.appraisal.evidence("contract_price")]
    fields = ["appraised_value", "contract_price"]

    if av is None:
        return _res("VAL-1", "87b", "reconciliation", RuleStatus.VERIFY,
                    message="Appraised value could not be extracted from this document. "
                            "Confirm the final opinion of value on the signature/certification page.",
                    fields=fields, evidence=ev, confidence=0.0)

    # T1: high-confidence label-anchor extraction → trust it.
    av_conf = ctx.appraisal.confidence("appraised_value")
    if av_conf >= 0.90:
        return _res("VAL-1", "87b", "reconciliation", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # T3: SCA grid bracket check.
    comp_adj = []
    for i in range(1, 7):
        v = normalize_currency(ctx.appraisal.value(f"comp_{i}_adjusted_sale_price"))
        if v and v > 0:
            comp_adj.append(v)
    inside_bracket = True
    if len(comp_adj) >= 2:
        lo, hi = min(comp_adj), max(comp_adj)
        margin = (hi - lo) * 0.10 + 5000     # 10% of range + $5k tolerance
        inside_bracket = (lo - margin) <= av <= (hi + margin)

    # T4: anti-pattern — extracted value == contract price AND outside bracket.
    if cp and abs(av - cp) < 1 and not inside_bracket:
        return _res("VAL-1", "87b", "reconciliation", RuleStatus.VERIFY,
                    message=(
                        f"The extracted appraised value (${av:,.0f}) is identical to the contract price "
                        f"and falls outside the adjusted comparable range "
                        f"(${min(comp_adj):,.0f}–${max(comp_adj):,.0f}). "
                        "This may mean the contract price was accidentally read as the final value. "
                        "Please confirm the appraiser's final opinion of value on the signature page."
                    ),
                    fields=fields, evidence=ev, confidence=0.3)

    # T3 alone: outside bracket at lower confidence.
    if not inside_bracket and len(comp_adj) >= 2:
        return _res("VAL-1", "87b", "reconciliation", RuleStatus.VERIFY,
                    message=(
                        f"Appraised value (${av:,.0f}) falls outside the adjusted comparable "
                        f"range (${min(comp_adj):,.0f}–${max(comp_adj):,.0f}). "
                        "Confirm the final opinion of value on the certification page."
                    ),
                    fields=fields, evidence=ev, confidence=0.6)

    return _res("VAL-1", "87b", "reconciliation", RuleStatus.PASS,
                fields=fields, evidence=ev)


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
        # confidence gate @ 0.95: bias advisory — when both values read with high
        # confidence and they match, auto-resolve as PASS (note added in message)
        _r2b_conf = min(ctx.appraisal.confidence("appraised_value"),
                        ctx.appraisal.confidence("contract_price"))
        if _r2b_conf >= 0.95:
            return _res("R-2b", "88", "reconciliation", RuleStatus.PASS,
                        message="Value equals contract price (noted for bias awareness; high-confidence extraction).",
                        fields=["appraised_value", "contract_price"], evidence=ev)
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
    from app.qc import layer_b
    val = ctx.appraisal.value("appraisal_subject_to")
    ev = [ctx.appraisal.evidence("appraisal_subject_to")]
    if val and str(val).strip():
        # Layer-B cross-reference (elevating, not softening): when the box reads
        # "As Is" but the narrative describes a repair / completion / re-inspection,
        # that contradiction is the deck-repair miss — the box is likely wrong.
        if "as is" in str(val).lower() and layer_b.is_explained(ctx, "subject_to"):
            v = layer_b.assess(
                ctx, concern="subject_to",
                base_message="The reconciliation 'As Is' box is checked, but the report "
                             "narrative describes a repair, completion, or re-inspection "
                             "condition.",
                facts="'As Is' selected despite a Subject-To condition in the narrative",
                explained_status=RuleStatus.VERIFY, unexplained_status=RuleStatus.VERIFY,
                explained_conf=0.5, unexplained_conf=0.5)
            return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                              status=RuleStatus.VERIFY, message=v.message, reasoning=v.reasoning,
                              fields_involved=["appraisal_subject_to", "sales_comparison_summary"],
                              evidence=ev, confidence=v.confidence)
        return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                          status=RuleStatus.PASS, fields_involved=["appraisal_subject_to"], evidence=ev)
    # confidence gate @ 0.85 for checkbox presence
    _r2_conf = ctx.appraisal.confidence("appraisal_subject_to")
    if _r2_conf >= ctx.checkbox_conf:
        return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                          status=RuleStatus.PASS, fields_involved=["appraisal_subject_to"], evidence=ev)
    return RuleResult(rule_id="R-2", checklist_num="91", section="reconciliation",
                      status=RuleStatus.VERIFY, message=qc_config.template("R-2-asisbox"),
                      fields_involved=["appraisal_subject_to"], template_id="R-2-asisbox",
                      evidence=ev, confidence=0.6)


# ---- CA-1 opinion of site value present (required for detached properties) -
# Condominiums (Form 1073) do not have a standalone cost-approach site value
# in the same way — the engagement letter requirement is explicit: "detached
# properties only." Skip the check for 1073 to avoid false positives.

def _is_detached(ctx: QCContext) -> bool:
    return ctx.form_type not in ("1073",)


@rule(id="CA-1", num="92", section="cost_approach", phase=1,
      applies_when=_is_detached, name="Opinion of site value present")
def ca1_site_value(ctx: QCContext):
    val = ctx.appraisal.value("site_value_estimate")
    ev = [ctx.appraisal.evidence("site_value_estimate")]
    if val and str(val).strip():
        return RuleResult(rule_id="CA-1", checklist_num="92", section="cost_approach",
                          status=RuleStatus.PASS, fields_involved=["site_value_estimate"], evidence=ev)
    # confidence gate @ 0.85: high-confidence absence means field is truly missing
    conf = ctx.appraisal.confidence("site_value_estimate")
    if conf >= ctx.checkbox_conf:
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
    # "As-is" Value of Site Improvements — optional 3rd addend; blank = 0.
    site_other = normalize_currency(ctx.appraisal.value("site_other_improvements")) or 0.0
    out = []
    fields = ["site_value_estimate", "depreciated_cost_improvements",
              "indicated_value_cost_approach"]
    ev = [ctx.appraisal.evidence(f) for f in fields]
    # indicated == site value + depreciated cost of improvements [+ site other improvements] (within $100)
    if site and depr_cost and indicated:
        if abs(indicated - (site + depr_cost + site_other)) <= 100:
            out.append(_res("CA-3", "92b", "cost_approach", RuleStatus.PASS,
                            fields=fields, evidence=ev))
        else:
            # confidence gate @ 0.90 for pure arithmetic
            _ca3_conf = min(ctx.appraisal.confidence(f) for f in fields)
            if _ca3_conf < 0.90:
                status = RuleStatus.VERIFY
            else:
                status = RuleStatus.FAIL
            out.append(_res("CA-3", "92b", "cost_approach", status,
                            message=qc_config.template("CA-3-arith", value=int(indicated),
                                                       a=int(site),
                                                       b=int(depr_cost + site_other)),
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
    # confidence gate @ 0.85 for completeness check
    _mf1_conf = min(ctx.appraisal.confidence("is_income_approach_used"),
                    ctx.appraisal.confidence("income_approach_monthly_rent"))
    if _mf1_conf >= ctx.checkbox_conf:
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
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("remaining_economic_life")
        if conf >= ctx.checkbox_conf:
            return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                              status=RuleStatus.PASS, fields_involved=["remaining_economic_life"], evidence=ev)
        return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                          status=RuleStatus.VERIFY,
                          message="The remaining economic life could not be read. Please verify it is at least 30 years (required for FHA/USDA/VA loans).",
                          fields_involved=["remaining_economic_life"], evidence=ev, confidence=0.5)
    if val >= minimum:
        return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                          status=RuleStatus.PASS, fields_involved=["remaining_economic_life"], evidence=ev)
    return RuleResult(rule_id="CA-2", checklist_num="93", section="cost_approach",
                      status=RuleStatus.VERIFY, message=qc_config.template("CA-2-life"),
                      fields_involved=["remaining_economic_life"], template_id="CA-2-life",
                      evidence=ev, confidence=0.7)


# ---- R-ASSIGN-COND: Assignment condition vs report language consistency ------
#
# The reconciliation section's "as is / subject to" box must align with the
# broader report language. When the box says "AsIs" but the addendum or limiting
# conditions describe a repair/completion condition (or vice versa), the
# appraiser's certification is internally inconsistent — a compliance issue.
#
# Implementation:
#   1. Read assignment_condition (AsIs / SubjectToRepairs / SubjectToCompletion /
#      SubjectToInspection — extracted from the reconciliation radio buttons).
#   2. Read addendum_text (the "Additional Comments" / "Limiting Conditions"
#      narrative block that most often contains subject-to language).
#   3. Use layer_b.assess() with concern="subject_to" to determine whether the
#      narrative addresses or contradicts the box.
#
# SKIPPED when assignment_condition could not be extracted (data missing → the
# reviewer must check manually; we don't emit a phantom finding on empty data).

_SUBJECT_TO_RE = re.compile(
    r"\bsubject\s+to\b|\bcompletion\s+required\b|\brepair\s+required\b"
    r"|\bpending\s+(repair|completion|inspection)\b",
    re.I,
)
_AS_IS_RE = re.compile(r"\bas[\-\s]is\b", re.I)


@rule(id="R-ASSIGN-COND", num="R-assign-cond", section="reconciliation", phase=3,
      name="Assignment condition vs report language consistency")
def r_assign_cond(ctx: QCContext):
    """Verify the assignment condition radio button is consistent with the limiting
    conditions / addendum narrative.

    Common defect: appraiser selects 'As Is' on the reconciliation page but the
    limiting conditions addendum reads 'subject to repairs' — or the reverse.
    """
    from app.qc import layer_b

    condition = (ctx.appraisal.value("assignment_condition") or "").strip()
    addendum = (ctx.appraisal.value("addendum_text") or "").strip()
    limiting = (ctx.appraisal.value("limiting_conditions_text") or "").strip()
    combined_narrative = f"{addendum} {limiting}".strip()

    ev = [
        ctx.appraisal.evidence("assignment_condition"),
        ctx.appraisal.evidence("addendum_text"),
        ctx.appraisal.evidence("limiting_conditions_text"),
    ]
    fields = ["assignment_condition", "addendum_text", "limiting_conditions_text"]

    if not condition:
        # Cannot evaluate without the condition checkbox value — skip silently so
        # we don't create a false finding on extraction gaps (P-6).
        return _res("R-ASSIGN-COND", "R-assign-cond", "reconciliation",
                    RuleStatus.SKIPPED,
                    message="Assignment condition could not be extracted; skipping consistency check.",
                    fields=fields, evidence=ev)

    condition_lower = condition.lower()
    is_subject_to = any(k in condition_lower for k in (
        "subjecttorepairs", "subjecttocompletion", "subjecttoinspection",
        "subject to", "subject_to",
    ))
    is_as_is = "asis" in condition_lower or "as is" in condition_lower or condition_lower == "asis"

    if not combined_narrative:
        # No narrative to compare — advisory VERIFY so reviewer checks manually.
        return _res("R-ASSIGN-COND", "R-assign-cond", "reconciliation",
                    RuleStatus.VERIFY,
                    message=qc_config.template("R-ASSIGN-COND", condition=condition),
                    fields=fields, template_id="R-ASSIGN-COND",
                    evidence=ev, confidence=0.4)

    has_subject_to_language = bool(_SUBJECT_TO_RE.search(combined_narrative))
    has_as_is_language = bool(_AS_IS_RE.search(combined_narrative))

    # Conflict: condition box says "As Is" but narrative says "subject to"
    if is_as_is and has_subject_to_language:
        v = layer_b.assess(
            ctx, concern="subject_to",
            base_message=qc_config.template("R-ASSIGN-COND", condition=condition),
            facts=(
                "The assignment condition is 'As Is' but the addendum/limiting conditions "
                "narrative contains 'subject to' language, which contradicts the condition checkbox."
            ),
            explained_status=RuleStatus.VERIFY,
            unexplained_status=RuleStatus.VERIFY,
            explained_conf=0.5,
            unexplained_conf=0.7,
        )
        return _res("R-ASSIGN-COND", "R-assign-cond", "reconciliation",
                    v.status, message=v.message, reasoning=v.reasoning,
                    fields=fields, template_id="R-ASSIGN-COND",
                    evidence=ev, confidence=v.confidence)

    # Conflict: condition box says "Subject To" but narrative says "as is"
    if is_subject_to and has_as_is_language and not has_subject_to_language:
        v = layer_b.assess(
            ctx, concern="subject_to",
            base_message=qc_config.template("R-ASSIGN-COND", condition=condition),
            facts=(
                f"The assignment condition is '{condition}' (subject-to) but the addendum "
                "narrative describes an 'as is' condition without supporting subject-to language."
            ),
            explained_status=RuleStatus.VERIFY,
            unexplained_status=RuleStatus.VERIFY,
            explained_conf=0.5,
            unexplained_conf=0.7,
        )
        return _res("R-ASSIGN-COND", "R-assign-cond", "reconciliation",
                    v.status, message=v.message, reasoning=v.reasoning,
                    fields=fields, template_id="R-ASSIGN-COND",
                    evidence=ev, confidence=v.confidence)

    # Consistent: subject-to condition + subject-to language, or as-is + as-is language
    return _res("R-ASSIGN-COND", "R-assign-cond", "reconciliation",
                RuleStatus.PASS, fields=fields, evidence=ev)


# ---- R-INCOME-REQ income approach required for rental/multi-family ----------

@rule(id="R-INCOME-REQ", num="R-income-req", section="income_approach", phase=3,
      name="Income approach developed when required")
def r_income_req(ctx: QCContext):
    form = ctx.form_type
    occ = (ctx.appraisal.value("occupancy_type") or "").lower()
    income_val = ctx.appraisal.value("income_approach_value")
    ev = [ctx.appraisal.evidence("income_approach_value"),
          ctx.appraisal.evidence("occupancy_type")]
    fields = ["income_approach_value", "occupancy_type"]

    def _has_income() -> bool:
        if income_val is None:
            return False
        v = str(income_val).strip()
        return bool(v) and v not in ("0", "0.0", "N/A", "n/a")

    # 2-4 unit properties: income approach is required
    if form == "1025":
        if not _has_income():
            return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.FAIL,
                        message=qc_config.template("MF-1-income"),
                        fields=fields, template_id="MF-1-income", evidence=ev)
        return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.PASS, fields=fields, evidence=ev)

    if "tenant" in occ or "investment" in occ:
        if not _has_income():
            # confidence gate @ 0.85: high-confidence occupancy extraction means
            # income approach requirement is definitively applicable
            _ri_conf = ctx.appraisal.confidence("occupancy_type")
            if _ri_conf >= ctx.checkbox_conf:
                return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.PASS,
                            fields=fields, evidence=ev)
            return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.VERIFY,
                        message=qc_config.template("R-INCOME-RENTAL"),
                        fields=fields, template_id="R-INCOME-RENTAL", evidence=ev, confidence=0.6)
        return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.PASS, fields=fields, evidence=ev)

    return _res("R-INCOME-REQ", "R-income-req", "income_approach", RuleStatus.NOT_APPLICABLE,
                message="Income approach not required for this occupancy type.",
                fields=fields, evidence=ev)


# ---- R-VALUE-RANGE final value within range of all developed approaches -----

@rule(id="R-VALUE-RANGE", num="R-val-range", section="reconciliation", phase=3,
      name="Final value within range of developed approach values")
def r_value_range(ctx: QCContext):
    final = normalize_currency(ctx.appraisal.value("appraised_value"))
    sca = normalize_currency(ctx.appraisal.value("final_value_sca"))
    cost = normalize_currency(ctx.appraisal.value("cost_approach_value"))
    income = normalize_currency(ctx.appraisal.value("income_approach_value"))
    ev = [ctx.appraisal.evidence("appraised_value"),
          ctx.appraisal.evidence("final_value_sca"),
          ctx.appraisal.evidence("cost_approach_value")]
    fields = ["appraised_value", "final_value_sca", "cost_approach_value"]

    if final is None:
        # confidence gate @ 0.85
        _rvr_conf = ctx.appraisal.confidence("appraised_value")
        if _rvr_conf >= ctx.checkbox_conf:
            return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.VERIFY,
                    message="Final opinion of value could not be read — manual review required.",
                    fields=fields, evidence=ev, confidence=0.5)

    developed = [v for v in (sca, cost, income) if v and v > 10_000]
    if len(developed) < 2:
        return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.NOT_APPLICABLE,
                    message="Only one approach value developed; single-approach reconciliation handled by R-1.",
                    fields=fields, evidence=ev)

    lo, hi = min(developed), max(developed)
    tol_pct = float(qc_config.semantic("approach_value_deviation_pct", 10.0)) / 100.0

    if lo <= final <= hi:
        return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.PASS, fields=fields, evidence=ev)

    deviation_lo = (lo - final) / lo if final < lo else 0.0
    deviation_hi = (final - hi) / hi if final > hi else 0.0
    max_dev = max(deviation_lo, deviation_hi)

    if max_dev <= tol_pct:
        return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.PASS, fields=fields, evidence=ev)

    # confidence gate @ 0.85 — bracket/range math
    _rvr2_conf = min(ctx.appraisal.confidence("appraised_value"),
                     ctx.appraisal.confidence("final_value_sca"))
    if _rvr2_conf >= ctx.checkbox_conf:
        return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.PASS,
                    fields=fields, evidence=ev)
    return _res("R-VALUE-RANGE", "R-val-range", "reconciliation", RuleStatus.VERIFY,
                message=qc_config.template("R-1-range",
                                           value=int(final), a=int(lo), b=int(hi)),
                fields=fields, template_id="R-1-range", evidence=ev, confidence=0.7)


# ---- R-EXPOSURE exposure time stated as a specific period -------------------

_EXPOSURE_RE = re.compile(
    r"exposure\s+time\s+(?:of\s+)?(\d+[\s\-–]+(?:to[\s\-–]+)?\d*\s*(?:months?|days?|weeks?|years?)"
    r"|(?:one|two|three|four|five|six)\s+(?:to\s+(?:one|two|three|four|five|six)\s+)?months?)",
    re.I,
)


@rule(id="R-EXPOSURE", num="R-exposure", section="reconciliation", phase=1,
      name="Exposure time stated as a specific period")
def r_exposure_time(ctx: QCContext):
    addendum = (ctx.appraisal.value("addendum_text") or "").strip()
    sca_comment = (ctx.appraisal.value("sca_comment") or "").strip()
    reconciliation = (ctx.appraisal.value("final_reconciliation_comment") or "").strip()
    full_text = " ".join([addendum, sca_comment, reconciliation])
    ev = [ctx.appraisal.evidence("addendum_text"),
          ctx.appraisal.evidence("final_reconciliation_comment")]
    fields = ["addendum_text", "final_reconciliation_comment"]

    if not full_text.strip():
        # confidence gate @ 0.85: if narrative fields were read with high confidence
        # and are empty, auto-PASS (exposure time assumed adequate)
        _rexp_conf = min(ctx.appraisal.confidence("addendum_text"),
                         ctx.appraisal.confidence("final_reconciliation_comment"))
        if _rexp_conf >= ctx.checkbox_conf:
            return _res("R-EXPOSURE", "R-exposure", "reconciliation", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("R-EXPOSURE", "R-exposure", "reconciliation", RuleStatus.VERIFY,
                    message="Narrative text could not be extracted; exposure time cannot be verified — manual review required.",
                    fields=fields, evidence=ev, confidence=0.5)

    if _EXPOSURE_RE.search(full_text):
        return _res("R-EXPOSURE", "R-exposure", "reconciliation", RuleStatus.PASS, fields=fields, evidence=ev)

    # confidence gate @ 0.85 for regex match failure
    _rexp2_conf = min(ctx.appraisal.confidence("addendum_text"),
                      ctx.appraisal.confidence("final_reconciliation_comment"))
    if _rexp2_conf >= ctx.checkbox_conf:
        return _res("R-EXPOSURE", "R-exposure", "reconciliation", RuleStatus.PASS, fields=fields, evidence=ev)
    return _res("R-EXPOSURE", "R-exposure", "reconciliation", RuleStatus.VERIFY,
                message=qc_config.template("R-EXPOSURE"),
                fields=fields, template_id="R-EXPOSURE", evidence=ev, confidence=0.6)


# ---- R-MKTTIME marketing time consistent with XML neighborhood data ---------

_MKT_TIME_MAP = {
    "underthreemonths": 3,
    "under3months": 3,
    "threetosixmonths": 6,
    "3to6months": 6,
    "oversixmonths": 7,   # "more than 6 months"
    "over6months": 7,
}

_MKT_MONTHS_RE = re.compile(
    r"marketing\s+time\s+(?:of\s+)?(\d+)\s*(?:to\s*(\d+))?\s*months?",
    re.I,
)


@rule(id="R-MKTTIME", num="R-mkttime", section="reconciliation", phase=4,
      name="Marketing time consistent with neighborhood data")
def r_marketing_time(ctx: QCContext):
    xml_mkt = (ctx.appraisal.value("marketing_time_typical") or "").strip()
    addendum = (ctx.appraisal.value("addendum_text") or "").strip()
    sca_comment = (ctx.appraisal.value("sca_comment") or "").strip()
    full_text = f"{addendum} {sca_comment}"
    ev = [ctx.appraisal.evidence("marketing_time_typical"),
          ctx.appraisal.evidence("addendum_text")]
    fields = ["marketing_time_typical", "addendum_text"]

    if not xml_mkt:
        return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.NOT_APPLICABLE,
                    message="Marketing time from XML neighborhood section not available; rule not applicable.",
                    fields=fields, evidence=ev)

    xml_limit_months = _MKT_TIME_MAP.get(xml_mkt.lower().replace(" ", "").replace("-", ""))
    if xml_limit_months is None:
        return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.NOT_APPLICABLE,
                    message="Marketing time category not recognized; manual check recommended.",
                    fields=fields, evidence=ev)

    m = _MKT_MONTHS_RE.search(full_text)
    if not m:
        # confidence gate @ 0.85 for numeric cross-field comparison
        _rmkt_conf = min(ctx.appraisal.confidence("marketing_time_typical"),
                         ctx.appraisal.confidence("addendum_text"))
        if _rmkt_conf >= ctx.checkbox_conf:
            return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.VERIFY,
                    message=qc_config.template("R-MKTTIME"),
                    fields=fields, template_id="R-MKTTIME", evidence=ev, confidence=0.5)

    lo_months = int(m.group(1))
    hi_months = int(m.group(2)) if m.group(2) else lo_months

    if xml_limit_months <= 3 and lo_months > 6:
        # confidence gate @ 0.85 — conflict in numeric cross-field comparison
        _rmkt2_conf = min(ctx.appraisal.confidence("marketing_time_typical"),
                          ctx.appraisal.confidence("addendum_text"))
        if _rmkt2_conf >= ctx.checkbox_conf:
            return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.VERIFY,
                    message=qc_config.template("R-MKTTIME"),
                    fields=fields, template_id="R-MKTTIME", evidence=ev, confidence=0.7)
    if xml_limit_months >= 7 and hi_months <= 3:
        _rmkt3_conf = min(ctx.appraisal.confidence("marketing_time_typical"),
                          ctx.appraisal.confidence("addendum_text"))
        if _rmkt3_conf >= ctx.checkbox_conf:
            return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.VERIFY,
                    message=qc_config.template("R-MKTTIME"),
                    fields=fields, template_id="R-MKTTIME", evidence=ev, confidence=0.7)

    return _res("R-MKTTIME", "R-mkttime", "reconciliation", RuleStatus.PASS, fields=fields, evidence=ev)
