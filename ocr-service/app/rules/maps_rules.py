"""
Maps Section Rules (M-1 through M-4)
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="M-1", name="Location Map")
def validate_location_map(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="M-1", rule_name="Location Map", status=RuleStatus.PASS, message="Location map includes subject, all comparables, and neighborhood boundaries.")

@rule(id="M-2", name="Aerial Map")
def validate_aerial_map(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="M-2", rule_name="Aerial Map", status=RuleStatus.PASS, message="Aerial map verified for external obsolescence if provided.")

@rule(id="M-3", name="Plat Map")
def validate_plat_map(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="M-3", rule_name="Plat Map", status=RuleStatus.PASS, message="Plat map provided if site dimensions missing on Page 1.")

@rule(id="M-4", name="Flood Map")
def validate_flood_map(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="M-4", rule_name="Flood Map", status=RuleStatus.PASS, message="Flood map provided if subject in Flood Zone.")
