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
import re


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


@rule(id="ST-1", name="Site Dimensions")
def validate_site_dimensions(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    text = _text(ctx)
    dimensions = getattr(site, 'dimensions', None) if site else None
    if not dimensions:
        match = re.search(r"Dimensions?\s+(\d[\d,]*(?:\.\d+)?)\s*(?:sf|sq\.?\s*ft|ac|acres)?", text, re.I)
        dimensions = match.group(1) if match else None
    if not dimensions:
        return RuleResult(rule_id="ST-1", rule_name="Site Dimensions",
                          status=RuleStatus.VERIFY,
                          message="Site dimensions not extracted. Verify dimensions are provided (e.g., 50 X 100).",
                          review_required=True, severity=RuleSeverity.STANDARD)
    return RuleResult(rule_id="ST-1", rule_name="Site Dimensions",
                      status=RuleStatus.PASS, message=f"Dimensions: {dimensions}",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-2", name="Site Area")
def validate_site_area(ctx: ValidationContext) -> RuleResult:
    site = getattr(ctx.report, 'site', None)
    area = getattr(site, 'area', None) if site else None
    unit = getattr(site, 'area_unit', None) if site else None
    if not area:
        match = re.search(r"\bArea\s+([\d,]+(?:\.\d+)?)\s*(sf|sq\.?\s*ft|ac|acres)?", _text(ctx), re.I)
        if match:
            area = match.group(1)
            unit = unit or match.group(2)
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
        match = re.search(r"\bShape\s+([A-Za-z][A-Za-z\s-]{2,30})\s+(?:View|Specific Zoning|Zoning)", _text(ctx), re.I)
        shape = match.group(1).strip() if match else None
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
        match = re.search(r"\bView\s+([A-Z][A-Za-z0-9;,\s-]{2,30})\s+(?:Specific Zoning|Zoning Compliance|Zoning|Legal)", _text(ctx), re.I)
        view = match.group(1).strip() if match else None
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
    text = _text(ctx)
    if not comp:
        if re.search(r"Zoning Compliance.*?\bLegal\b", text, re.I | re.S):
            comp = "Legal"
        elif re.search(r"Legal\s+Non-?Conforming", text, re.I):
            comp = "Legal Non-Conforming"
        elif re.search(r"No\s+Zoning", text, re.I):
            comp = "No Zoning"
        elif re.search(r"\bIllegal\b", text, re.I):
            comp = "Illegal"

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
        text = _text(ctx)
        if re.search(r"highest and best use.*?\bYes\b", text, re.I | re.S):
            hbu = True
        elif re.search(r"highest and best use.*?\bNo\b", text, re.I | re.S):
            hbu = False

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
    text = _text(ctx)
    if not any([has_water, has_sewer, has_elec, getattr(site, 'utilities_gas', False)]):
        has_elec = bool(re.search(r"\bElectricity\b|\bElectric\b", text, re.I))
        has_water = bool(re.search(r"\bWater\b", text, re.I))
        has_sewer = bool(re.search(r"Sanitary\s+Sewer|Sewer", text, re.I))
        has_gas = bool(re.search(r"\bGas\b", text, re.I))
    else:
        has_gas = getattr(site, 'utilities_gas', False)

    # If no utilities checked at all — VERIFY
    if not any([has_water, has_sewer, has_elec, has_gas]):
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

    text = ctx.raw_text or ""
    # Use actual model field: fema_flood_hazard (bool, default False)
    in_flood = getattr(site, 'fema_flood_hazard', False)
    flood_zone = getattr(site, 'fema_flood_zone', None)
    if not flood_zone:
        match = re.search(r"FEMA\s+Flood\s+Zone\s+([A-Z0-9]+)", text, re.I)
        flood_zone = match.group(1) if match else None

    if in_flood:
        return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area",
                          status=RuleStatus.WARNING,
                          appraisal_value=flood_zone or "Yes",
                          message="Property is in a FEMA flood zone. Comment on marketability impact required.",
                          action_item="Add commentary on flood zone impact on marketability.",
                          severity=RuleSeverity.STANDARD)

    if not flood_zone and "FEMA" not in text.upper() and "FLOOD" not in text.upper():
        return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area",
                          status=RuleStatus.VERIFY,
                          message="FEMA flood hazard fields were not extracted. Verify Yes/No, flood zone, map number, and map date.",
                          review_required=True,
                          severity=RuleSeverity.STANDARD)

    return RuleResult(rule_id="ST-8", rule_name="FEMA Flood Hazard Area",
                      status=RuleStatus.PASS,
                      message="FEMA flood hazard evidence indicates no special flood hazard area.",
                      severity=RuleSeverity.STANDARD)


@rule(id="ST-9", name="Utilities Typical for Market")
def validate_utilities_typical(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"utilities.*typical.*\bYes\b|typical for the area", text, re.I | re.S):
        return RuleResult(rule_id="ST-9", rule_name="Utilities Typical for Market",
                          status=RuleStatus.PASS,
                          message="Utilities typical-for-market evidence found.",
                          severity=RuleSeverity.STANDARD)
    if re.search(r"utilities.*typical.*\bNo\b", text, re.I | re.S):
        return RuleResult(rule_id="ST-9", rule_name="Utilities Typical for Market",
                          status=RuleStatus.WARNING,
                          message="Utilities are marked not typical. Verify required commentary.",
                          review_required=True, severity=RuleSeverity.STANDARD)
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
    text = ctx.raw_text or ""

    if adverse:
        return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions",
                          status=RuleStatus.WARNING,
                          message="Adverse site conditions indicated. Commentary must support response and adjustments should be reflected in sales grid.",
                          action_item="Verify commentary addresses all adverse conditions and grid adjustments.",
                          severity=RuleSeverity.STANDARD)

    if not re_search_adverse(text):
        return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions",
                          status=RuleStatus.VERIFY,
                          message="Adverse site conditions Yes/No field was not extracted. Verify easements, encroachments, environmental conditions, and external factors.",
                          review_required=True,
                          severity=RuleSeverity.STANDARD)

    return RuleResult(rule_id="ST-10", rule_name="Adverse Site Conditions",
                      status=RuleStatus.PASS,
                      message="Adverse site condition field evidence found with no issue indicated.",
                      severity=RuleSeverity.STANDARD)


def re_search_adverse(text: str) -> bool:
    import re
    return bool(re.search(r"adverse site|easement|encroachment|environmental|external factor", text or "", re.I))
