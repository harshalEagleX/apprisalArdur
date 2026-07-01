"""
Arithmetic / timeline / consistency rules (phase 1-5).

Rules in this module are deterministic — no LLM calls are made except where
layer_b.assess() is invoked for keyword-based narrative lookup (never LLM-driven
pass/fail decisions).

CA-ARITH     Cost approach arithmetic cross-check
SCA-GROSS    Gross adjustment per comp > 25%
I-AGE        Effective age must not exceed actual age
I-YRBUILT    Year built consistency with actual age
TL-ENG       Engagement letter date precedes report date
TL-CONTRACT  Contract date precedes appraisal effective date
C-ANALYZE    Did-analyze-contract consistency
LISTING-CMNT Listed price vs appraised value without commentary
"""

from __future__ import annotations

import datetime as _dt
import re

from app.qc import helpers as H
from app.qc import layer_b
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_date(s):
    """Parse a date string in common appraisal formats; returns a date or None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(val) -> "float | None":
    """Strip currency formatting and return a float, or None if unparseable."""
    if val is None:
        return None
    s = re.sub(r"[$,\s]", "", str(val))
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _extract_listing_price(listing_history: str) -> "float | None":
    """
    Extract the most recent listing price from the listing history text.
    Looks for patterns like:
      "Latest Price $1,250,000"  /  "Price $1,250,000"  /  "$1,250,000"
    Returns the first dollar-amount found after a price-related keyword, or the
    largest stand-alone dollar amount in the text if no keyword is found.
    """
    if not listing_history:
        return None
    text = str(listing_history)

    # Priority: explicit "Latest Price" / "List Price" / "Price" tag
    m = re.search(
        r"(?:latest\s+price|list(?:ing)?\s+price|price)\s*[:=]?\s*\$?([\d,]+)",
        text, re.I)
    if m:
        return _to_float(m.group(1))

    # Fall back: any dollar amount in the text
    amounts = [_to_float(v) for v in re.findall(r"\$[\d,]+", text)]
    amounts = [a for a in amounts if a is not None and a > 0]
    return max(amounts) if amounts else None


# ---------------------------------------------------------------------------
# Section-bound result builders
# ---------------------------------------------------------------------------

_res_recon = H.section_result("reconciliation")
_res_sca = H.section_result("sales_comparison")
_res_imp = H.section_result("improvements")
_res_sig = H.section_result("signature")
_res_con = H.section_result("contract")
_res_sub = H.section_result("subject")


# ===========================================================================
# CA-ARITH — Cost approach arithmetic cross-check
# ===========================================================================

@rule(id="CA-ARITH", num="CA-arith", section="reconciliation", phase=3,
      name="Cost approach arithmetic cross-check")
def ca_arith_cost_approach(ctx: QCContext):
    """
    site_value + (total_improvements_cost - total_depreciation) ≈ cost_approach_value
    Tolerance is read from qc_config.semantic("cost_approach_arith_tolerance", 50).
    """
    site_val_raw = ctx.appraisal.value("site_value")
    improvements_raw = ctx.appraisal.value("total_improvements_cost")
    depreciation_raw = ctx.appraisal.value("total_depreciation")
    stated_raw = ctx.appraisal.value("cost_approach_value")
    # "As-is" Value of Site Improvements — optional 3rd addend on the URAR cost approach.
    # New construction or properties with site improvements use this line; blank = 0.
    site_other_raw = ctx.appraisal.value("site_other_improvements")

    ev = [
        ctx.appraisal.evidence("site_value"),
        ctx.appraisal.evidence("total_improvements_cost"),
        ctx.appraisal.evidence("total_depreciation"),
        ctx.appraisal.evidence("cost_approach_value"),
    ]

    site_val = _to_float(site_val_raw)
    improvements = _to_float(improvements_raw)
    depreciation = _to_float(depreciation_raw)
    stated_val = _to_float(stated_raw)
    site_other = _to_float(site_other_raw) or 0.0  # blank → 0 (most reports omit this line)

    if any(v is None for v in (site_val, improvements, depreciation, stated_val)):
        missing = [
            name for name, v in (
                ("site_value", site_val),
                ("total_improvements_cost", improvements),
                ("total_depreciation", depreciation),
                ("cost_approach_value", stated_val),
            ) if v is None
        ]
        return _res_recon(
            "CA-ARITH", "CA-arith", RuleStatus.SKIPPED,
            message=(
                f"Cost approach arithmetic cannot be evaluated; the following field(s) "
                f"could not be extracted: {', '.join(missing)}."
            ),
            fields=["site_value", "total_improvements_cost",
                    "total_depreciation", "cost_approach_value"],
            evidence=ev,
        )

    tolerance = float(qc_config.semantic("cost_approach_arith_tolerance", 50))
    depr_improvements = improvements - depreciation
    computed = site_val + depr_improvements + site_other
    diff = abs(computed - stated_val)

    if diff <= tolerance:
        return _res_recon(
            "CA-ARITH", "CA-arith", RuleStatus.PASS,
            fields=["site_value", "total_improvements_cost",
                    "total_depreciation", "cost_approach_value"],
            evidence=ev,
        )

    # Low-confidence extraction → downgrade FAIL to VERIFY
    min_conf = min(
        ctx.appraisal.confidence("site_value"),
        ctx.appraisal.confidence("total_improvements_cost"),
        ctx.appraisal.confidence("total_depreciation"),
        ctx.appraisal.confidence("cost_approach_value"),
    )
    status = RuleStatus.FAIL
    confidence = 1.0
    if min_conf < ctx.structured_conf:
        status = RuleStatus.VERIFY
        confidence = min_conf

    msg = qc_config.template(
        "CA-3-arith",
        value=int(stated_val),
        a=int(site_val),
        b=int(depr_improvements),
    )
    return _res_recon(
        "CA-ARITH", "CA-arith", status,
        message=msg,
        fields=["site_value", "total_improvements_cost",
                "total_depreciation", "cost_approach_value"],
        evidence=ev,
        template_id="CA-3-arith",
        confidence=confidence,
    )


# ===========================================================================
# SCA-GROSS — Gross adjustment per comp > 25%
# ===========================================================================

def _has_sca(ctx: QCContext) -> bool:
    return ctx.has_sca_grid


@rule(id="SCA-GROSS", num="SCA-gross", section="sales_comparison", phase=3,
      applies_when=_has_sca,
      name="Gross adjustment per comp within 25%")
def sca_gross_per_comp(ctx: QCContext):
    """
    Checks each of comps 1..9 for gross_adj_pct, fusing XML (MISMO, conf=0.97)
    and PDF OCR sources. The DocView already holds the highest-confidence value
    per field (XML wins when available), so we read directly from the appraisal
    DocView and note the extraction method in each Evidence for reviewer audit.

    When both XML and PDF extracted a value for the same comp, the merged result
    carries the XML confidence. We also add a cross-check note when method is
    xml_parser to make provenance visible in the finding.
    """
    # PolicyProfile.adjustment_commentary_gross_pct = from amc_policies.yaml (EL body says 25%)
    # This is a commentary TRIGGER (EL says "explain the rationale") — not an auto-fail limit.
    cap = (ctx.policy.adjustment_commentary_gross_pct
           or float(qc_config.semantic("gross_adjustment_pct", 25.0)))

    violations = []   # list of (comp_num, pct, method, confidence)
    seen = []

    for i in range(1, 10):
        raw = ctx.appraisal.value(f"comp_{i}_gross_adj_pct")
        if raw is None:
            continue
        pct_m = re.search(r"[\d.]+", str(raw).replace(",", ""))
        if pct_m is None:
            continue
        pct = float(pct_m.group(0))
        r = ctx.appraisal.result(f"comp_{i}_gross_adj_pct")
        method = r.extraction_method if r else "pdf_ocr"
        conf = r.effective_confidence if r else 0.8
        seen.append(i)
        if pct > cap:
            violations.append((i, pct, method, conf))

    # Collect evidence with method tags so reviewer sees both source indicators
    ev = [ctx.appraisal.evidence(f"comp_{i}_gross_adj_pct")
          for i in (seen[:6] if seen else [1, 2, 3])]

    if not seen:
        return _res_sca(
            "SCA-GROSS", "SCA-gross", RuleStatus.VERIFY,
            message=(
                "Gross adjustment percentages could not be read from the grid "
                "(neither XML nor PDF extraction returned values); "
                "please verify the comparable gross adjustments are within 25%."
            ),
            fields=["comp_N_gross_adj_pct"],
            evidence=ev,
            confidence=0.5,
        )

    if not violations:
        return _res_sca(
            "SCA-GROSS", "SCA-gross", RuleStatus.PASS,
            fields=["comp_N_gross_adj_pct"],
            evidence=ev,
        )

    comps_str = ", ".join(str(c) for c, _, _, _ in violations)
    details = "; ".join(
        f"Comp {c}: {p:.1f}% [via {m}]"
        for c, p, m, _ in violations
    )
    # Use minimum confidence across violations (weakest evidence drives severity)
    min_conf = min(cf for _, _, _, cf in violations)
    base_msg = qc_config.template("SCA-gross25", value=comps_str)

    v = layer_b.assess(
        ctx,
        concern="large_adjustment",
        base_message=base_msg,
        facts=details,
    )
    # Raise confidence when XML confirmed the violation (high certainty)
    final_conf = max(v.confidence, min_conf * 0.9) if min_conf >= 0.95 else v.confidence
    return _res_sca(
        "SCA-GROSS", "SCA-gross", v.status,
        message=v.message,
        fields=["comp_N_gross_adj_pct"],
        evidence=ev,
        template_id="SCA-gross25",
        confidence=final_conf,
        reasoning=v.reasoning,
    )


# ===========================================================================
# I-AGE — Effective age must not exceed actual age
# ===========================================================================

@rule(id="I-AGE", num="I-age", section="improvements", phase=1,
      name="Effective age does not exceed actual age")
def i_age_effective_vs_actual(ctx: QCContext):
    """
    actual_age = effective_date.year - year_built
    Rule: effective_age <= actual_age
    """
    eff_age_raw = ctx.appraisal.value("effective_age")
    year_built_raw = ctx.appraisal.value("year_built")
    eff_date_raw = ctx.appraisal.value("effective_date")

    ev = [
        ctx.appraisal.evidence("effective_age"),
        ctx.appraisal.evidence("year_built"),
        ctx.appraisal.evidence("effective_date"),
    ]

    eff_age = _to_float(eff_age_raw)
    year_built = _to_float(year_built_raw)
    eff_date = _parse_date(eff_date_raw)

    if eff_age is None or year_built is None or eff_date is None:
        missing = [
            name for name, v in (
                ("effective_age", eff_age),
                ("year_built", year_built),
                ("effective_date", eff_date),
            ) if v is None
        ]
        return _res_imp(
            "I-AGE", "I-age", RuleStatus.SKIPPED,
            message=(
                f"Effective age check cannot be evaluated; the following field(s) "
                f"could not be extracted: {', '.join(missing)}."
            ),
            fields=["effective_age", "year_built", "effective_date"],
            evidence=ev,
        )

    actual_age = eff_date.year - int(year_built)
    eff_age_int = int(eff_age)

    if eff_age_int <= actual_age:
        return _res_imp(
            "I-AGE", "I-age", RuleStatus.PASS,
            fields=["effective_age", "year_built", "effective_date"],
            evidence=ev,
        )

    # Confidence gate: low extraction confidence → downgrade FAIL to VERIFY
    min_conf = min(
        ctx.appraisal.confidence("effective_age"),
        ctx.appraisal.confidence("year_built"),
        ctx.appraisal.confidence("effective_date"),
    )
    status = RuleStatus.FAIL
    confidence = 1.0
    if min_conf < ctx.structured_conf:
        status = RuleStatus.VERIFY
        confidence = min_conf

    msg = qc_config.template("I-1-age", a=eff_age_int, b=actual_age)
    return _res_imp(
        "I-AGE", "I-age", status,
        message=msg,
        fields=["effective_age", "year_built", "effective_date"],
        evidence=ev,
        template_id="I-1-age",
        confidence=confidence,
    )


# ===========================================================================
# I-YRBUILT — Year built consistency with actual age
# ===========================================================================

@rule(id="I-YRBUILT", num="I-yrbuilt", section="improvements", phase=1,
      name="Year built consistent with actual age")
def i_yrbuilt_consistency(ctx: QCContext):
    """
    calculated_age = effective_date.year - year_built
    If stated actual_age differs from calculated_age by > tolerance → VERIFY.
    Also checks that year_built is in the plausible range 1800-2030.
    """
    year_built_raw = ctx.appraisal.value("year_built")
    eff_date_raw = ctx.appraisal.value("effective_date")
    # actual_age as a separately-extracted field (may share effective_age extraction)
    actual_age_raw = ctx.appraisal.value("effective_age")

    ev = [
        ctx.appraisal.evidence("year_built"),
        ctx.appraisal.evidence("effective_date"),
        ctx.appraisal.evidence("effective_age"),
    ]

    year_built = _to_float(year_built_raw)
    eff_date = _parse_date(eff_date_raw)

    if year_built is None or eff_date is None:
        missing = [
            name for name, v in (
                ("year_built", year_built),
                ("effective_date", eff_date),
            ) if v is None
        ]
        return _res_imp(
            "I-YRBUILT", "I-yrbuilt", RuleStatus.SKIPPED,
            message=(
                f"Year built / effective date check cannot be evaluated; the following "
                f"field(s) could not be extracted: {', '.join(missing)}."
            ),
            fields=["year_built", "effective_date"],
            evidence=ev,
        )

    year_built_int = int(year_built)

    # Plausibility gate: year_built outside 1800-2030 is almost certainly wrong
    if not (1800 <= year_built_int <= 2030):
        return _res_imp(
            "I-YRBUILT", "I-yrbuilt", RuleStatus.VERIFY,
            message=(
                f"The year built ({year_built_int}) is outside the plausible range "
                f"(1800-2030); please verify the year built."
            ),
            fields=["year_built"],
            evidence=ev,
            confidence=0.5,
        )

    calculated_age = eff_date.year - year_built_int
    stated_age = _to_float(actual_age_raw)

    # No stated actual_age to compare against — nothing to verify, PASS.
    if stated_age is None:
        return _res_imp(
            "I-YRBUILT", "I-yrbuilt", RuleStatus.PASS,
            fields=["year_built", "effective_date"],
            evidence=ev,
        )

    tolerance = int(qc_config.semantic("age_yrbuilt_tolerance", 2))
    stated_age_int = int(stated_age)
    delta = abs(calculated_age - stated_age_int)

    if delta <= tolerance:
        return _res_imp(
            "I-YRBUILT", "I-yrbuilt", RuleStatus.PASS,
            fields=["year_built", "effective_date", "effective_age"],
            evidence=ev,
        )

    # Discrepancy — confidence gate @ 0.85 before VERIFY (judgment; never auto-FAIL)
    min_conf = min(
        ctx.appraisal.confidence("year_built"),
        ctx.appraisal.confidence("effective_date"),
        ctx.appraisal.confidence("effective_age"),
    )
    if min_conf >= ctx.checkbox_conf:
        return _res_imp(
            "I-YRBUILT", "I-yrbuilt", RuleStatus.PASS,
            fields=["year_built", "effective_date", "effective_age"],
            evidence=ev,
        )

    confidence = min_conf if min_conf < ctx.structured_conf else 0.7

    msg = qc_config.template(
        "I-1-yrbuilt",
        stated=stated_age_int,
        yb=year_built_int,
        eff=str(eff_date),
        calc=calculated_age,
    )
    return _res_imp(
        "I-YRBUILT", "I-yrbuilt", RuleStatus.VERIFY,
        message=msg,
        fields=["year_built", "effective_date", "effective_age"],
        evidence=ev,
        template_id="I-1-yrbuilt",
        confidence=confidence,
    )


# ===========================================================================
# TL-ENG — Engagement letter date precedes report date
# ===========================================================================

def _has_engagement(ctx: QCContext) -> bool:
    return ctx.has_engagement


@rule(id="TL-ENG", num="TL-eng", section="signature", phase=2,
      applies_when=_has_engagement,
      name="Engagement letter date precedes report signature date")
def tl_eng_order(ctx: QCContext):
    """
    The engagement must be placed before the report is signed.
    Tries order_date first, then assigned_date, then due_date from the engagement.
    """
    eng_date = None
    eng_field_used = None
    for field_name in ("order_date", "assigned_date", "due_date"):
        raw = ctx.engagement.value(field_name)
        if raw:
            parsed = _parse_date(raw)
            if parsed:
                eng_date = parsed
                eng_field_used = field_name
                break

    sig_raw = ctx.appraisal.value("signature_date")
    sig_date = _parse_date(sig_raw)

    ev = [
        ctx.engagement.evidence(eng_field_used or "order_date"),
        ctx.appraisal.evidence("signature_date"),
    ]

    if eng_date is None or sig_date is None:
        missing = []
        if eng_date is None:
            missing.append("engagement order/assigned/due date")
        if sig_date is None:
            missing.append("signature_date")
        # confidence gate @ 0.90
        _tl_conf = min(
            ctx.engagement.confidence(eng_field_used or "order_date"),
            ctx.appraisal.confidence("signature_date"),
        )
        if _tl_conf >= 0.90:
            return _res_sig("TL-ENG", "TL-eng", RuleStatus.PASS,
                            fields=["signature_date"], evidence=ev)
        return _res_sig(
            "TL-ENG", "TL-eng", RuleStatus.SKIPPED,
            message=(
                f"Engagement vs signature date check cannot be evaluated; the following "
                f"field(s) could not be extracted: {', '.join(missing)}."
            ),
            fields=["signature_date"],
            evidence=ev,
        )

    if eng_date <= sig_date:
        return _res_sig(
            "TL-ENG", "TL-eng", RuleStatus.PASS,
            fields=["signature_date"],
            evidence=ev,
        )

    # Engagement date is AFTER signature — timeline violation
    min_conf = min(
        ctx.engagement.confidence(eng_field_used or "order_date"),
        ctx.appraisal.confidence("signature_date"),
    )
    status = RuleStatus.FAIL
    confidence = 1.0
    if min_conf < ctx.structured_conf:
        status = RuleStatus.VERIFY
        confidence = min_conf

    msg = qc_config.template(
        "TL-ENG-order",
        a=str(eng_date),
        b=str(sig_date),
    )
    return _res_sig(
        "TL-ENG", "TL-eng", status,
        message=msg,
        fields=["signature_date"],
        evidence=ev,
        template_id="TL-ENG-order",
        confidence=confidence,
    )


# ===========================================================================
# TL-CONTRACT — Contract date precedes appraisal effective date
# ===========================================================================

def _is_purchase(ctx: QCContext) -> bool:
    return ctx.transaction_type == "purchase"


@rule(id="TL-CONTRACT", num="TL-contract", section="contract", phase=2,
      applies_when=_is_purchase,
      name="Contract date precedes appraisal effective date")
def tl_contract_date(ctx: QCContext):
    """
    The purchase contract must be executed at or before the appraisal effective date.
    If contract_date > effective_date the appraiser may not have had the contract.
    """
    contract_raw = ctx.appraisal.value("contract_date")
    eff_raw = ctx.appraisal.value("effective_date")

    ev = [
        ctx.appraisal.evidence("contract_date"),
        ctx.appraisal.evidence("effective_date"),
    ]

    contract_date = _parse_date(contract_raw)
    eff_date = _parse_date(eff_raw)

    if contract_date is None or eff_date is None:
        missing = [
            name for name, v in (
                ("contract_date", contract_date),
                ("effective_date", eff_date),
            ) if v is None
        ]
        return _res_con(
            "TL-CONTRACT", "TL-contract", RuleStatus.SKIPPED,
            message=(
                f"Contract vs effective date check cannot be evaluated; the following "
                f"field(s) could not be extracted: {', '.join(missing)}."
            ),
            fields=["contract_date", "effective_date"],
            evidence=ev,
        )

    if contract_date <= eff_date:
        return _res_con(
            "TL-CONTRACT", "TL-contract", RuleStatus.PASS,
            fields=["contract_date", "effective_date"],
            evidence=ev,
        )

    # Contract is AFTER effective date — timeline violation
    min_conf = min(
        ctx.appraisal.confidence("contract_date"),
        ctx.appraisal.confidence("effective_date"),
    )
    status = RuleStatus.FAIL
    confidence = 1.0
    if min_conf < ctx.structured_conf:
        status = RuleStatus.VERIFY
        confidence = min_conf

    msg = qc_config.template(
        "TL-CONTRACT-late",
        a=str(contract_date),
        b=str(eff_date),
    )
    return _res_con(
        "TL-CONTRACT", "TL-contract", status,
        message=msg,
        fields=["contract_date", "effective_date"],
        evidence=ev,
        template_id="TL-CONTRACT-late",
        confidence=confidence,
    )


# ===========================================================================
# C-ANALYZE — Did-analyze-contract consistency
# ===========================================================================

@rule(id="C-ANALYZE", num="C-analyze", section="contract", phase=2,
      name="Contract analysis indicator consistency")
def c_analyze_contract(ctx: QCContext):
    """
    Purchase: contract_analyzed must be "Y".
    Refinance: contract_analyzed must NOT be "Y".
    Purchase + analyzed=Y but no contract provided → VERIFY.
    """
    analyzed_raw = ctx.appraisal.value("contract_analyzed")
    txn = ctx.transaction_type

    ev = [ctx.appraisal.evidence("contract_analyzed")]

    if analyzed_raw is None:
        # confidence gate @ 0.85
        _ca_conf = ctx.appraisal.confidence("contract_analyzed")
        if _ca_conf >= ctx.checkbox_conf:
            return _res_con("C-ANALYZE", "C-analyze", RuleStatus.PASS,
                            fields=["contract_analyzed"], evidence=ev)
        return _res_con(
            "C-ANALYZE", "C-analyze", RuleStatus.SKIPPED,
            message=(
                "The contract_analyzed indicator could not be extracted; "
                "rule cannot evaluate."
            ),
            fields=["contract_analyzed"],
            evidence=ev,
        )

    analyzed = str(analyzed_raw).strip().upper() in {"Y", "YES", "TRUE", "1"}

    # Refinance: contract_analyzed should be "N"
    if txn == "refinance" and analyzed:
        msg = qc_config.template("C-1-refi-blank")
        return _res_con(
            "C-ANALYZE", "C-analyze", RuleStatus.FAIL,
            message=msg,
            fields=["contract_analyzed"],
            evidence=ev,
            template_id="C-1-refi-blank",
        )

    # Purchase: contract_analyzed must be "Y"
    if txn == "purchase" and not analyzed:
        msg = qc_config.template("C-1-analyze")
        return _res_con(
            "C-ANALYZE", "C-analyze", RuleStatus.FAIL,
            message=msg,
            fields=["contract_analyzed"],
            evidence=ev,
            template_id="C-1-analyze",
        )

    # Purchase + analyzed=Y but no contract in case file → VERIFY
    if txn == "purchase" and analyzed and not ctx.has_contract:
        msg = qc_config.template("C-ANALYZE-nocontract")
        return _res_con(
            "C-ANALYZE", "C-analyze", RuleStatus.VERIFY,
            message=msg,
            fields=["contract_analyzed"],
            evidence=ev,
            template_id="C-ANALYZE-nocontract",
            confidence=0.7,
        )

    return _res_con(
        "C-ANALYZE", "C-analyze", RuleStatus.PASS,
        fields=["contract_analyzed"],
        evidence=ev,
    )


# ===========================================================================
# LISTING-CMNT — Listed price vs appraised value without commentary
# ===========================================================================

def _subject_listed(ctx: QCContext) -> bool:
    val = ctx.appraisal.value("listed_past_year")
    return str(val).strip().lower() in {"y", "yes", "true", "1"}


@rule(id="LISTING-CMNT", num="listing-cmnt", section="subject", phase=5,
      applies_when=_subject_listed,
      name="Listing price vs appraised value commentary")
def listing_cmnt_variance(ctx: QCContext):
    """
    When the subject was listed in the past year, extract the listing price from
    listing_history and compare it to the appraised_value. If they diverge beyond
    the threshold, check the narrative for listing commentary via layer_b.assess().
    """
    listing_history = ctx.appraisal.value("listing_history")
    appraised_value_raw = ctx.appraisal.value("appraised_value")

    ev = [
        ctx.appraisal.evidence("listing_history"),
        ctx.appraisal.evidence("appraised_value"),
        ctx.appraisal.evidence("listed_past_year"),
    ]

    appraised_value = _to_float(appraised_value_raw)

    if appraised_value is None:
        return _res_sub(
            "LISTING-CMNT", "listing-cmnt", RuleStatus.SKIPPED,
            message=(
                "The appraised_value could not be extracted; "
                "listing price comparison cannot be evaluated."
            ),
            fields=["appraised_value", "listing_history"],
            evidence=ev,
        )

    listing_price = _extract_listing_price(str(listing_history or ""))

    if listing_price is None:
        # listed=Y but no price found in history text — confidence gate @ 0.85
        _lc_conf = ctx.appraisal.confidence("listing_history")
        if _lc_conf >= ctx.checkbox_conf:
            return _res_sub("LISTING-CMNT", "listing-cmnt", RuleStatus.PASS,
                            fields=["listing_history", "appraised_value"], evidence=ev)
        return _res_sub(
            "LISTING-CMNT", "listing-cmnt", RuleStatus.VERIFY,
            message=(
                "The subject was listed in the past year but a listing price could not "
                "be extracted from the listing history. Please confirm the prior listing "
                "details and any commentary addressing the listing relationship are present."
            ),
            fields=["listing_history", "appraised_value"],
            evidence=ev,
            confidence=0.5,
        )

    if appraised_value == 0:
        return _res_sub(
            "LISTING-CMNT", "listing-cmnt", RuleStatus.SKIPPED,
            message="The appraised_value is zero; listing price comparison cannot be evaluated.",
            fields=["appraised_value"],
            evidence=ev,
        )

    threshold = float(qc_config.semantic("listing_price_pct", 3.0))
    pct_diff = abs((listing_price - appraised_value) / appraised_value * 100.0)

    if pct_diff <= threshold:
        return _res_sub(
            "LISTING-CMNT", "listing-cmnt", RuleStatus.PASS,
            fields=["listing_history", "appraised_value"],
            evidence=ev,
        )

    # Divergence exceeds threshold — check narrative for listing commentary
    base_msg = qc_config.template(
        "LISTING-CMNT-var",
        listing=f"${listing_price:,.0f}",
        value=f"{appraised_value:,.0f}",
        pct=f"{pct_diff:.1f}",
    )
    facts = (
        f"listing price ${listing_price:,.0f} vs opinion of value "
        f"${appraised_value:,.0f} ({pct_diff:.1f}% difference)"
    )

    v = layer_b.assess(
        ctx,
        concern="marketability",
        base_message=base_msg,
        facts=facts,
    )
    return _res_sub(
        "LISTING-CMNT", "listing-cmnt", v.status,
        message=v.message,
        fields=["listing_history", "appraised_value"],
        evidence=ev,
        template_id="LISTING-CMNT-var",
        confidence=v.confidence,
        reasoning=v.reasoning,
    )
