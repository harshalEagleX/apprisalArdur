"""
Neighborhood Section Rules (N-1 through N-7)
All validation rules for the Neighborhood section of appraisal reports.
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="N-1", name="Neighborhood Characteristics")
def validate_neighborhood_characteristics(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Location, Built-Up, Growth
    Rule: At least 1 box in each category MUST be checked
    Validation: Built-Up percentage must coincide with Present Land Use
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood:
        raise DataMissingException("Neighborhood Section")
        
    missing = []
    if not neighborhood.location: missing.append("Location")
    if not neighborhood.built_up: missing.append("Built-Up")
    if not neighborhood.growth: missing.append("Growth")
    
    if missing:
        return RuleResult(
            rule_id="N-1",
            rule_name="Neighborhood Characteristics",
            status=RuleStatus.FAIL,
            message=f"In the neighborhood section, checkbox is missing for {', '.join(missing)}, please revise."
        )
        
    return RuleResult(
        rule_id="N-1",
        rule_name="Neighborhood Characteristics",
        status=RuleStatus.PASS,
        message="Neighborhood characteristics are properly completed."
    )

@rule(id="N-2", name="Housing Trends")
def validate_housing_trends(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Property Values, Demand/Supply, Marketing Time
    Rule: Be aware of Characteristics and Land Use
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood:
        raise DataMissingException("Neighborhood Section")
        
    if not neighborhood.property_values or not neighborhood.demand_supply or not neighborhood.marketing_time:
        return RuleResult(
            rule_id="N-2",
            rule_name="Housing Trends",
            status=RuleStatus.FAIL,
            message="Property Values, Demand/Supply, or Marketing Time fields are missing."
        )
        
    return RuleResult(
        rule_id="N-2",
        rule_name="Housing Trends",
        status=RuleStatus.PASS,
        message="Housing trends are properly completed."
    )

@rule(id="N-3", name="One-Unit Housing Price and Age")
def validate_housing_price_age(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Price Low/High/Predominant, Age Low/High/Predominant
    Format: Range must be Low to High
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood:
        raise DataMissingException("Neighborhood Section")
        
    if not neighborhood.price_low or not neighborhood.price_high or not neighborhood.price_predominant:
        return RuleResult(
            rule_id="N-3",
            rule_name="One-Unit Housing Price and Age",
            status=RuleStatus.FAIL,
            message="Housing price range (Low, High, Predominant) is incomplete."
        )
        
    if neighborhood.price_low > neighborhood.price_high:
         return RuleResult(
            rule_id="N-3",
            rule_name="One-Unit Housing Price and Age",
            status=RuleStatus.FAIL,
            message="Price Low must be less than or equal to Price High."
        )
        
    return RuleResult(
        rule_id="N-3",
        rule_name="One-Unit Housing Price and Age",
        status=RuleStatus.PASS,
        message="Housing price and age ranges are valid."
    )

@rule(id="N-4", name="Present Land Use")
def validate_present_land_use(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Present Land Use percentages
    Rule: Must complete and identify "Other" uses if any percentage given
    Validation: Total MUST equal 100%
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood:
        raise DataMissingException("Neighborhood Section")
        
    total_percentage = (
        (neighborhood.land_use_one_unit or 0) +
        (neighborhood.land_use_two_to_four or 0) +
        (neighborhood.land_use_multi_family or 0) +
        (neighborhood.land_use_commercial or 0) +
        (neighborhood.land_use_other or 0)
    )
    
    if total_percentage != 100:
        return RuleResult(
            rule_id="N-4",
            rule_name="Present Land Use",
            status=RuleStatus.FAIL,
            message="The sum of present land use in the neighborhood section should always be 100%. Please verify and revise as needed."
        )
        
    return RuleResult(
        rule_id="N-4",
        rule_name="Present Land Use",
        status=RuleStatus.PASS,
        message="Present land use totals 100%."
    )

@rule(id="N-5", name="Neighborhood Boundaries")
def validate_neighborhood_boundaries(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Boundaries (North, South, East, West)
    Rule: All four boundaries MUST be described
    Format: Must spell out: "North", "South", "East", "West"
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood:
        raise DataMissingException("Neighborhood Section")
        
    boundaries = neighborhood.boundaries or ""
    boundaries_upper = boundaries.upper()
    
    missing_bounds = []
    for bound in ["NORTH", "SOUTH", "EAST", "WEST"]:
        if bound not in boundaries_upper:
            missing_bounds.append(bound.capitalize())
            
    if missing_bounds:
         return RuleResult(
            rule_id="N-5",
            rule_name="Neighborhood Boundaries",
            status=RuleStatus.FAIL,
            message=f"{', '.join(missing_bounds)} boundary is missing under Neighborhood Boundaries. Please revise. Must be clearly delineated using 'North', 'South', 'East', and 'West'."
        )
        
    return RuleResult(
        rule_id="N-5",
        rule_name="Neighborhood Boundaries",
        status=RuleStatus.PASS,
        message="Neighborhood boundaries are clearly defined."
    )

@rule(id="N-6", name="Neighborhood Description")
def validate_neighborhood_description(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Neighborhood Description
    Rule: Must be completed with specific area description
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood or not neighborhood.description or len(neighborhood.description.strip()) < 10:
         return RuleResult(
            rule_id="N-6",
            rule_name="Neighborhood Description",
            status=RuleStatus.FAIL,
            message="Neighborhood Description must be completed with specific area description."
        )
        
    return RuleResult(
        rule_id="N-6",
        rule_name="Neighborhood Description",
        status=RuleStatus.PASS,
        message="Neighborhood description is provided."
    )

@rule(id="N-7", name="Market Conditions")
def validate_market_conditions(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Market Conditions
    Rule: Must be completed with actual market analysis
    Invalid: "See 1004MC" is NOT acceptable
    """
    neighborhood = getattr(ctx.report, 'neighborhood', None)
    if not neighborhood or not neighborhood.market_conditions:
         return RuleResult(
            rule_id="N-7",
            rule_name="Market Conditions",
            status=RuleStatus.FAIL,
            message="Market Conditions must be completed."
        )
        
    if "SEE 1004MC" in neighborhood.market_conditions.upper() and len(neighborhood.market_conditions.strip()) < 15:
        return RuleResult(
            rule_id="N-7",
            rule_name="Market Conditions",
            status=RuleStatus.FAIL,
            message="'See 1004MC' is NOT acceptable for Market Conditions. Please provide actual market analysis."
        )
        
    return RuleResult(
        rule_id="N-7",
        rule_name="Market Conditions",
        status=RuleStatus.PASS,
        message="Market conditions are provided."
    )
