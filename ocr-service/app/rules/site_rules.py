"""
Site Section Rules (ST-1 through ST-10)
All validation rules for the Site section of appraisal reports.
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="ST-1", name="Site Dimensions")
def validate_site_dimensions(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not site.dimensions:
        return RuleResult(
            rule_id="ST-1",
            rule_name="Site Dimensions",
            status=RuleStatus.FAIL,
            message="Must list site dimensions (e.g., 50 X 100)."
        )
    return RuleResult(rule_id="ST-1", rule_name="Site Dimensions", status=RuleStatus.PASS, message="Site dimensions provided.")

@rule(id="ST-2", name="Site Area")
def validate_site_area(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not site.area:
        return RuleResult(
            rule_id="ST-2",
            rule_name="Site Area",
            status=RuleStatus.FAIL,
            message="Site area must be provided with unit designation (sf or ac)."
        )
    return RuleResult(rule_id="ST-2", rule_name="Site Area", status=RuleStatus.PASS, message="Site area provided.")

@rule(id="ST-3", name="Site Shape")
def validate_site_shape(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not site.shape:
        return RuleResult(
            rule_id="ST-3",
            rule_name="Site Shape",
            status=RuleStatus.FAIL,
            message="Site shape must be provided."
        )
    return RuleResult(rule_id="ST-3", rule_name="Site Shape", status=RuleStatus.PASS, message="Site shape provided.")

@rule(id="ST-4", name="View")
def validate_site_view(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not site.view:
        return RuleResult(
            rule_id="ST-4",
            rule_name="View",
            status=RuleStatus.FAIL,
            message="View must be provided and be UAD Compliant (Rating;Factor;Other)."
        )
    return RuleResult(rule_id="ST-4", rule_name="View", status=RuleStatus.PASS, message="Site view provided.")

@rule(id="ST-5", name="Zoning Classification and Compliance")
def validate_zoning_compliance(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not site.zoning_compliance:
        return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.FAIL,
            message="At least one zoning compliance checkbox MUST be marked."
        )
        
    comp_upper = site.zoning_compliance.upper()
    if comp_upper == "NO ZONING":
        return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.WARNING,
            message="Zoning Compliance is marked 'No Zoning'. Please comment if the subject can be rebuilt if destroyed."
        )
    elif comp_upper == "LEGAL NON-CONFORMING":
        return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.WARNING,
            message="Zoning Compliance is marked 'Legal Non-Conforming'. Please explain why and if subject can be rebuilt if destroyed over 50%."
        )
    elif comp_upper == "ILLEGAL":
         return RuleResult(
            rule_id="ST-5",
            rule_name="Zoning Classification and Compliance",
            status=RuleStatus.FAIL,
            message="Zoning Compliance is marked 'Illegal'. HOLD report for escalation."
        )
        
    return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance", status=RuleStatus.PASS, message="Zoning compliance is acceptable.")

@rule(id="ST-6", name="Highest and Best Use")
def validate_highest_best_use(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or site.highest_best_use_yes is None:
         return RuleResult(
            rule_id="ST-6",
            rule_name="Highest and Best Use",
            status=RuleStatus.FAIL,
            message="Highest and best use indicator is missing."
        )
        
    if not site.highest_best_use_yes:
        return RuleResult(
            rule_id="ST-6",
            rule_name="Highest and Best Use",
            status=RuleStatus.FAIL,
            message="Highest and Best Use is marked NO. HOLD report and notify immediately. Analysis MUST be provided."
        )
        
    return RuleResult(rule_id="ST-6", rule_name="Highest and Best Use", status=RuleStatus.PASS, message="Highest and Best Use marked Yes.")

@rule(id="ST-7", name="Utilities and Off-Site Improvements")
def validate_utilities(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")
        
    if site.private_well_septic:
        return RuleResult(
            rule_id="ST-7",
            rule_name="Utilities and Off-Site Improvements",
            status=RuleStatus.WARNING,
            message="Private well and septic system: please comment if it is typical and if having this feature has impact on marketability and value."
        )
        
    if site.private_street:
        return RuleResult(
            rule_id="ST-7",
            rule_name="Utilities and Off-Site Improvements",
            status=RuleStatus.WARNING,
            message='Subject has "Private Street"; please comment on condition and who is responsible for the maintenance.'
        )
        
    return RuleResult(rule_id="ST-7", rule_name="Utilities and Off-Site Improvements", status=RuleStatus.PASS, message="Utilities are correctly documented.")

@rule(id="ST-8", name="FEMA Flood Hazard Area")
def validate_flood_hazard(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")
        
    if site.in_fema_flood_area:
        return RuleResult(
            rule_id="ST-8",
            rule_name="FEMA Flood Hazard Area",
            status=RuleStatus.WARNING,
            message="The appraisal indicates the subject property is in a FEMA designated flood zone. Please comment if it will impact the marketability of the Subject."
        )
        
    return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area", status=RuleStatus.PASS, message="Flood hazard information provided.")

@rule(id="ST-9", name="Utilities Typical for Market")
def validate_utilities_typical(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or site.utilities_typical is None:
        return RuleResult(
            rule_id="ST-9",
            rule_name="Utilities Typical for Market",
            status=RuleStatus.FAIL,
            message="Utilities typical for market (Yes/No) MUST be checked."
        )
        
    if not site.utilities_typical:
         return RuleResult(
            rule_id="ST-9",
            rule_name="Utilities Typical for Market",
            status=RuleStatus.WARNING,
            message="Utilities are not typical for market. Commentary REQUIRED."
        )
        
    return RuleResult(rule_id="ST-9", rule_name="Utilities Typical for Market", status=RuleStatus.PASS, message="Utilities are typical for market.")

@rule(id="ST-10", name="Adverse Site Conditions")
def validate_adverse_site_conditions(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")
        
    if site.has_adverse_site_conditions:
         return RuleResult(
            rule_id="ST-10",
            rule_name="Adverse Site Conditions",
            status=RuleStatus.WARNING,
            message="Adverse site conditions exist. Comment MUST support the response and explain marketability impact."
        )
        
    return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions", status=RuleStatus.PASS, message="No adverse site conditions indicated.")
