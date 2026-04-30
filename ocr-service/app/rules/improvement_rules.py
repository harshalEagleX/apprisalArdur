"""
Improvement Section Rules (I-1 through I-13)

These rules use the actual AppraisalReport.improvements model. When the current
extractors do not expose enough data for a checklist item, the rule returns
VERIFY instead of a misleading PASS.
"""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult, RuleSeverity, DataMissingException
from app.models.appraisal import ValidationContext


def _improvements(ctx: ValidationContext):
    imp = getattr(ctx.report, "improvements", None)
    if not imp:
        raise DataMissingException("Improvement Section")
    return imp


def _raw(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _verify(rule_id: str, name: str, message: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=name,
        status=RuleStatus.VERIFY,
        message=message,
        review_required=True,
        severity=RuleSeverity.STANDARD,
    )


@rule(id="I-1", name="General Description")
def validate_general_description(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    text = _raw(ctx)
    missing = []
    if imp.units_count is None and not re.search(r"\bUnits?\b.*(?:One|1)", text, re.I):
        missing.append("Units")
    if not imp.design_style and not re.search(r"Design\s*\(Style\)\s+[A-Za-z]", text, re.I):
        missing.append("Design Style")
    if not imp.year_built and not re.search(r"Year\s+Built\s+\d{4}", text, re.I):
        missing.append("Year Built")
    if imp.effective_age is None and not re.search(r"Effective\s+Age\s*\(Yrs\)?\s*\d+", text, re.I):
        missing.append("Effective Age")
    if missing:
        return _verify("I-1", "General Description", f"Improvement general description is incomplete or not extracted: {', '.join(missing)}.")
    return RuleResult(rule_id="I-1", rule_name="General Description", status=RuleStatus.PASS, message="Improvement general description fields are present.")


@rule(id="I-2", name="Foundation")
def validate_foundation(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    text = _raw(ctx)
    if not imp.foundation_type and not re.search(r"Concrete\s+Slab|Crawl\s+Space|Basement|Foundation", text, re.I):
        return _verify("I-2", "Foundation", "Foundation type/details not extracted. Verify slab, crawl space, basement, sump pump, and moisture/settlement fields as applicable.")
    return RuleResult(rule_id="I-2", rule_name="Foundation", status=RuleStatus.PASS, message=f"Foundation evidence found: {imp.foundation_type or 'OCR text'}.")


@rule(id="I-3", name="Exterior Description")
def validate_exterior_description(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    text = _raw(ctx)
    missing = []
    if not imp.exterior_walls and not re.search(r"Exterior\s+Walls?\s+[A-Za-z]", text, re.I):
        missing.append("Exterior Walls")
    if not imp.roof_surface and not re.search(r"Roof\s+Surface\s+[A-Za-z]", text, re.I):
        missing.append("Roof Surface")
    if missing:
        return _verify("I-3", "Exterior Description", f"Exterior description fields not extracted: {', '.join(missing)}.")
    return RuleResult(rule_id="I-3", rule_name="Exterior Description", status=RuleStatus.PASS, message="Exterior walls and roof surface are documented.")


@rule(id="I-4", name="Interior Description")
def validate_interior_description(ctx: ValidationContext) -> RuleResult:
    text = _raw(ctx)
    if not re.search(r"\b(Floors?|Walls?|Trim/Finish|Bath\s+Floor|Bath\s+Wainscot|Interior)\b", text, re.I):
        return _verify("I-4", "Interior Description", "Interior finish fields were not extracted. Verify floors, walls, trim/finish, bath floor, and bath wainscot are completed.")
    return RuleResult(rule_id="I-4", rule_name="Interior Description", status=RuleStatus.PASS, message="Interior description evidence found in OCR text.")


@rule(id="I-5", name="Utilities")
def validate_improvement_utilities(ctx: ValidationContext) -> RuleResult:
    if ctx.report.subject.utilities_on is None and not re.search(r"utilities?\s+(?:and appliances\s+)?(?:were\s+)?(?:on|off)|all utilities.*were on", _raw(ctx), re.I):
        return RuleResult(rule_id="I-5", rule_name="Utilities", status=RuleStatus.FAIL, message="Must state if utilities were ON at time of inspection.")
    return RuleResult(rule_id="I-5", rule_name="Utilities", status=RuleStatus.PASS, message="Utilities status is documented or indicated.")


@rule(id="I-6", name="Appliances")
def validate_appliances(ctx: ValidationContext) -> RuleResult:
    text = _raw(ctx)
    if not re.search(r"\b(appliance|dishwasher|range|oven|microwave|disposal|refrigerator)\b", text, re.I):
        return _verify("I-6", "Appliances", "Built-in appliances and operational statement were not extracted. Verify built-in items only and FHA operation statement if applicable.")
    return RuleResult(rule_id="I-6", rule_name="Appliances", status=RuleStatus.PASS, message="Appliance evidence found in OCR text.")


@rule(id="I-7", name="Above Grade Room Count")
def validate_room_count(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    missing = []
    if imp.total_rooms is None:
        missing.append("Total Rooms")
    if imp.bedrooms is None:
        missing.append("Bedrooms")
    if imp.baths is None:
        missing.append("Baths")
    if imp.gla is None:
        missing.append("GLA")
    if missing:
        return _verify("I-7", "Above Grade Room Count", f"Above-grade room count/GLA not fully extracted: {', '.join(missing)}.")
    return RuleResult(rule_id="I-7", rule_name="Above Grade Room Count", status=RuleStatus.PASS, message="Above-grade rooms, baths, bedrooms, and GLA are present.")


@rule(id="I-8", name="Additional Features")
def validate_additional_features(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"\bAdditional\s+Features\b|\bStandard insulation\b|\benergy efficient\b|\bnone\b", _raw(ctx), re.I):
        return _verify("I-8", "Additional Features", "Additional features section not extracted. Verify energy-efficient items are listed or 'NONE' is stated.")
    return RuleResult(rule_id="I-8", rule_name="Additional Features", status=RuleStatus.PASS, message="Additional-features evidence found.")


@rule(id="I-9", name="Property Condition Rating")
def validate_condition_rating(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    rating = (imp.condition_rating or "").upper()
    if not rating:
        match = re.search(r"Condition.*?\b(C[1-6])\b|Describe the condition.*?\b(C[1-6])\b", _raw(ctx), re.I | re.S)
        if match:
            rating = (match.group(1) or match.group(2)).upper()
    if not rating:
        return RuleResult(rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.FAIL, message="Condition of the Property must be UAD Compliant (C1-C6).")
    if rating not in {"C1", "C2", "C3", "C4", "C5", "C6"}:
        return RuleResult(rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.FAIL, message=f"Invalid condition rating: {rating}. Must be C1-C6.")
    return RuleResult(rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.PASS, message=f"Valid condition rating {rating}.")


@rule(id="I-10", name="Adverse Conditions Affecting Livability")
def validate_adverse_livability(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    if imp.adverse_conditions:
        return RuleResult(rule_id="I-10", rule_name="Adverse Conditions Affecting Livability", status=RuleStatus.WARNING, message="Adverse conditions affecting livability are indicated. Verify supporting commentary.")
    if not re.search(r"adverse conditions.*(?:Yes|No)|livability|soundness|structural integrity", _raw(ctx), re.I | re.S):
        return _verify("I-10", "Adverse Conditions Affecting Livability", "Adverse livability Yes/No field not extracted. Verify manually.")
    return RuleResult(rule_id="I-10", rule_name="Adverse Conditions Affecting Livability", status=RuleStatus.PASS, message="No adverse livability issue indicated.")


@rule(id="I-11", name="Neighborhood Conformity")
def validate_neighborhood_conformity(ctx: ValidationContext) -> RuleResult:
    imp = _improvements(ctx)
    text = _raw(ctx)
    if imp.conforms_to_neighborhood is False:
        return RuleResult(rule_id="I-11", rule_name="Neighborhood Conformity", status=RuleStatus.WARNING, message="Property does not conform to neighborhood. Extensive commentary is required.")
    if imp.conforms_to_neighborhood is None and not re.search(r"conform to the neighborhood.*(?:Yes|No)|property generally conform", text, re.I | re.S):
        return _verify("I-11", "Neighborhood Conformity", "Neighborhood conformity Yes/No field not extracted.")
    return RuleResult(rule_id="I-11", rule_name="Neighborhood Conformity", status=RuleStatus.PASS, message="Property conforms to neighborhood.")


@rule(id="I-12", name="Additions to Subject")
def validate_additions(ctx: ValidationContext) -> RuleResult:
    if re.search(r"\b(addition|converted|unpermitted|permit)\b", _raw(ctx), re.I):
        return RuleResult(rule_id="I-12", rule_name="Additions to Subject", status=RuleStatus.WARNING, message="Possible addition/permit language found. Verify permits, conformity, marketability impact, and zoning compliance.")
    return _verify("I-12", "Additions to Subject", "Automated addition detection is inconclusive. Verify whether additions exist and whether required commentary is present.")


@rule(id="I-13", name="Security Bars")
def validate_security_bars(ctx: ValidationContext) -> RuleResult:
    if re.search(r"security bars?|window bars?|release latch", _raw(ctx), re.I):
        return RuleResult(rule_id="I-13", rule_name="Security Bars", status=RuleStatus.WARNING, message="Security bar language found. Verify release latches and local code compliance.")
    return RuleResult(rule_id="I-13", rule_name="Security Bars", status=RuleStatus.PASS, message="No security bar language detected in OCR text.")
