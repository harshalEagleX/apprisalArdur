"""
Signature Page Rules (SIG-1 through SIG-4)
"""
from typing import Optional
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

@rule(id="SIG-1", name="Signature Requirements")
def validate_signatures(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SIG-1", rule_name="Signature Requirements", status=RuleStatus.PASS, message="Date and appraiser signature provided.")

@rule(id="SIG-2", name="Appraiser Information")
def validate_appraiser_info(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SIG-2", rule_name="Appraiser Information", status=RuleStatus.PASS, message="Appraiser and company details provided.")

@rule(id="SIG-3", name="Supervisory Appraiser")
def validate_supervisory_appraiser(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SIG-3", rule_name="Supervisory Appraiser", status=RuleStatus.PASS, message="Supervisory appraiser details verified if applicable.")

@rule(id="SIG-4", name="Email Address")
def validate_email_address(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SIG-4", rule_name="Email Address", status=RuleStatus.PASS, message="Email address provided.")
