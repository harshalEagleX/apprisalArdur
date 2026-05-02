"""USDA Loan Requirements and Multi-Family Form Rules."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="USDA-1", name="Cost Approach")
def validate_usda_cost_approach(ctx: ValidationContext) -> RuleResult:
    if re.search(r"cost approach", _text(ctx), re.I):
        return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.PASS, message="Cost Approach evidence found for USDA review.")
    return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.FAIL, message="USDA loan requires Cost Approach, but Cost Approach evidence was not detected.")


@rule(id="MF-1", name="Subject Rent Matching")
def validate_mf_rent_matching(ctx: ValidationContext) -> RuleResult:
    if re.search(r"gross monthly rent|subject rent schedule|1007", _text(ctx), re.I):
        return RuleResult(rule_id="MF-1", rule_name="Subject Rent Matching", status=RuleStatus.VERIFY, message="Rent schedule evidence found. Verify rent matches income approach.")
    return _verify("MF-1", "Subject Rent Matching", "Subject rent schedule evidence not detected. Verify if applicable.")


@rule(id="MF-2", name="Operating Income Statement (Form 216)")
def validate_mf_form_216(ctx: ValidationContext) -> RuleResult:
    if re.search(r"form\s*216|operating income statement", _text(ctx), re.I):
        return RuleResult(rule_id="MF-2", rule_name="Operating Income Statement", status=RuleStatus.PASS, message="Form 216 evidence found.")
    return _verify("MF-2", "Operating Income Statement", "Form 216 evidence not detected. Verify when income approach is used.")
