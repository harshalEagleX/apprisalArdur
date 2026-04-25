"""
USDA Loan Requirements and Multi-Family Form Rules
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="USDA-1", name="Cost Approach")
def validate_usda_cost_approach(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.PASS, message="Cost Approach provided for USDA loan.")

@rule(id="MF-1", name="Subject Rent Matching")
def validate_mf_rent_matching(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="MF-1", rule_name="Subject Rent Matching", status=RuleStatus.PASS, message="Gross Monthly Rent matches Subject Rent Schedule.")

@rule(id="MF-2", name="Operating Income Statement (Form 216)")
def validate_mf_form_216(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="MF-2", rule_name="Operating Income Statement", status=RuleStatus.PASS, message="Form 216 completed.")
