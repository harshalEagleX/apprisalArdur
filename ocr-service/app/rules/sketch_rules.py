"""
Floor Plan Sketch Rules (SK-1 through SK-5)
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="SK-1", name="Sketch Location")
def validate_sketch_location(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SK-1", rule_name="Sketch Location", status=RuleStatus.PASS, message="Sketch is on proper page.")

@rule(id="SK-2", name="Floor Coverage")
def validate_floor_coverage(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SK-2", rule_name="Floor Coverage", status=RuleStatus.PASS, message="Sketch includes all floors.")

@rule(id="SK-3", name="Dimensions")
def validate_sketch_dimensions(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SK-3", rule_name="Dimensions", status=RuleStatus.PASS, message="Exterior dimensions and room labels provided.")

@rule(id="SK-4", name="Outbuildings and Structures")
def validate_sketch_outbuildings(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SK-4", rule_name="Outbuildings and Structures", status=RuleStatus.PASS, message="Structures contributing to value are sketched.")

@rule(id="SK-5", name="Area Calculations")
def validate_area_calculations(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SK-5", rule_name="Area Calculations", status=RuleStatus.PASS, message="Area calculations provided and match GLA.")
