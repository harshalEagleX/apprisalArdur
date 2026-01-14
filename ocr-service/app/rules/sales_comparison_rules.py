"""Sales Comparison Approach Rules (SCA-1, SCA-2)

Validations for the Sales Comparison Approach section of appraisal reports.

NOTE: Missing data should raise DataMissingException so the engine converts it
into VERIFY (human review) rather than a hard failure.
"""

import re
from typing import Dict, List, Optional, Tuple

from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


def _count_grid_sales(ctx: ValidationContext) -> int:
    comps = ctx.report.sales_comparison.comparables or []
    # Treat anything not explicitly marked listing as a sale comparable.
    return sum(1 for c in comps if not getattr(c, "is_listing", False))


def _count_grid_listings(ctx: ValidationContext) -> int:
    comps = ctx.report.sales_comparison.comparables or []
    return sum(1 for c in comps if getattr(c, "is_listing", False))


def _comps(ctx: ValidationContext):
    comps = ctx.report.sales_comparison.comparables
    if comps is None:
        raise DataMissingException("Sales Comparison Grid Comparables")
    return comps


def _idxs_missing(comps, attr: str) -> List[int]:
    out: List[int] = []
    for i, c in enumerate(comps, start=1):
        v = getattr(c, attr, None)
        if v is None:
            out.append(i)
            continue
        if isinstance(v, str) and not v.strip():
            out.append(i)
    return out


def _idxs_invalid(comps, attr: str, pred) -> List[int]:
    out: List[int] = []
    for i, c in enumerate(comps, start=1):
        v = getattr(c, attr, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        if not pred(v):
            out.append(i)
    return out


def _uad_quality(val: str) -> bool:
    return bool(re.fullmatch(r"Q[1-6]", val.strip(), re.IGNORECASE))


def _uad_condition(val: str) -> bool:
    return bool(re.fullmatch(r"C[1-6]", val.strip(), re.IGNORECASE))


def _uad_proximity(val: str) -> bool:
    # Example: 0.25 mi NE
    v = val.strip().upper()
    if not re.search(r"\b(N|S|E|W|NE|NW|SE|SW)\b", v):
        return False
    m = re.search(r"(\d+(?:\.\d+)?)", v)
    if not m:
        return False
    try:
        return float(m.group(1)) >= 0.01
    except Exception:
        return False


def _looks_like_usps_address(val: str) -> bool:
    v = val.strip()
    # Minimal checks only (street number + street name). USPS verification itself is not machine-checkable here.
    return bool(re.search(r"\b\d+\b", v) and re.search(r"[A-Za-z]", v))


def _uad_data_source(val: str) -> bool:
    v = val.strip()
    # Expect something like: MISMLS#3546935;DOM12 (allow Unk)
    has_mls = bool(re.search(r"\bMLS\s*#?\s*\w+", v, re.IGNORECASE) or re.search(r"#\d{4,}", v))
    has_dom = bool(re.search(r"\bDOM\s*(\d+|Unk)\b", v, re.IGNORECASE))
    return has_mls and has_dom


def _date_like(val: str) -> bool:
    v = val.strip()
    return bool(
        re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", v)
        or re.search(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", v)
        or re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b", v, re.IGNORECASE)
    )


def _uad_rating_semicolon(val: str) -> bool:
    # Generic "Rating;Descriptor" (max 2 descriptors isn't enforced strictly).
    v = val.strip()
    return bool(re.match(r"^[^;]+;[^;]+(?:;[^;]+)?$", v))


def _result_verify(rule_id: str, rule_name: str, message: str, details: Optional[Dict[str, object]] = None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_name,
        status=RuleStatus.VERIFY,
        message=message,
        details=details or {},
        action_item="Please verify/correct the Sales Comparison grid field(s) and add commentary where required.",
        review_required=True,
    )


def _result_fail(rule_id: str, rule_name: str, message: str, details: Optional[Dict[str, object]] = None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_name,
        status=RuleStatus.FAIL,
        message=message,
        details=details or {},
        action_item="Please correct the Sales Comparison grid per UAD/QC requirements or provide supporting commentary.",
        review_required=True,
    )


@rule(id="SCA-1", name="Comparable Market Summary")
def validate_sca_1_comparable_market_summary(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields:
      - # of Comparable Properties Currently Offered
      - # of Comparable Sales within 12 Months

    Rule:
      - Counts must be present.
      - Counts should be consistent with comparables provided in the grid.

    NOTE:
      - Cross-check with 1004MC and predominant price ranges is not reliably
        machine-checkable yet; do not FAIL for that. Use PASS/VERIFY based on
        extraction completeness and internal consistency.
    """
    sca = ctx.report.sales_comparison

    if sca.comparables_count_sales is None:
        raise DataMissingException("# of Comparable Sales within 12 Months")
    if sca.comparables_count_listings is None:
        raise DataMissingException("# of Comparable Properties Currently Offered")

    grid_sales = _count_grid_sales(ctx)
    grid_listings = _count_grid_listings(ctx)

    # If grid is empty, we can only VERIFY (can't validate consistency).
    if grid_sales + grid_listings == 0:
        return RuleResult(
            rule_id="SCA-1",
            rule_name="Comparable Market Summary",
            status=RuleStatus.VERIFY,
            message=(
                "Sales Comparison grid comparables were not extracted. "
                "Please verify '# Listings' and '# Sales' fields above the grid manually."
            ),
            details={
                "comparables_count_sales": sca.comparables_count_sales,
                "comparables_count_listings": sca.comparables_count_listings,
            },
            action_item="Complete/verify the Sales Comparison grid and the market summary counts above the grid.",
            review_required=True,
        )

    # Counts above the grid should not be less than what the grid actually contains.
    if sca.comparables_count_sales < grid_sales or sca.comparables_count_listings < grid_listings:
        return RuleResult(
            rule_id="SCA-1",
            rule_name="Comparable Market Summary",
            status=RuleStatus.FAIL,
            message=(
                "The '# Listings' / '# Sales' market summary counts above the Sales Comparison grid "
                "are inconsistent with the comparables shown in the grid."
            ),
            details={
                "summary_sales_within_12_months": sca.comparables_count_sales,
                "summary_listings_currently_offered": sca.comparables_count_listings,
                "grid_sales": grid_sales,
                "grid_listings": grid_listings,
            },
            action_item="Update the market summary counts above the grid so they are consistent with the comparables provided.",
            review_required=True,
        )

    return RuleResult(
        rule_id="SCA-1",
        rule_name="Comparable Market Summary",
        status=RuleStatus.PASS,
        message=(
            f"Market summary counts present (Sales within 12 months: {sca.comparables_count_sales}, "
            f"Listings currently offered: {sca.comparables_count_listings})."
        ),
        details={
            "summary_sales_within_12_months": sca.comparables_count_sales,
            "summary_listings_currently_offered": sca.comparables_count_listings,
            "grid_sales": grid_sales,
            "grid_listings": grid_listings,
        },
    )


@rule(id="SCA-2", name="Comparables Required")
def validate_sca_2_comparables_required(ctx: ValidationContext) -> RuleResult:
    """
    Requirement:
      - Value < $1M: minimum 3 sales + 2 listings
      - Value >= $1M: minimum 4 sales + 2 listings

    Current implementation:
      - We do not reliably have the final value extracted yet.
      - Therefore:
          - Always require at least 3 sales + 2 listings.
          - If exactly 3 sales are present, return VERIFY to flag that >=$1M may
            require 4 sales.
    """
    comps = ctx.report.sales_comparison.comparables
    if comps is None:
        raise DataMissingException("Sales Comparison Grid Comparables")

    grid_sales = _count_grid_sales(ctx)
    grid_listings = _count_grid_listings(ctx)

    # If we could not extract the grid rows, do not hard fail; require manual verification.
    if (grid_sales + grid_listings) == 0:
        raise DataMissingException("Sales Comparison Grid Comparables")

    if grid_sales < 3 or grid_listings < 2:
        return RuleResult(
            rule_id="SCA-2",
            rule_name="Comparables Required",
            status=RuleStatus.FAIL,
            message=(
                "Sales Comparison Approach does not meet minimum comparable requirements: "
                "minimum 3 sales and 2 listings are required."
            ),
            details={"grid_sales": grid_sales, "grid_listings": grid_listings},
            action_item="Add sufficient comparable sales and listings/pending sales in the Sales Comparison grid.",
            review_required=True,
        )

    if grid_sales == 3:
        return RuleResult(
            rule_id="SCA-2",
            rule_name="Comparables Required",
            status=RuleStatus.VERIFY,
            message=(
                "Minimum baseline met (3 sales + 2 listings). Verify if subject value is >= $1M; "
                "if so, 4 sales comparables are required."
            ),
            details={"grid_sales": grid_sales, "grid_listings": grid_listings},
            action_item="Verify if subject value is >= $1M and add a 4th sale comparable if required.",
            review_required=True,
        )

    return RuleResult(
        rule_id="SCA-2",
        rule_name="Comparables Required",
        status=RuleStatus.PASS,
        message=f"Comparable minimums satisfied (Sales: {grid_sales}, Listings: {grid_listings}).",
        details={"grid_sales": grid_sales, "grid_listings": grid_listings},
    )


@rule(id="SCA-3", name="Address (Subject and Comparables)")
def validate_sca_3_addresses(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)

    subj = ctx.report.subject
    if not getattr(subj, "address", None):
        raise DataMissingException("Subject Address")
    if not getattr(subj, "zip_code", None):
        raise DataMissingException("Subject Zip Code")

    missing = _idxs_missing(comps, "address")
    if missing:
        return _result_verify(
            "SCA-3",
            "Address (Subject and Comparables)",
            "Comparable address is missing for one or more comparables; please correct or comment.",
            {"missing_comp_addresses": missing},
        )

    invalid = _idxs_invalid(comps, "address", _looks_like_usps_address)
    if invalid:
        return _result_verify(
            "SCA-3",
            "Address (Subject and Comparables)",
            "Comparable address format may not be USPS/UAD compliant; please verify/correct.",
            {"invalid_comp_addresses": invalid},
        )

    return RuleResult(
        rule_id="SCA-3",
        rule_name="Address (Subject and Comparables)",
        status=RuleStatus.PASS,
        message="Subject and comparable addresses are present.",
    )


@rule(id="SCA-4", name="Proximity to Subject")
def validate_sca_4_proximity(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "proximity")
    if missing:
        return _result_verify(
            "SCA-4",
            "Proximity to Subject",
            "Proximity to subject is missing for one or more comparables; please provide proximity (minimum 0.01 miles with direction) or verify map support.",
            {"missing_proximity": missing},
        )

    invalid = _idxs_invalid(comps, "proximity", _uad_proximity)
    if invalid:
        return _result_fail(
            "SCA-4",
            "Proximity to Subject",
            "Proximity to subject is not UAD compliant (must include miles and direction). Please correct or comment.",
            {"invalid_proximity": invalid},
        )

    return RuleResult(
        rule_id="SCA-4",
        rule_name="Proximity to Subject",
        status=RuleStatus.PASS,
        message="Proximity appears present and plausibly UAD formatted for all extracted comparables.",
    )


@rule(id="SCA-5", name="Data Sources")
def validate_sca_5_data_sources(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "data_source")
    if missing:
        return _result_verify(
            "SCA-5",
            "Data Sources",
            "Data Source(s) are missing for one or more comparables. Please provide specific MLS name/MLS# and DOM (or Unk with commentary).",
            {"missing_data_source": missing},
        )

    invalid = _idxs_invalid(comps, "data_source", _uad_data_source)
    if invalid:
        return _result_verify(
            "SCA-5",
            "Data Sources",
            "MLS number and/or DOM not detected in Data Source(s) for one or more comparables; please correct or comment.",
            {"invalid_data_source": invalid},
        )

    return RuleResult(
        rule_id="SCA-5",
        rule_name="Data Sources",
        status=RuleStatus.PASS,
        message="Data Source(s) appear present for extracted comparables.",
    )


@rule(id="SCA-6", name="Verification Sources")
def validate_sca_6_verification_sources(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "verification_source")
    if missing:
        return _result_verify(
            "SCA-6",
            "Verification Sources",
            "Verification Source(s) are missing for one or more closed comparable sales; please provide a full specific source name (e.g., County Assessor Tax Card).",
            {"missing_verification_source": missing},
        )

    return RuleResult(
        rule_id="SCA-6",
        rule_name="Verification Sources",
        status=RuleStatus.PASS,
        message="Verification Source(s) appear present for extracted comparables.",
    )


@rule(id="SCA-7", name="Sale or Financing Concessions")
def validate_sca_7_financing_concessions(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "sale_financing_concessions")
    if missing:
        return _result_verify(
            "SCA-7",
            "Sale or Financing Concessions",
            "Sale/financing/concessions field is missing for one or more comparables; please correct or comment (and add '0' where no adjustment is applied for UAD compliance).",
            {"missing_sale_financing_concessions": missing},
        )

    return RuleResult(
        rule_id="SCA-7",
        rule_name="Sale or Financing Concessions",
        status=RuleStatus.PASS,
        message="Sale/financing/concessions fields appear present for extracted comparables; verify adjustment direction and '0' entries where applicable.",
    )


@rule(id="SCA-8", name="Date of Sale/Time Adjustment")
def validate_sca_8_sale_dates(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "sale_date")
    if missing:
        return _result_verify(
            "SCA-8",
            "Date of Sale/Time Adjustment",
            "Sale date is missing for one or more comparables; please correct or comment.",
            {"missing_sale_date": missing},
        )

    invalid = _idxs_invalid(comps, "sale_date", _date_like)
    if invalid:
        return _result_verify(
            "SCA-8",
            "Date of Sale/Time Adjustment",
            "Sale date format may not be UAD compliant; please verify/correct.",
            {"invalid_sale_date": invalid},
        )

    return RuleResult(
        rule_id="SCA-8",
        rule_name="Date of Sale/Time Adjustment",
        status=RuleStatus.PASS,
        message="Sale date appears present for extracted comparables.",
    )


@rule(id="SCA-9", name="Location Rating")
def validate_sca_9_location_rating(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "location_rating")
    if missing:
        return _result_verify(
            "SCA-9",
            "Location Rating",
            "Location rating is missing for one or more comparables; please correct or comment.",
            {"missing_location_rating": missing},
        )

    invalid = _idxs_invalid(comps, "location_rating", _uad_rating_semicolon)
    if invalid:
        return _result_verify(
            "SCA-9",
            "Location Rating",
            "Location rating may not be UAD compliant (expected Rating;Type;Other). Please verify/correct.",
            {"invalid_location_rating": invalid},
        )

    return RuleResult(
        rule_id="SCA-9",
        rule_name="Location Rating",
        status=RuleStatus.PASS,
        message="Location ratings appear present for extracted comparables.",
    )


@rule(id="SCA-10", name="Leasehold/Fee Simple")
def validate_sca_10_leasehold_fee_simple(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "leasehold_fee_simple")
    if missing:
        return _result_verify(
            "SCA-10",
            "Leasehold/Fee Simple",
            "Leasehold/Fee Simple field is missing for one or more comparables; please correct or comment.",
            {"missing_leasehold_fee_simple": missing},
        )

    invalid = _idxs_invalid(
        comps,
        "leasehold_fee_simple",
        lambda v: bool(re.search(r"fee\s*simple|lease\s*hold|leasehold", str(v), re.IGNORECASE)),
    )
    if invalid:
        return _result_verify(
            "SCA-10",
            "Leasehold/Fee Simple",
            "Leasehold/Fee Simple value may not be standard (expected Fee Simple or Leasehold). Please verify/correct.",
            {"nonstandard_leasehold_fee_simple": invalid},
        )

    return RuleResult(
        rule_id="SCA-10",
        rule_name="Leasehold/Fee Simple",
        status=RuleStatus.PASS,
        message="Leasehold/Fee Simple fields appear present for extracted comparables.",
    )


@rule(id="SCA-11", name="Site")
def validate_sca_11_site(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "site_size")
    if missing:
        return _result_verify(
            "SCA-11",
            "Site",
            "Site size is missing for one or more comparables; please provide with proper units (SF if <1 acre, acreage if >=1 acre).",
            {"missing_site_size": missing},
        )
    return RuleResult(
        rule_id="SCA-11",
        rule_name="Site",
        status=RuleStatus.PASS,
        message="Site sizes appear present for extracted comparables.",
    )


@rule(id="SCA-12", name="View")
def validate_sca_12_view(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "view")
    if missing:
        return _result_verify(
            "SCA-12",
            "View",
            "View field is missing for one or more comparables; please correct or comment. If no adjustment is applied for differences, enter '0' for UAD compliance.",
            {"missing_view": missing},
        )

    return RuleResult(
        rule_id="SCA-12",
        rule_name="View",
        status=RuleStatus.PASS,
        message="View fields appear present for extracted comparables; verify UAD formatting and '0' entries where applicable.",
    )


@rule(id="SCA-13", name="Design (Style)")
def validate_sca_13_design_style(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "design_style")
    if missing:
        return _result_verify(
            "SCA-13",
            "Design (Style)",
            "Design/Style field is missing for one or more comparables; please correct or comment. If no adjustment is applied for differences, enter '0' for UAD compliance.",
            {"missing_design_style": missing},
        )

    return RuleResult(
        rule_id="SCA-13",
        rule_name="Design (Style)",
        status=RuleStatus.PASS,
        message="Design/Style fields appear present for extracted comparables; verify UAD formatting manually.",
    )


@rule(id="SCA-14", name="Quality of Construction")
def validate_sca_14_quality(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "quality_rating")
    if missing:
        return _result_verify(
            "SCA-14",
            "Quality of Construction",
            "Quality rating (Q1-Q6) is missing for one or more comparables; please correct or comment.",
            {"missing_quality_rating": missing},
        )

    invalid = _idxs_invalid(comps, "quality_rating", _uad_quality)
    if invalid:
        return _result_fail(
            "SCA-14",
            "Quality of Construction",
            "Quality rating must be UAD compliant (Q1-Q6). Please correct or comment.",
            {"invalid_quality_rating": invalid},
        )

    return RuleResult(
        rule_id="SCA-14",
        rule_name="Quality of Construction",
        status=RuleStatus.PASS,
        message="Quality ratings appear UAD compliant for extracted comparables.",
    )


@rule(id="SCA-15", name="Actual Age")
def validate_sca_15_actual_age(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "actual_age")
    if missing:
        return _result_verify(
            "SCA-15",
            "Actual Age",
            "Actual age is missing for one or more comparables; please correct or comment.",
            {"missing_actual_age": missing},
        )
    return RuleResult(
        rule_id="SCA-15",
        rule_name="Actual Age",
        status=RuleStatus.PASS,
        message="Actual age appears present for extracted comparables.",
    )


@rule(id="SCA-16", name="Condition")
def validate_sca_16_condition(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "condition_rating")
    if missing:
        return _result_verify(
            "SCA-16",
            "Condition",
            "Condition rating (C1-C6) is missing for one or more comparables; please correct or comment.",
            {"missing_condition_rating": missing},
        )

    invalid = _idxs_invalid(comps, "condition_rating", _uad_condition)
    if invalid:
        return _result_fail(
            "SCA-16",
            "Condition",
            "Condition rating must be UAD compliant (C1-C6). Please correct or comment.",
            {"invalid_condition_rating": invalid},
        )

    return RuleResult(
        rule_id="SCA-16",
        rule_name="Condition",
        status=RuleStatus.PASS,
        message="Condition ratings appear UAD compliant for extracted comparables.",
    )


@rule(id="SCA-17", name="Above Grade Room Count and GLA")
def validate_sca_17_rooms_gla(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing_gla = _idxs_missing(comps, "gla")
    if missing_gla:
        return _result_verify(
            "SCA-17",
            "Above Grade Room Count and GLA",
            "GLA is missing for one or more comparables; please correct or comment.",
            {"missing_gla": missing_gla},
        )

    subj_gla = getattr(ctx.report.improvements, "gla", None)
    if subj_gla is None:
        # Can't cross-check sketch/rooms without subject improvements extraction.
        return _result_verify(
            "SCA-17",
            "Above Grade Room Count and GLA",
            "Subject GLA/room counts not extracted to cross-check against the grid/sketch. Please verify manually.",
        )

    return RuleResult(
        rule_id="SCA-17",
        rule_name="Above Grade Room Count and GLA",
        status=RuleStatus.PASS,
        message="GLA appears present for extracted comparables; verify sketch cross-check manually.",
        details={"subject_gla": subj_gla},
    )


@rule(id="SCA-18", name="Basement & Finished Rooms Below Grade")
def validate_sca_18_basement(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "basement_gla")
    if missing:
        return _result_verify(
            "SCA-18",
            "Basement & Finished Rooms Below Grade",
            "Basement/below-grade data is missing for one or more comparables; please correct or comment.",
            {"missing_basement_gla": missing},
        )
    return RuleResult(
        rule_id="SCA-18",
        rule_name="Basement & Finished Rooms Below Grade",
        status=RuleStatus.PASS,
        message="Basement/below-grade fields appear present for extracted comparables; verify exit type/UAD formatting manually.",
    )


@rule(id="SCA-19", name="Functional Utility")
def validate_sca_19_functional_utility(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "functional_utility")
    if missing:
        return _result_verify(
            "SCA-19",
            "Functional Utility",
            "Functional utility field is missing for one or more comparables; please correct or comment. If no adjustment is applied for differences, enter '0' for UAD compliance.",
            {"missing_functional_utility": missing},
        )

    return RuleResult(
        rule_id="SCA-19",
        rule_name="Functional Utility",
        status=RuleStatus.PASS,
        message="Functional utility fields appear present for extracted comparables; verify adjustments and commentary where required.",
    )


@rule(id="SCA-20", name="Heating/Cooling")
def validate_sca_20_heating_cooling(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "heating_cooling")
    if missing:
        return _result_verify(
            "SCA-20",
            "Heating/Cooling",
            "Heating/Cooling field is missing for one or more comparables; please correct or comment.",
            {"missing_heating_cooling": missing},
        )

    return RuleResult(
        rule_id="SCA-20",
        rule_name="Heating/Cooling",
        status=RuleStatus.PASS,
        message="Heating/Cooling fields appear present for extracted comparables; verify they match Page 1 information.",
    )


@rule(id="SCA-21", name="Garage/Carport")
def validate_sca_21_garage(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "garage_carport")
    if missing:
        return _result_verify(
            "SCA-21",
            "Garage/Carport",
            "Garage/Carport data is missing for one or more comparables; please correct or comment.",
            {"missing_garage_carport": missing},
        )
    return RuleResult(
        rule_id="SCA-21",
        rule_name="Garage/Carport",
        status=RuleStatus.PASS,
        message="Garage/Carport fields appear present for extracted comparables; verify UAD formatting manually.",
    )


@rule(id="SCA-22", name="Porch/Patio/Deck")
def validate_sca_22_porch_patio_deck(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    missing = _idxs_missing(comps, "porch_patio_deck")
    if missing:
        return _result_verify(
            "SCA-22",
            "Porch/Patio/Deck",
            "Porch/Patio/Deck field is missing for one or more comparables; please correct or comment (or explicitly state 'None').",
            {"missing_porch_patio_deck": missing},
        )

    return RuleResult(
        rule_id="SCA-22",
        rule_name="Porch/Patio/Deck",
        status=RuleStatus.PASS,
        message="Porch/Patio/Deck fields appear present for extracted comparables; verify they match Page 1 or state 'None'.",
    )


@rule(id="SCA-23", name="Listing Comparables")
def validate_sca_23_listing_comparables(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    listing_count = sum(1 for c in comps if getattr(c, "is_listing", False))
    if listing_count == 0:
        return _result_verify(
            "SCA-23",
            "Listing Comparables",
            "No listing comparables were detected in extracted grid data. Please verify at least two competing listings/pending sales are provided or explain why not warranted.",
        )
    return _result_verify(
        "SCA-23",
        "Listing Comparables",
        "Listing comparable(s) detected. Please verify list-to-sales price ratio adjustment is applied or explain why not warranted.",
        {"listing_comparables_detected": listing_count},
    )


@rule(id="SCA-24", name="Unique Design Properties")
def validate_sca_24_unique_design(ctx: ValidationContext) -> RuleResult:
    return _result_verify(
        "SCA-24",
        "Unique Design Properties",
        "Verify if the subject has unique characteristics (green/log home/1-bedroom/ADU/etc.). If so, include similar comparables or explain in detail why not available.",
    )


@rule(id="SCA-25", name="New Construction")
def validate_sca_25_new_construction(ctx: ValidationContext) -> RuleResult:
    return _result_verify(
        "SCA-25",
        "New Construction",
        "Verify if the subject is new construction. If yes, provide at least one comparable from the competing development (or explain alternatives if not available).",
    )


@rule(id="SCA-26", name="Square Footage")
def validate_sca_26_square_footage(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)

    # We can only do limited machine checks with current extraction fields.
    # If basement_gla is present and gla is present, verify GLA is not obviously using below-grade as above-grade.
    suspicious: List[int] = []
    for i, c in enumerate(comps, start=1):
        gla = getattr(c, "gla", None)
        bg = getattr(c, "basement_gla", None)
        if gla is None or bg is None:
            continue
        try:
            if float(bg) > 0 and float(gla) > 0 and float(bg) >= float(gla):
                suspicious.append(i)
        except Exception:
            continue

    if suspicious:
        return _result_verify(
            "SCA-26",
            "Square Footage",
            "Basement/below-grade square footage may be included in GLA for one or more comparables. Please verify methodology is consistent and explain if necessary.",
            {"suspicious_gla_vs_basement": suspicious},
        )

    return _result_verify(
        "SCA-26",
        "Square Footage",
        "Verify below-grade square footage is not included in GLA unless necessary, and that all comps reflect the same methodology (MLS/public records limitations).",
    )


@rule(id="SCA-27", name="Comparable Photos")
def validate_sca_27_comparable_photos(ctx: ValidationContext) -> RuleResult:
    return _result_verify(
        "SCA-27",
        "Comparable Photos",
        "Verify comparable photos meet loan requirements (MLS photos acceptable for conventional with drive-by commentary; FHA requires drive-by photos).",
    )
