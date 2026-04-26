"""
Neighborhood Section Rules — N-1 through N-7 (QC Checklist structural checks)

Checks completeness of the Neighborhood section checkboxes, price ranges,
land use totals, boundaries, and commentary fields.

Field name mapping to NeighborhoodSection model:
  growth          → growth_rate
  price_predominant → predominant_price
  boundaries      → boundaries_description
  description     → description_commentary
  market_conditions → market_conditions_comment

All rules return VERIFY (not FAIL) when fields are not yet extracted,
since neighborhood section extraction is populated by qc_processor from Phase 2.
Commentary QUALITY checks are in narrative_rules.py (COM-1..COM-7).
"""

from app.rule_engine.engine import rule, RuleStatus, RuleResult, RuleSeverity, DataMissingException
from app.models.appraisal import ValidationContext


@rule(id="N-1", name="Neighborhood Characteristics")
def validate_neighborhood_characteristics(ctx: ValidationContext) -> RuleResult:
    """
    N-1: Location (Urban/Suburban/Rural), Built-Up %, Growth — at least 1 each must be checked.
    """
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr:
        raise DataMissingException("Neighborhood Section")

    missing = []
    if not nbr.location:    missing.append("Location")
    if not nbr.built_up:    missing.append("Built-Up")
    if not nbr.growth_rate: missing.append("Growth")

    if missing:
        return RuleResult(
            rule_id="N-1", rule_name="Neighborhood Characteristics",
            status=RuleStatus.VERIFY,
            message=f"Neighborhood checkboxes could not be verified: {', '.join(missing)}. "
                    "Confirm Location, Built-Up, and Growth are all marked.",
            review_required=True, severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-1", rule_name="Neighborhood Characteristics",
        status=RuleStatus.PASS,
        message=f"{nbr.location} / {nbr.built_up} / {nbr.growth_rate}.",
        severity=RuleSeverity.STANDARD,
    )


@rule(id="N-2", name="Housing Trends")
def validate_housing_trends(ctx: ValidationContext) -> RuleResult:
    """N-2: Property Values, Demand/Supply, Marketing Time must be checked."""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    missing = [f for f, v in [
        ("Property Values", nbr.property_values),
        ("Demand/Supply",   nbr.demand_supply),
        ("Marketing Time",  nbr.marketing_time),
    ] if not v]

    if missing:
        return RuleResult(
            rule_id="N-2", rule_name="Housing Trends",
            status=RuleStatus.VERIFY,
            message=f"Could not verify: {', '.join(missing)}.",
            review_required=True, severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-2", rule_name="Housing Trends",
        status=RuleStatus.PASS,
        message=f"Values={nbr.property_values}, Supply={nbr.demand_supply}, Marketing={nbr.marketing_time}.",
        severity=RuleSeverity.STANDARD,
    )


@rule(id="N-3", name="One-Unit Housing Price Range")
def validate_housing_price_range(ctx: ValidationContext) -> RuleResult:
    """N-3: Price Low/High must be provided and Low ≤ High."""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    if nbr.price_low is None or nbr.price_high is None:
        return RuleResult(
            rule_id="N-3", rule_name="One-Unit Housing Price Range",
            status=RuleStatus.VERIFY,
            message="Housing price range (Low/High) not extracted. Verify price range is provided.",
            review_required=True, severity=RuleSeverity.ADVISORY,
        )
    if nbr.price_low > nbr.price_high:
        return RuleResult(
            rule_id="N-3", rule_name="One-Unit Housing Price Range",
            status=RuleStatus.FAIL,
            message=f"Price Low (${nbr.price_low:,.0f}) exceeds Price High (${nbr.price_high:,.0f}).",
            appraisal_value=f"Low=${nbr.price_low:,.0f}, High=${nbr.price_high:,.0f}",
            severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-3", rule_name="One-Unit Housing Price Range",
        status=RuleStatus.PASS,
        message=f"Price range ${nbr.price_low:,.0f}–${nbr.price_high:,.0f}.",
        severity=RuleSeverity.ADVISORY,
    )


@rule(id="N-4", name="Present Land Use Total")
def validate_present_land_use(ctx: ValidationContext) -> RuleResult:
    """N-4: Land use percentages must total 100%."""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    if nbr.land_use_total is None:
        return RuleResult(
            rule_id="N-4", rule_name="Present Land Use Total",
            status=RuleStatus.VERIFY,
            message="Land use total not extracted. Confirm percentages sum to 100%.",
            review_required=True, severity=RuleSeverity.ADVISORY,
        )
    if abs(nbr.land_use_total - 100) > 1:
        return RuleResult(
            rule_id="N-4", rule_name="Present Land Use Total",
            status=RuleStatus.FAIL,
            message=f"Present land use totals {nbr.land_use_total:.0f}% — must equal 100%.",
            appraisal_value=f"{nbr.land_use_total:.0f}%",
            severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-4", rule_name="Present Land Use Total",
        status=RuleStatus.PASS,
        message=f"Land use totals {nbr.land_use_total:.0f}%.",
        severity=RuleSeverity.ADVISORY,
    )


@rule(id="N-5", name="Neighborhood Boundaries")
def validate_neighborhood_boundaries(ctx: ValidationContext) -> RuleResult:
    """N-5: North, South, East, West — all four must be spelled out (no abbreviations)."""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    text = nbr.boundaries_description or ""
    if not text or len(text.strip()) < 5:
        return RuleResult(
            rule_id="N-5", rule_name="Neighborhood Boundaries",
            status=RuleStatus.VERIFY,
            message="Neighborhood boundaries not extracted. Verify all four directions are described.",
            review_required=True, severity=RuleSeverity.STANDARD,
        )

    upper = text.upper()
    missing = [b for b in ["NORTH", "SOUTH", "EAST", "WEST"] if b not in upper]
    if missing:
        return RuleResult(
            rule_id="N-5", rule_name="Neighborhood Boundaries",
            status=RuleStatus.FAIL,
            message=f"Missing boundaries: {', '.join(m.capitalize() for m in missing)}. "
                    "Spell out North, South, East, West — do not abbreviate.",
            appraisal_value=text[:100],
            severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-5", rule_name="Neighborhood Boundaries",
        status=RuleStatus.PASS,
        message="All four neighborhood boundaries are described.",
        severity=RuleSeverity.STANDARD,
    )


@rule(id="N-6", name="Neighborhood Description Present")
def validate_neighborhood_description_present(ctx: ValidationContext) -> RuleResult:
    """N-6: Neighborhood description must be present. (Quality checked by COM-1.)"""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    text = nbr.description_commentary or ""
    if not text or len(text.strip()) < 10:
        return RuleResult(
            rule_id="N-6", rule_name="Neighborhood Description Present",
            status=RuleStatus.VERIFY,
            message="Neighborhood description not found. A specific area description is required.",
            review_required=True, severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-6", rule_name="Neighborhood Description Present",
        status=RuleStatus.PASS,
        message="Neighborhood description is present.",
        severity=RuleSeverity.STANDARD,
    )


@rule(id="N-7", name="Market Conditions Present")
def validate_market_conditions_present(ctx: ValidationContext) -> RuleResult:
    """N-7: Market conditions must have actual content. 'See 1004MC' alone is not acceptable."""
    nbr = getattr(ctx.report, "neighborhood", None)
    if not nbr: raise DataMissingException("Neighborhood Section")

    text = nbr.market_conditions_comment or ""
    if not text or len(text.strip()) < 5:
        return RuleResult(
            rule_id="N-7", rule_name="Market Conditions Present",
            status=RuleStatus.VERIFY,
            message="Market conditions commentary not found. Please verify this section.",
            review_required=True, severity=RuleSeverity.STANDARD,
        )
    if "SEE 1004MC" in text.upper() and len(text.strip()) < 15:
        return RuleResult(
            rule_id="N-7", rule_name="Market Conditions Present",
            status=RuleStatus.FAIL,
            message="'See 1004MC' is not acceptable as the sole market conditions commentary.",
            appraisal_value=text.strip(), severity=RuleSeverity.STANDARD,
        )
    return RuleResult(
        rule_id="N-7", rule_name="Market Conditions Present",
        status=RuleStatus.PASS,
        message="Market conditions commentary is present.",
        severity=RuleSeverity.STANDARD,
    )
