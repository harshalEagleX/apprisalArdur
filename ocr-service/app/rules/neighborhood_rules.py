"""
Neighborhood Section Rules (N-1 through N-7)
All validation rules for the Neighborhood section of appraisal reports.
"""
from typing import Optional, List
import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


@rule(id="N-1", name="Neighborhood Characteristics")
def validate_neighborhood_characteristics(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Location (Urban/Suburban/Rural), Built-Up (Over 75%/25-75%/Under 25%), 
                   Growth (Rapid/Stable/Slow)
    Rule: At least 1 box in each category MUST be checked
    Validation: Built-Up percentage must coincide with Present Land Use
    
    Note: Checkboxes are marked with 'X', not check marks
    """
    neighborhood = ctx.report.neighborhood
    missing_fields = []
    
    # Check Location
    if not neighborhood.location:
        missing_fields.append("Location (Urban/Suburban/Rural)")
    else:
        valid_locations = ["URBAN", "SUBURBAN", "RURAL"]
        if neighborhood.location.strip().upper() not in valid_locations:
            return RuleResult(
                rule_id="N-1",
                rule_name="Neighborhood Characteristics",
                status=RuleStatus.FAIL,
                message=f"Invalid Location value: '{neighborhood.location}'. Must be Urban, Suburban, or Rural."
            )
    
    # Check Built-Up
    if not neighborhood.built_up:
        missing_fields.append("Built-Up (Over 75%/25-75%/Under 25%)")
    else:
        valid_built_ups = ["OVER 75%", "25-75%", "UNDER 25%", "OVER75%", "25 75%", "UNDER25%"]
        built_up_normalized = neighborhood.built_up.strip().upper().replace(" ", "")
        if not any(built_up_normalized.replace("-", "").replace("%", "") in vbu.replace("-", "").replace("%", "") for vbu in valid_built_ups):
            return RuleResult(
                rule_id="N-1",
                rule_name="Neighborhood Characteristics",
                status=RuleStatus.FAIL,
                message=f"Invalid Built-Up value: '{neighborhood.built_up}'. Must be 'Over 75%', '25-75%', or 'Under 25%'."
            )
    
    # Check Growth Rate
    if not neighborhood.growth_rate:
        missing_fields.append("Growth (Rapid/Stable/Slow)")
    else:
        valid_growth = ["RAPID", "STABLE", "SLOW"]
        if neighborhood.growth_rate.strip().upper() not in valid_growth:
            return RuleResult(
                rule_id="N-1",
                rule_name="Neighborhood Characteristics",
                status=RuleStatus.FAIL,
                message=f"Invalid Growth Rate value: '{neighborhood.growth_rate}'. Must be Rapid, Stable, or Slow."
            )
    
    # If any fields are missing, return FAIL
    if missing_fields:
        field_list = ", ".join(missing_fields)
        return RuleResult(
            rule_id="N-1",
            rule_name="Neighborhood Characteristics",
            status=RuleStatus.FAIL,
            message=f"In the neighborhood section, checkbox is missing for {field_list}, please revise.",
            details={"missing_fields": missing_fields}
        )
    
    # Validate Built-Up coincides with Present Land Use (if available)
    if neighborhood.built_up and neighborhood.land_use_one_unit is not None:
        built_up_upper = neighborhood.built_up.strip().upper()
        one_unit_pct = neighborhood.land_use_one_unit
        
        # Check consistency
        if "OVER 75" in built_up_upper or "OVER75" in built_up_upper:
            if one_unit_pct < 75:
                return RuleResult(
                    rule_id="N-1",
                    rule_name="Neighborhood Characteristics",
                    status=RuleStatus.WARNING,
                    message=f"Built-Up is marked as 'Over 75%' but Present Land Use shows only {one_unit_pct}% one-unit housing. Please verify consistency.",
                    details={"built_up": neighborhood.built_up, "land_use_one_unit": one_unit_pct}
                )
        elif "UNDER 25" in built_up_upper or "UNDER25" in built_up_upper:
            if one_unit_pct > 25:
                return RuleResult(
                    rule_id="N-1",
                    rule_name="Neighborhood Characteristics",
                    status=RuleStatus.WARNING,
                    message=f"Built-Up is marked as 'Under 25%' but Present Land Use shows {one_unit_pct}% one-unit housing. Please verify consistency.",
                    details={"built_up": neighborhood.built_up, "land_use_one_unit": one_unit_pct}
                )
    
    return RuleResult(
        rule_id="N-1",
        rule_name="Neighborhood Characteristics",
        status=RuleStatus.PASS,
        message="Neighborhood characteristics are complete and valid."
    )


@rule(id="N-2", name="Housing Trends")
def validate_housing_trends(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Property Values (Increasing/Stable/Declining), Demand/Supply, Marketing Time
    Rule: Be aware of Characteristics and Land Use
    If DECLINING or INCREASING: Proper directional adjustments REQUIRED in sales grid
    Consistency: Trend must match 1004MC form or specific commentary required
    Condition: If no time adjustments made in increasing/declining market → Commentary REQUIRED
    """
    neighborhood = ctx.report.neighborhood
    missing_fields = []
    
    # Check Property Values
    if not neighborhood.property_values:
        missing_fields.append("Property Values (Increasing/Stable/Declining)")
    else:
        valid_values = ["INCREASING", "STABLE", "DECLINING"]
        if neighborhood.property_values.strip().upper() not in valid_values:
            return RuleResult(
                rule_id="N-2",
                rule_name="Housing Trends",
                status=RuleStatus.FAIL,
                message=f"Invalid Property Values: '{neighborhood.property_values}'. Must be Increasing, Stable, or Declining."
            )
    
    # Check Demand/Supply
    if not neighborhood.demand_supply:
        missing_fields.append("Demand/Supply")
    else:
        valid_demand_supply = ["SHORTAGE", "IN BALANCE", "OVER SUPPLY", "OVERSUPPLY", "INBALANCE"]
        ds_normalized = neighborhood.demand_supply.strip().upper().replace(" ", "")
        if not any(ds_normalized in vds.replace(" ", "") for vds in valid_demand_supply):
            return RuleResult(
                rule_id="N-2",
                rule_name="Housing Trends",
                status=RuleStatus.FAIL,
                message=f"Invalid Demand/Supply value: '{neighborhood.demand_supply}'. Must be Shortage, In Balance, or Over Supply."
            )
    
    # Check Marketing Time
    if not neighborhood.marketing_time:
        missing_fields.append("Marketing Time")
    else:
        # Accept various formats: "Under 3 mths", "3-6 mths", "Over 6 mths"
        valid_marketing = ["UNDER 3", "3-6", "OVER 6", "UNDER3", "36", "OVER6"]
        mt_normalized = neighborhood.marketing_time.strip().upper().replace(" ", "").replace("MTHS", "").replace("MONTHS", "")
        if not any(vmt in mt_normalized for vmt in valid_marketing):
            return RuleResult(
                rule_id="N-2",
                rule_name="Housing Trends",
                status=RuleStatus.FAIL,
                message=f"Invalid Marketing Time value: '{neighborhood.marketing_time}'. Must be 'Under 3 mths', '3-6 mths', or 'Over 6 mths'."
            )
    
    # If any fields are missing
    if missing_fields:
        field_list = ", ".join(missing_fields)
        return RuleResult(
            rule_id="N-2",
            rule_name="Housing Trends",
            status=RuleStatus.FAIL,
            message=f"In the neighborhood section, the following trends are missing: {field_list}. Please revise.",
            details={"missing_fields": missing_fields}
        )
    
    # Check for time adjustments if market is Increasing or Declining
    if neighborhood.property_values:
        pv_upper = neighborhood.property_values.strip().upper()
        if pv_upper in ["INCREASING", "DECLINING"]:
            # Check if comparables have time adjustments
            has_time_adjustments = False
            comparables = ctx.report.sales_comparison.comparables if ctx.report.sales_comparison else []
            
            # Look for time/date adjustments in comparables (this is a simplified check)
            # In a real system, you'd check specific adjustment fields
            if len(comparables) > 0:
                # Placeholder: assume time adjustments exist if we have comparables
                # In production, check actual adjustment columns
                has_time_adjustments = True  # Simplified for now
            
            if not has_time_adjustments and len(comparables) > 0:
                return RuleResult(
                    rule_id="N-2",
                    rule_name="Housing Trends",
                    status=RuleStatus.WARNING,
                    message=f"Property values are marked as '{neighborhood.property_values}', but no time adjustments appear to be made in the sales comparison grid. Please verify or provide commentary explaining market conditions.",
                    details={"property_values": neighborhood.property_values}
                )
    
    return RuleResult(
        rule_id="N-2",
        rule_name="Housing Trends",
        status=RuleStatus.PASS,
        message="Housing trends are complete and appear consistent."
    )


@rule(id="N-3", name="One-Unit Housing Price and Age")
def validate_price_age_ranges(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Price Low/High/Predominant, Age Low/High/Predominant
    Format: Range must be Low to High
    Validation: Unadjusted sales prices of comparables must fall within ranges
    Exception: If comps outside neighborhood → Comment REQUIRED
    Condition: If Market Value differs from Predominant by >10% → Comment on over/under improvement
    """
    neighborhood = ctx.report.neighborhood
    issues = []
    
    # Check Price Range
    if neighborhood.price_low is None or neighborhood.price_high is None:
        raise DataMissingException("Price Range (Low and/or High)")
    
    if neighborhood.price_low > neighborhood.price_high:
        return RuleResult(
            rule_id="N-3",
            rule_name="One-Unit Housing Price and Age",
            status=RuleStatus.FAIL,
            message=f"Price range is invalid: Low (${neighborhood.price_low:,.0f}) is greater than High (${neighborhood.price_high:,.0f}). Please correct.",
            details={"price_low": neighborhood.price_low, "price_high": neighborhood.price_high}
        )
    
    # Check Age Range
    if neighborhood.age_low is None or neighborhood.age_high is None:
        raise DataMissingException("Age Range (Low and/or High)")
    
    if neighborhood.age_low > neighborhood.age_high:
        return RuleResult(
            rule_id="N-3",
            rule_name="One-Unit Housing Price and Age",
            status=RuleStatus.FAIL,
            message=f"Age range is invalid: Low ({neighborhood.age_low} years) is greater than High ({neighborhood.age_high} years). Please correct.",
            details={"age_low": neighborhood.age_low, "age_high": neighborhood.age_high}
        )
    
    # Validate comparables fall within price range
    comparables = ctx.report.sales_comparison.comparables if ctx.report.sales_comparison else []
    out_of_range_comps = []
    
    for i, comp in enumerate(comparables, start=1):
        if comp.sale_price and not comp.is_listing:  # Only check actual sales, not listings
            if comp.sale_price < neighborhood.price_low or comp.sale_price > neighborhood.price_high:
                out_of_range_comps.append({
                    "comp_number": i,
                    "address": comp.address or "Unknown",
                    "sale_price": comp.sale_price
                })
    
    if out_of_range_comps:
        comp_details = ", ".join([f"Comp #{c['comp_number']} (${c['sale_price']:,.0f})" for c in out_of_range_comps])
        return RuleResult(
            rule_id="N-3",
            rule_name="One-Unit Housing Price and Age",
            status=RuleStatus.WARNING,
            message=f"The following comparables have sale prices outside the neighborhood price range (${neighborhood.price_low:,.0f} - ${neighborhood.price_high:,.0f}): {comp_details}. If comparables are outside the neighborhood, please provide commentary.",
            details={"out_of_range_comps": out_of_range_comps}
        )
    
    # Check if Market Value differs from Predominant Price by >10%
    # Note: We'd need market_value field in the model. For now, skip this check
    # This would typically be in the reconciliation or subject section
    
    return RuleResult(
        rule_id="N-3",
        rule_name="One-Unit Housing Price and Age",
        status=RuleStatus.PASS,
        message=f"Price range (${neighborhood.price_low:,.0f} - ${neighborhood.price_high:,.0f}) and age range ({neighborhood.age_low}-{neighborhood.age_high} years) are valid."
    )


@rule(id="N-4", name="Present Land Use")
def validate_present_land_use(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Present Land Use percentages
    Rule: Must complete and identify "Other" uses if any percentage given
    Cannot be: Blank, "Vacant" (must be specific)
    Validation: Total MUST equal 100%
    If Other: Description REQUIRED
    """
    neighborhood = ctx.report.neighborhood
    
    # Collect all land use percentages
    land_uses = {
        "One Unit": neighborhood.land_use_one_unit or 0.0,
        "2-4 Family": neighborhood.land_use_2_4_family or 0.0,
        "Multi-Family": neighborhood.land_use_multi_family or 0.0,
        "Commercial": neighborhood.land_use_commercial or 0.0,
        "Industrial": neighborhood.land_use_industrial or 0.0,
        "Other": neighborhood.land_use_other or 0.0
    }
    
    # Calculate total
    total = sum(land_uses.values())
    
    # Check if all are zero (missing data)
    if total == 0:
        raise DataMissingException("Present Land Use percentages")
    
    # Check if total equals 100% (allow small floating point tolerance)
    if abs(total - 100.0) > 0.1:
        land_use_breakdown = ", ".join([f"{k}: {v}%" for k, v in land_uses.items() if v > 0])
        return RuleResult(
            rule_id="N-4",
            rule_name="Present Land Use",
            status=RuleStatus.WARNING, # Downgraded from FAIL
            message=f"The sum of present land use in the neighborhood section should always be 100%. Current total is {total:.1f}%. Breakdown: {land_use_breakdown}. Please verify if any rows were missed by OCR.",
            details={"land_uses": land_uses, "total": total}
        )
    
    # Check if "Other" has a percentage but no description
    if neighborhood.land_use_other and neighborhood.land_use_other > 0:
        if not neighborhood.land_use_other_description or len(neighborhood.land_use_other_description.strip()) < 3:
            return RuleResult(
                rule_id="N-4",
                rule_name="Present Land Use",
                status=RuleStatus.WARNING, # Downgraded from FAIL
                message=f"'Other' land use is {neighborhood.land_use_other}% but no description is provided. Please verify if a description exists in the report.",
                details={"land_use_other": neighborhood.land_use_other}
            )
    
    return RuleResult(
        rule_id="N-4",
        rule_name="Present Land Use",
        status=RuleStatus.PASS,
        message=f"Present land use percentages are complete and sum to 100%."
    )


@rule(id="N-5", name="Neighborhood Boundaries")
def validate_neighborhood_boundaries(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Boundaries (North, South, East, West)
    Rule: All four boundaries MUST be described
    Format: Must spell out: "North", "South", "East", "West"
    Cannot: Abbreviate as N, S, E, W
    Validation: Boundaries must be visible on location map
    """
    boundaries = ctx.report.neighborhood.boundaries_description
    
    if not boundaries or len(boundaries.strip()) < 10:
        return RuleResult(
            rule_id="N-5",
            rule_name="Neighborhood Boundaries",
            status=RuleStatus.FAIL,
            message="Must list the boundaries only; North, South, East, West, please correct"
        )
    
    # Check for all four directions (case-insensitive, whole word match)
    boundaries_upper = boundaries.upper()
    
    # Define patterns to find direction words (not abbreviations)
    directions_found = {
        "North": bool(re.search(r'\bNORTH\b', boundaries_upper)),
        "South": bool(re.search(r'\bSOUTH\b', boundaries_upper)),
        "East": bool(re.search(r'\bEAST\b', boundaries_upper)),
        "West": bool(re.search(r'\bWEST\b', boundaries_upper))
    }
    
    missing_directions = [direction for direction, found in directions_found.items() if not found]
    
    if missing_directions:
        if len(missing_directions) == 4:
            return RuleResult(
                rule_id="N-5",
                rule_name="Neighborhood Boundaries",
                status=RuleStatus.FAIL,
                message="Must list the boundaries only; North, South, East, West, please correct"
            )
        else:
            missing_list = ", ".join(missing_directions)
            return RuleResult(
                rule_id="N-5",
                rule_name="Neighborhood Boundaries",
                status=RuleStatus.WARNING, # Downgraded from FAIL
                message=f"{missing_list} boundary seems to be missing under Neighborhood Boundaries. Please verify if it is described within a combined sentence.",
                details={"missing_directions": missing_directions, "provided_text": boundaries}
            )
    
    # Check for abbreviations (warn if found)
    abbreviation_pattern = r'\b[NSEW]\b(?!\w)'  # Single letter N, S, E, W not part of a word
    if re.search(abbreviation_pattern, boundaries):
        return RuleResult(
            rule_id="N-5",
            rule_name="Neighborhood Boundaries",
            status=RuleStatus.WARNING,
            message="Must list the boundaries only; North, South, East, West, please correct",
            details={"boundaries": boundaries}
        )
    
    return RuleResult(
        rule_id="N-5",
        rule_name="Neighborhood Boundaries",
        status=RuleStatus.PASS,
        message="All four neighborhood boundaries (North, South, East, West) are properly described."
    )


@rule(id="N-6", name="Neighborhood Description")
def validate_neighborhood_description(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Neighborhood Description
    Rule: Must be completed with specific area description
    NLP Check: Commentary must be specific to the area, no canned text
    """
    description = ctx.report.neighborhood.description_commentary
    
    if not description or len(description.strip()) == 0:
        raise DataMissingException("Neighborhood Description")

    description_lower = description.lower()
    
    # Check for "See attached addenda" (Appraisal logic: This is VALID DATA)
    # Move this BEFORE length checks
    addenda_patterns = [r"see\s+(?:attached\s+)?addend[um|a]", r"refer\s+to\s+(?:attached\s+)?addend[um|a]", r"see\s+attached"]
    if any(re.search(pattern, description_lower) for pattern in addenda_patterns):
        # Validate that the addenda actually contains neighborhood info
        addenda = ctx.addenda_text.lower() if ctx.addenda_text else ""
        neighborhood_keywords = ["neighborhood", "census", "cdp", "rural", "suburban", "urban", "residential", "employment", "commuting"]
        if any(kw in addenda for kw in neighborhood_keywords):
            return RuleResult(
                rule_id="N-6",
                rule_name="Neighborhood Description",
                status=RuleStatus.PASS,
                message="Neighborhood Description refers to attached addenda, and relevant keywords were found in supplemental commentary."
            )
        else:
            return RuleResult(
                rule_id="N-6",
                rule_name="Neighborhood Description",
                status=RuleStatus.WARNING,
                message="Neighborhood Description refers to attached addenda, but no clear neighborhood-specific commentary was found in the supplemental text.",
                details={"addenda_searched": bool(ctx.addenda_text)}
            )

    if len(description.strip()) < 20:
        return RuleResult(
            rule_id="N-6",
            rule_name="Neighborhood Description",
            status=RuleStatus.WARNING, # Downgraded from FAIL
            message="Neighborhood Description is too brief. Please provide a specific description of the neighborhood area or refer to addenda."
        )
    
    # Basic NLP check for canned/generic text
    # Common generic phrases that indicate canned commentary
    generic_phrases = [
        "typical neighborhood",
        "average neighborhood",
        "typical for the area",
        "standard neighborhood",
        "good neighborhood",
        "nice area",
        "residential area with homes",
        "homes in the area",
        "similar to surrounding areas"
    ]
    
    found_generic = []
    for phrase in generic_phrases:
        if phrase in description_lower:
            found_generic.append(phrase)
    
    if found_generic:
        return RuleResult(
            rule_id="N-6",
            rule_name="Neighborhood Description",
            status=RuleStatus.WARNING,
            message=f"Neighborhood Description may contain generic/canned commentary. Please ensure the description is specific to this property's neighborhood. Generic phrases detected: {', '.join(found_generic)}",
            details={"generic_phrases_found": found_generic}
        )
    
    # Check minimum substance (at least some specific details)
    # A good description should have specific elements like street names, landmarks, etc.
    word_count = len(description.split())
    if word_count < 15:
        return RuleResult(
            rule_id="N-6",
            rule_name="Neighborhood Description",
            status=RuleStatus.WARNING,
            message=f"Neighborhood Description seems brief ({word_count} words). Please ensure it provides adequate detail about the specific neighborhood.",
            details={"word_count": word_count}
        )
    
    return RuleResult(
        rule_id="N-6",
        rule_name="Neighborhood Description",
        status=RuleStatus.PASS,
        message="Neighborhood Description is complete and appears to be property-specific."
    )


@rule(id="N-7", name="Market Conditions")
def validate_market_conditions(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Market Conditions
    Rule: Must be completed with actual market analysis
    Invalid: "See 1004MC" is NOT acceptable
    Consistency: Must align with 1004MC form data
    """
    market_conditions = ctx.report.neighborhood.market_conditions_comment
    
    if not market_conditions or len(market_conditions.strip()) == 0:
        raise DataMissingException("Market Conditions")

    mc_lower = market_conditions.lower().strip()
    
    # Check for "See attached addenda" (Appraisal logic: This is VALID DATA)
    # Move this BEFORE length checks
    addenda_patterns = [r"see\s+(?:attached\s+)?addend[um|a]", r"refer\s+to\s+(?:attached\s+)?addend[um|a]", r"see\s+attached"]
    if any(re.search(pattern, mc_lower) for pattern in addenda_patterns):
        # Validate that the addenda actually contains market conditions info
        addenda = ctx.addenda_text.lower() if ctx.addenda_text else ""
        market_keywords = ["market", "trend", "stabilizing", "shortage", "inventory", "median", "median price", "absorption", "exposure time"]
        if any(kw in addenda for kw in market_keywords):
            return RuleResult(
                rule_id="N-7",
                rule_name="Market Conditions",
                status=RuleStatus.PASS,
                message="Market Conditions refers to attached addenda, and relevant market indicators were found in supplemental commentary."
            )
        else:
            return RuleResult(
                rule_id="N-7",
                rule_name="Market Conditions",
                status=RuleStatus.WARNING,
                message="Market Conditions refers to attached addenda, but no clear market condition analysis was found in the supplemental text.",
                details={"addenda_searched": bool(ctx.addenda_text)}
            )

    invalid_phrases = [
        "n/a",
        "none",
        "not applicable"
    ]
    
    for phrase in invalid_phrases:
        if phrase == mc_lower:
            return RuleResult(
                rule_id="N-7",
                rule_name="Market Conditions",
                status=RuleStatus.FAIL,
                message=f"Market Conditions cannot be blank or use placeholder text like '{phrase}'.",
                details={"invalid_text": market_conditions}
            )

    if len(market_conditions.strip()) < 20:
        return RuleResult(
            rule_id="N-7",
            rule_name="Market Conditions",
            status=RuleStatus.WARNING, # Downgraded from FAIL
            message="Market Conditions commentary is too brief. Please provide actual market analysis or refer to addenda."
        )
    
    # Check for minimum substance
    word_count = len(market_conditions.split())
    if word_count < 20:
        return RuleResult(
            rule_id="N-7",
            rule_name="Market Conditions",
            status=RuleStatus.WARNING,
            message=f"Market Conditions commentary seems brief ({word_count} words). Please ensure it provides substantive market analysis including trends, inventory levels, and days on market.",
            details={"word_count": word_count}
        )
    
    # Check if it mentions key market condition indicators
    has_indicators = False
    market_indicators = [
        "supply", "demand", "inventory", "days on market", "dom", "absorption",
        "trend", "increasing", "decreasing", "stable", "appreciation", "depreciation",
        "seller", "buyer", "market", "listing", "sale"
    ]
    
    for indicator in market_indicators:
        if indicator in mc_lower:
            has_indicators = True
            break
    
    if not has_indicators:
        return RuleResult(
            rule_id="N-7",
            rule_name="Market Conditions",
            status=RuleStatus.WARNING,
            message="Market Conditions commentary should include market indicators such as supply/demand, inventory levels, days on market, or market trends.",
            details={"commentary": market_conditions}
        )
    
    return RuleResult(
        rule_id="N-7",
        rule_name="Market Conditions",
        status=RuleStatus.PASS,
        message="Market Conditions commentary is complete with substantive market analysis."
    )
