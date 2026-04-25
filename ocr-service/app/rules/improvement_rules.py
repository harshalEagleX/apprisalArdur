"""
Improvement Section Rules (I-1 through I-13)
All validation rules for the Improvement section of appraisal reports.
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="I-1", name="General Description")
def validate_general_description(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    missing = []
    if not improvement.units: missing.append("Units")
    if not improvement.stories: missing.append("Stories")
    if not improvement.property_type: missing.append("Type")
    if not improvement.status: missing.append("Status (Existing/Proposed/Under Construction)")
    if not improvement.design_style: missing.append("Design Style")
    if not improvement.year_built: missing.append("Year Built")
    if not improvement.effective_age: missing.append("Effective Age")
    
    if missing:
        return RuleResult(
            rule_id="I-1", rule_name="General Description", status=RuleStatus.FAIL,
            message=f"Missing general description fields: {', '.join(missing)}"
        )
    return RuleResult(rule_id="I-1", rule_name="General Description", status=RuleStatus.PASS, message="General description complete.")

@rule(id="I-2", name="Foundation")
def validate_foundation(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or not improvement.foundation_details:
        return RuleResult(
            rule_id="I-2", rule_name="Foundation", status=RuleStatus.FAIL,
            message="Foundation details must be completed as applicable."
        )
    return RuleResult(rule_id="I-2", rule_name="Foundation", status=RuleStatus.PASS, message="Foundation details provided.")

@rule(id="I-3", name="Exterior Description")
def validate_exterior_description(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or not improvement.exterior_details:
        return RuleResult(
            rule_id="I-3", rule_name="Exterior Description", status=RuleStatus.FAIL,
            message="Exterior details must be completed as applicable."
        )
    return RuleResult(rule_id="I-3", rule_name="Exterior Description", status=RuleStatus.PASS, message="Exterior details provided.")

@rule(id="I-4", name="Interior Description")
def validate_interior_description(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    if improvement.car_storage == "None" and improvement.has_driveway:
        return RuleResult(
            rule_id="I-4", rule_name="Interior Description", status=RuleStatus.WARNING,
            message="Car storage should NOT be 'None' if subject has a driveway."
        )
    return RuleResult(rule_id="I-4", rule_name="Interior Description", status=RuleStatus.PASS, message="Interior description valid.")

@rule(id="I-5", name="Utilities")
def validate_improvement_utilities(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or improvement.utilities_on is None:
        return RuleResult(
            rule_id="I-5", rule_name="Utilities", status=RuleStatus.FAIL,
            message="Must state if utilities were ON at time of inspection."
        )
    return RuleResult(rule_id="I-5", rule_name="Utilities", status=RuleStatus.PASS, message="Utilities status documented.")

@rule(id="I-6", name="Appliances")
def validate_appliances(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or not improvement.appliances:
         return RuleResult(
            rule_id="I-6", rule_name="Appliances", status=RuleStatus.WARNING,
            message="Note ONLY built-in items. Appraiser MUST operate built-in appliances and provide statement on operational status."
        )
    return RuleResult(rule_id="I-6", rule_name="Appliances", status=RuleStatus.PASS, message="Built-in appliances documented.")

@rule(id="I-7", name="Above Grade Room Count")
def validate_room_count(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    if not improvement.above_grade_rooms or not improvement.above_grade_bedrooms or not improvement.above_grade_baths or not improvement.gla:
        return RuleResult(
            rule_id="I-7", rule_name="Above Grade Room Count", status=RuleStatus.FAIL,
            message="Above Grade Contains (Total Rooms, Bedrooms, Baths, GLA) must be provided."
        )
    return RuleResult(rule_id="I-7", rule_name="Above Grade Room Count", status=RuleStatus.PASS, message="Above grade room count provided.")

@rule(id="I-8", name="Additional Features")
def validate_additional_features(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or not improvement.additional_features:
        return RuleResult(
            rule_id="I-8", rule_name="Additional Features", status=RuleStatus.WARNING,
            message="List energy efficient items if any. If None, state 'NONE'."
        )
    return RuleResult(rule_id="I-8", rule_name="Additional Features", status=RuleStatus.PASS, message="Additional features documented.")

@rule(id="I-9", name="Property Condition Rating")
def validate_condition_rating(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or not improvement.condition_rating:
        return RuleResult(
            rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.FAIL,
            message="Condition of the Property must be UAD Compliant (C1-C6)."
        )
    
    rating = improvement.condition_rating.upper()
    if rating not in ["C1", "C2", "C3", "C4", "C5", "C6"]:
        return RuleResult(
            rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.FAIL,
            message=f"Invalid condition rating: {rating}. Must be C1-C6."
        )
    return RuleResult(rule_id="I-9", rule_name="Property Condition Rating", status=RuleStatus.PASS, message=f"Valid condition rating {rating}.")

@rule(id="I-10", name="Adverse Conditions Affecting Livability")
def validate_adverse_livability(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    if improvement.has_adverse_livability_conditions:
         return RuleResult(
            rule_id="I-10", rule_name="Adverse Conditions Affecting Livability", status=RuleStatus.WARNING,
            message="Adverse conditions affecting livability are checked. Verify items actually affect livability."
        )
    return RuleResult(rule_id="I-10", rule_name="Adverse Conditions Affecting Livability", status=RuleStatus.PASS, message="No adverse livability conditions.")

@rule(id="I-11", name="Neighborhood Conformity")
def validate_neighborhood_conformity(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement or improvement.conforms_to_neighborhood is None:
        return RuleResult(
            rule_id="I-11", rule_name="Neighborhood Conformity", status=RuleStatus.FAIL,
            message="Does property conform to neighborhood? Yes or No must be checked."
        )
    
    if not improvement.conforms_to_neighborhood:
        return RuleResult(
            rule_id="I-11", rule_name="Neighborhood Conformity", status=RuleStatus.WARNING,
            message="Property does not conform to neighborhood. Extensive commentary REQUIRED addressing why, rebuildability, and overbuilt status."
        )
    return RuleResult(rule_id="I-11", rule_name="Neighborhood Conformity", status=RuleStatus.PASS, message="Property conforms to neighborhood.")

@rule(id="I-12", name="Additions to Subject")
def validate_additions(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    if improvement.has_additions:
         return RuleResult(
            rule_id="I-12", rule_name="Additions to Subject", status=RuleStatus.WARNING,
            message="Additions detected. Required Commentary: Is addition permitted? Conforms to original structure? Marketability impact and zoning compliance."
        )
    return RuleResult(rule_id="I-12", rule_name="Additions to Subject", status=RuleStatus.PASS, message="No additions noted.")

@rule(id="I-13", name="Security Bars")
def validate_security_bars(ctx: ValidationContext) -> RuleResult:
    improvement = getattr(ctx.report, 'improvement', None)
    if not improvement: raise DataMissingException("Improvement Section")
    
    if improvement.has_security_bars:
         return RuleResult(
            rule_id="I-13", rule_name="Security Bars", status=RuleStatus.WARNING,
            message="Security bars on windows detected. Comment required: Safety release latches present? Meets building codes?"
        )
    return RuleResult(rule_id="I-13", rule_name="Security Bars", status=RuleStatus.PASS, message="No security bars noted.")
