"""
Site Section Rules (ST-1 through ST-10)

Uses getattr with defaults throughout so rules return VERIFY (not crash)
when site-section fields haven't been extracted yet.

SiteSection model fields (appraisal.py):
  dimensions, area, area_unit, shape, view
  zoning_classification, zoning_compliance
  highest_and_best_use (bool)
  utilities_electricity, utilities_gas, utilities_water, utilities_sewer (bool)
  fema_flood_hazard (bool), fema_flood_zone, fema_map_date
  adverse_site_conditions (bool)
"""

from app.rule_engine.engine import rule, RuleStatus, RuleResult, RuleSeverity, DataMissingException
from app.models.appraisal import ValidationContext


@rule(id="ST-1", name="Site Dimensions")
def validate_site_dimensions(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site or not getattr(site, 'dimensions', None):
        return RuleResult(rule_id="ST-1", rule_name="Site Dimensions",
                          status=RuleStatus.VERIFY,
                          message="Site dimensions not extracted. Verify dimensions are provided (e.g., 50 X 100).",
                          review_required=True, severity=RuleSeverity.STANDARD)
    return RuleResult(rule_id="ST-1", rule_name="Site Dimensions",
                      status=RuleStatus.PASS, message=f"Dimensions: {site.dimensions}",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-2", name="Site Area")
def validate_site_area(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    area = getattr(site, 'area', None) if site else None
    unit = getattr(site, 'area_unit', None) if site else None
    if not area:
        return RuleResult(rule_id="ST-2", rule_name="Site Area",
                          status=RuleStatus.VERIFY,
                          message="Site area not extracted. Verify area is provided with unit (sf or ac).",
                          review_required=True, severity=RuleSeverity.STANDARD)
    return RuleResult(rule_id="ST-2", rule_name="Site Area",
                      status=RuleStatus.PASS,
                      message=f"Site area: {area} {unit or ''}".strip(),
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-3", name="Site Shape")
def validate_site_shape(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    shape = getattr(site, 'shape', None) if site else None
    if not shape:
        return RuleResult(rule_id="ST-3", rule_name="Site Shape",
                          status=RuleStatus.VERIFY,
                          message="Site shape not extracted. Verify shape is provided.",
                          review_required=True, severity=RuleSeverity.STANDARD)
    return RuleResult(rule_id="ST-3", rule_name="Site Shape",
                      status=RuleStatus.PASS, message=f"Shape: {shape}",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-4", name="View")
def validate_site_view(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    view = getattr(site, 'view', None) if site else None
    if not view:
        return RuleResult(rule_id="ST-4", rule_name="View",
                          status=RuleStatus.VERIFY,
                          message="View not extracted. Verify UAD compliant view (Rating;Factor).",
                          review_required=True, severity=RuleSeverity.ADVISORY)
    return RuleResult(rule_id="ST-4", rule_name="View",
                      status=RuleStatus.PASS, message=f"View: {view}",
                      severity=RuleSeverity.ADVISORY)


@rule(id="ST-5", name="Zoning Classification and Compliance")
def validate_zoning_compliance(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    comp = getattr(site, 'zoning_compliance', None) if site else None

    if not comp:
        return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance",
                          status=RuleStatus.VERIFY,
                          message="Zoning compliance not extracted. Verify at least one checkbox is marked.",
                          review_required=True, severity=RuleSeverity.STANDARD)

    comp_upper = comp.upper()
    if "NO ZONING" in comp_upper:
        return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance",
                          status=RuleStatus.WARNING, appraisal_value=comp,
                          message="Zoning is 'No Zoning'. Comment required: can subject be rebuilt if destroyed?",
                          severity=RuleSeverity.STANDARD)
    if "NON-CONFORMING" in comp_upper or "NONCONFORMING" in comp_upper:
        return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance",
                          status=RuleStatus.WARNING, appraisal_value=comp,
                          message="Zoning is 'Legal Non-Conforming'. Explain why and rebuild rights.",
                          severity=RuleSeverity.STANDARD)
    if "ILLEGAL" in comp_upper:
        return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance",
                          status=RuleStatus.FAIL, appraisal_value=comp,
                          message="Zoning is 'Illegal'. HOLD report for escalation.",
                          severity=RuleSeverity.BLOCKING)

    return RuleResult(rule_id="ST-5", rule_name="Zoning Classification and Compliance",
                      status=RuleStatus.PASS, message=f"Zoning compliance: {comp}",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-6", name="Highest and Best Use")
def validate_highest_best_use(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    # Model field is: highest_and_best_use (bool or None)
    hbu = getattr(site, 'highest_and_best_use', None) if site else None

    if hbu is None:
        return RuleResult(rule_id="ST-6", rule_name="Highest and Best Use",
                          status=RuleStatus.VERIFY,
                          message="Highest and Best Use not extracted. Verify Yes/No is checked.",
                          review_required=True, severity=RuleSeverity.BLOCKING)
    if hbu is False:
        return RuleResult(rule_id="ST-6", rule_name="Highest and Best Use",
                          status=RuleStatus.FAIL,
                          message="Highest and Best Use is marked NO. HOLD report — analysis MUST be provided.",
                          severity=RuleSeverity.BLOCKING)

    return RuleResult(rule_id="ST-6", rule_name="Highest and Best Use",
                      status=RuleStatus.PASS, message="Highest and Best Use: Yes.",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-7", name="Utilities and Off-Site Improvements")
def validate_utilities(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")

    # Use actual model fields (not private_well_septic / private_street which don't exist)
    has_water  = getattr(site, 'utilities_water', False)
    has_sewer  = getattr(site, 'utilities_sewer', False)
    has_elec   = getattr(site, 'utilities_electricity', False)

    # If no utilities checked at all — VERIFY
    if not any([has_water, has_sewer, has_elec,
                getattr(site, 'utilities_gas', False)]):
        return RuleResult(rule_id="ST-7", rule_name="Utilities and Off-Site Improvements",
                          status=RuleStatus.VERIFY,
                          message="Utilities not extracted. Verify electricity, gas, water, sewer are documented.",
                          review_required=True, severity=RuleSeverity.STANDARD)

    return RuleResult(rule_id="ST-7", rule_name="Utilities and Off-Site Improvements",
                      status=RuleStatus.PASS,
                      message="Utilities are documented.",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-8", name="FEMA Flood Hazard Area")
def validate_flood_hazard(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")

    # Use actual model field: fema_flood_hazard (bool, default False)
    in_flood = getattr(site, 'fema_flood_hazard', False)
    flood_zone = getattr(site, 'fema_flood_zone', None)

    if in_flood:
        return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area",
                          status=RuleStatus.WARNING,
                          appraisal_value=flood_zone or "Yes",
                          message="Property is in a FEMA flood zone. Comment on marketability impact required.",
                          action_item="Add commentary on flood zone impact on marketability.",
                          severity=RuleSeverity.STANDARD)

    return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area",
                      status=RuleStatus.PASS,
                      message="Property is not in a FEMA special flood hazard area.",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-9", name="Utilities Typical for Market")
def validate_utilities_typical(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    # SiteSection doesn't have utilities_typical — return VERIFY (data not yet extracted)
    return RuleResult(rule_id="ST-9", rule_name="Utilities Typical for Market",
                      status=RuleStatus.VERIFY,
                      message="Utilities typical for market (Yes/No) could not be extracted. Verify manually.",
                      review_required=True, severity=RuleSeverity.STANDARD)


@rule(id="ST-10", name="Adverse Site Conditions")
def validate_adverse_site_conditions(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    if not site:
        raise DataMissingException("Site Section")

    # Use actual model field: adverse_site_conditions (bool, default False)
    adverse = getattr(site, 'adverse_site_conditions', False)

    if adverse:
        return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions",
                          status=RuleStatus.WARNING,
                          message="Adverse site conditions indicated. Commentary must support response and adjustments should be reflected in sales grid.",
                          action_item="Verify commentary addresses all adverse conditions and grid adjustments.",
                          severity=RuleSeverity.STANDARD)

    return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions",
                      status=RuleStatus.PASS,
                      message="No adverse site conditions indicated.",
                      severity=RuleSeverity.STANDARD)
