"""
Site Section Rules (ST-1 through ST-10)
Validation rules for the Site section of appraisal reports.
"""
import re
from typing import Optional, List
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


def _check_addenda(ctx: ValidationContext, keywords: List[str]) -> bool:
    """Helper to check addenda for specific keywords."""
    if not ctx.addenda_text:
        return False
    addenda_lower = ctx.addenda_text.lower()
    return any(kw.lower() in addenda_lower for kw in keywords)


def _is_addenda_referenced(text: Optional[str]) -> bool:
    """Helper to check if 'See attached addenda' is mentioned."""
    if not text:
        return False
    patterns = [r"see\s+(?:attached\s+)?addend[um|a]", r"refer\s+to\s+(?:attached\s+)?addend[um|a]", r"see\s+attached"]
    return any(re.search(pattern, text.lower()) for pattern in patterns)


@rule(id="ST-1", name="Site Dimensions")
def validate_site_dimensions(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Dimensions
    Rule: Must list site dimensions (e.g., 50 X 100)
    If Irregular: Plat map MUST be provided with subject clearly marked
    """
    site = ctx.report.site
    if not site.dimensions:
        raise DataMissingException("Site Dimensions")

    # Appraisal logic: "See Plat Map" is common
    if "PLAT MAP" in site.dimensions.upper():
        if site.shape and site.shape.strip().upper() == "IRREGULAR":
            return RuleResult(
                rule_id="ST-1",
                rule_name="Site Dimensions",
                status=RuleStatus.PASS,
                message="Dimensions refers to Plat Map for an Irregular site, which is acceptable."
            )
        else:
            return RuleResult(
                rule_id="ST-1",
                rule_name="Site Dimensions",
                status=RuleStatus.WARNING,
                message="Dimensions refers to Plat Map. Please ensure the subject is clearly marked on the provided map."
            )

    # Basic format check (e.g., 50 x 100)
    if re.search(r'\d+\s*[xX*]\s*\d+', site.dimensions):
        return RuleResult(
            rule_id="ST-1",
            rule_name="Site Dimensions",
            status=RuleStatus.PASS,
            message=f"Site dimensions '{site.dimensions}' are provided."
        )

    return RuleResult(
        rule_id="ST-1",
        rule_name="Site Dimensions",
        status=RuleStatus.WARNING,
        message=f"Site dimensions '{site.dimensions}' may not be in standard format (e.g., 50 x 100). Please verify.",
        details={"dimensions": site.dimensions}
    )


@rule(id="ST-2", name="Site Area")
def validate_site_area(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Area
    Rule: Must include unit designation (sf or ac)
    If <1 Acre: Provide in square feet with "sf"
    If >=1 Acre: Provide in acreage with "ac"
    """
    site = ctx.report.site
    if site.area is None:
        raise DataMissingException("Site Area")
    if not site.area_unit:
        return RuleResult(
            rule_id="ST-2",
            rule_name="Site Area",
            status=RuleStatus.FAIL,
            message="Site area unit (sf or ac) is missing."
        )

    unit = site.area_unit.strip().lower()
    if unit not in ["sf", "ac"]:
        return RuleResult(
            rule_id="ST-2",
            rule_name="Site Area",
            status=RuleStatus.FAIL,
            message=f"Invalid site area unit: '{site.area_unit}'. Must be 'sf' or 'ac'."
        )

    # Validate based on size
    if unit == "sf" and site.area >= 43560:
        return RuleResult(
            rule_id="ST-2",
            rule_name="Site Area",
            status=RuleStatus.WARNING,
            message=f"Site area is {site.area} sf (>= 1 acre). Acreage ('ac') is typically preferred for sites over 1 acre."
        )
    elif unit == "ac" and site.area < 1:
        return RuleResult(
            rule_id="ST-2",
            rule_name="Site Area",
            status=RuleStatus.WARNING,
            message=f"Site area is {site.area} ac (< 1 acre). Square feet ('sf') is typically preferred for sites under 1 acre."
        )

    # Special check for acreage with farm keywords in addenda
    if unit == "ac" and site.area > 2:
        if _check_addenda(ctx, ["farm", "agricultural", "barn", "outbuilding", "working farm"]):
           return RuleResult(
                rule_id="ST-2",
                rule_name="Site Area",
                status=RuleStatus.PASS,
                message=f"Site area is {site.area} ac. Agricultural/Farm commentary was found in addenda."
            )

    return RuleResult(
        rule_id="ST-2",
        rule_name="Site Area",
        status=RuleStatus.PASS,
        message=f"Site area {site.area} {unit} is properly formatted."
    )


@rule(id="ST-3", name="Site Shape")
def validate_site_shape(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Shape
    Rule: Must be provided
    If Irregular: Plat map MUST be provided
    """
    site = ctx.report.site
    if not site.shape:
        return RuleResult(
            rule_id="ST-3",
            rule_name="Site Shape",
            status=RuleStatus.FAIL,
            message="Site shape is missing."
        )

    if site.shape.strip().upper() == "IRREGULAR":
        return RuleResult(
            rule_id="ST-3",
            rule_name="Site Shape",
            status=RuleStatus.WARNING,
            message="Site is Irregular. Please ensure a plat map is provided with the subject clearly marked."
        )

    return RuleResult(
        rule_id="ST-3",
        rule_name="Site Shape",
        status=RuleStatus.PASS,
        message=f"Site shape '{site.shape}' is provided."
    )


@rule(id="ST-4", name="View")
def validate_view(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: View
    Rule: Must be UAD Compliant (Rating;Factor;Other)
    """
    site = ctx.report.site
    if not site.view:
        return RuleResult(
            rule_id="ST-4",
            rule_name="View",
            status=RuleStatus.FAIL,
            message="View is missing."
        )

    # UAD Format: [A]|[N];[factor code];[other description]
    # e.g., N;Pstrl; or A;Wtr;
    uad_pattern = r'^[AN];[A-Za-z]+;'
    if not re.match(uad_pattern, site.view):
        return RuleResult(
            rule_id="ST-4",
            rule_name="View",
            status=RuleStatus.WARNING,
            message=f"View '{site.view}' may not be UAD compliant. Expected format like 'N;Pstrl;'.",
            details={"view": site.view}
        )

    return RuleResult(
        rule_id="ST-4",
        rule_name="View",
        status=RuleStatus.PASS,
        message=f"View '{site.view}' is UAD compliant."
    )


@rule(id="ST-5", name="Zoning Classification and Compliance")
def validate_zoning(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Zoning Classification, Zoning Description, Zoning Compliance
    Rule: At least one compliance checkbox MUST be marked
    If Legal Non-Conforming or No Zoning: Comment if subject can be rebuilt
    If Illegal: HOLD report
    """
    site = ctx.report.site
    if not site.zoning_classification:
        raise DataMissingException("Zoning Classification")
    if not site.zoning_compliance:
        return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.FAIL,
            message="Zoning Compliance checkbox is not marked."
        )

    comp = site.zoning_compliance.strip().upper()
    
    if "ILLEGAL" in comp:
        return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.FAIL,
            message="Site zoning is marked as ILLEGAL. HOLD report for immediate escalation.",
            review_required=True
        )

    if comp in ["NO ZONING", "LEGAL NONCONFORMING", "LEGAL NON-CONFORMING"]:
        # Check for rebuilding commentary
        keywords = ["rebuilt", "destroyed", "replacement", "reconstruction", "non-conforming", "50%"]
        found_in_addenda = _check_addenda(ctx, keywords)
        found_in_desc = site.zoning_description and any(kw in site.zoning_description.lower() for kw in keywords)
        
        if _is_addenda_referenced(site.zoning_description) and found_in_addenda:
            return RuleResult(
                rule_id="ST-5",
                rule_name="Zoning Classification and Compliance",
                status=RuleStatus.PASS,
                message=f"Zoning is {comp}. Rebuilding commentary was found in addenda."
            )
        
        if not (found_in_desc or found_in_addenda):
            msg = f"Zoning Compliance is marked '{site.zoning_compliance}'. Please explain why and comment if the subject can be rebuilt if destroyed."
            return RuleResult(
                rule_id="ST-5",
                rule_name="Zoning Classification and Compliance",
                status=RuleStatus.WARNING,
                message=msg
            )

    return RuleResult(
        rule_id="ST-5",
        rule_name="Zoning Classification and Compliance",
        status=RuleStatus.PASS,
        message=f"Zoning {site.zoning_classification} and compliance {site.zoning_compliance} are valid."
    )


@rule(id="ST-6", name="Highest and Best Use")
def validate_highest_best_use(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Highest and Best Use checkbox
    Expected: YES should be marked
    If NO: HOLD report
    """
    site = ctx.report.site
    if site.highest_and_best_use is None:
        return RuleResult(
            rule_id="ST-6",
            rule_name="Highest and Best Use",
            status=RuleStatus.FAIL,
            message="Highest and Best Use checkbox is not marked."
        )

    if not site.highest_and_best_use:
        return RuleResult(
            rule_id="ST-6",
            rule_name="Highest and Best Use",
            status=RuleStatus.FAIL,
            message="Highest and Best Use is marked 'NO'. HOLD report and notify immediately.",
            review_required=True
        )

    # Check for analysis if addenda is referenced
    if _is_addenda_referenced(site.highest_and_best_use_comment):
        keywords = ["physically possible", "legally permissible", "financially feasible", "most profitable", "four tests"]
        if _check_addenda(ctx, keywords):
            return RuleResult(
                rule_id="ST-6",
                rule_name="Highest and Best Use",
                status=RuleStatus.PASS,
                message="Highest and Best Use analysis found in addenda."
            )
        else:
             return RuleResult(
                rule_id="ST-6",
                rule_name="Highest and Best Use",
                status=RuleStatus.WARNING,
                message="Highest and Best Use refers to addenda, but standard analysis keywords (e.g., 'physically possible') were not found."
            )

    return RuleResult(
        rule_id="ST-6",
        rule_name="Highest and Best Use",
        status=RuleStatus.PASS,
        message="Existing use is marked as Highest and Best Use."
    )


@rule(id="ST-7", name="Utilities and Off-Site Improvements")
def validate_utilities(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Utilities and Off-Site Improvements
    Rule: If box is checked, description cannot be "None" or "N/A"
    Handle Private Well/Septic/Street
    """
    site = ctx.report.site
    issues = []
    
    # Check descriptions
    utils = [
        ("Electricity", site.utilities_electricity, site.utilities_electricity_other),
        ("Gas", site.utilities_gas, site.utilities_gas_other),
        ("Water", site.utilities_water, site.utilities_water_other),
        ("Sewer", site.utilities_sewer, site.utilities_sewer_other)
    ]
    
    for name, checked, other in utils:
        if checked and other and other.strip().upper() in ["NONE", "N/A", "NA"]:
            issues.append(f"{name} checkbox is checked but description is '{other}'.")

    # Private components logic
    private_utils = []
    if site.utilities_water_other and "WELL" in site.utilities_water_other.upper():
        private_utils.append("Private Well")
    if site.utilities_sewer_other and ("SEPTIC" in site.utilities_sewer_other.upper() or "CESSPOOL" in site.utilities_sewer_other.upper()):
        private_utils.append("Septic System")

    if private_utils:
        keywords = ["typical", "marketability", "impact", "value", "public access"]
        if not _check_addenda(ctx, keywords):
             issues.append(f"{' and '.join(private_utils)} detected. Please comment if typical for market and if there's any impact on marketability.")

    # Private Street
    if site.offsite_street_type and site.offsite_street_type.strip().upper() == "PRIVATE":
        if not _check_addenda(ctx, ["responsible", "maintenance", "condition"]):
            issues.append("Subject has 'Private Street'. Please comment on condition and maintenance responsibility.")

    if issues:
        return RuleResult(
            rule_id="ST-7",
            rule_name="Utilities and Off-Site Improvements",
            status=RuleStatus.WARNING,
            message="; ".join(issues)
        )

    return RuleResult(
        rule_id="ST-7",
        rule_name="Utilities and Off-Site Improvements",
        status=RuleStatus.PASS,
        message="Utilities and off-site improvements are valid."
    )


@rule(id="ST-8", name="FEMA Flood Hazard Area")
def validate_flood(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: FEMA info
    """
    site = ctx.report.site
    if site.fema_flood_hazard is None:
        raise DataMissingException("FEMA Flood Hazard Area (Yes/No)")

    if site.fema_flood_hazard:
        if not site.fema_flood_zone:
            return RuleResult(
                rule_id="ST-8",
                rule_name="FEMA Flood Hazard Area",
                status=RuleStatus.FAIL,
                message="Property is in a Flood Zone, but Zone ID is missing."
            )
        
        # Check commentary for marketability impact
        keywords = ["marketability", "impact", "flood", "hazard"]
        if not _check_addenda(ctx, keywords):
            return RuleResult(
                rule_id="ST-8",
                rule_name="FEMA Flood Hazard Area",
                status=RuleStatus.WARNING,
                message="Property is in a designated flood zone. Please comment if it will impact the marketability."
            )

    return RuleResult(
        rule_id="ST-8",
        rule_name="FEMA Flood Hazard Area",
        status=RuleStatus.PASS,
        message="FEMA Flood information is valid."
    )


@rule(id="ST-9", name="Utilities Typical for Market")
def validate_utilities_typical(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Typical for Market?
    """
    site = ctx.report.site
    if site.utilities_typical is None:
        return RuleResult(
            rule_id="ST-9",
            rule_name="Utilities Typical for Market",
            status=RuleStatus.FAIL,
            message="Utilities Typical for Market Yes/No toggle is skipped."
        )

    if not site.utilities_typical:
        desc = site.utilities_typical_description or ""
        if len(desc.strip()) < 10 and not _is_addenda_referenced(desc):
             return RuleResult(
                rule_id="ST-9",
                rule_name="Utilities Typical for Market",
                status=RuleStatus.WARNING,
                message="Utilities are marked as atypical for market, but substantive commentary is missing."
            )

    return RuleResult(
        rule_id="ST-9",
        rule_name="Utilities Typical for Market",
        status=RuleStatus.PASS,
        message="Utilities Typical for Market responded correctly."
    )


@rule(id="ST-10", name="Adverse Site Conditions")
def validate_adverse_conditions(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Adverse site conditions
    """
    site = ctx.report.site
    if site.adverse_site_conditions is None:
        return RuleResult(
            rule_id="ST-10",
            rule_name="Adverse Site Conditions",
            status=RuleStatus.FAIL,
            message="Adverse Site Conditions Yes/No toggle is skipped."
        )

    if site.adverse_site_conditions:
        desc = site.adverse_site_conditions_description or ""
        keywords = ["easement", "encroachment", "environmental", "land use", "impact", "drainage", "grading"]
        found_in_addenda = _check_addenda(ctx, keywords)
        
        if not (len(desc.strip()) > 15 or (_is_addenda_referenced(desc) and found_in_addenda)):
            return RuleResult(
                rule_id="ST-10",
                rule_name="Adverse Site Conditions",
                status=RuleStatus.WARNING,
                message="Adverse conditions are marked YES, but supporting commentary is missing or does not found relevant keywords like 'easement'."
            )

    return RuleResult(
        rule_id="ST-10",
        rule_name="Adverse Site Conditions",
        status=RuleStatus.PASS,
        message="Adverse Site Conditions responded correctly."
    )
