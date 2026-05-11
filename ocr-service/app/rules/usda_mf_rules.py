"""USDA Loan Requirements and Multi-Family Form Rules."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


def _is_multifamily(ctx: ValidationContext) -> bool:
    """True only when the property/form type indicates multi-family or investment use."""
    text = _text(ctx)
    return bool(re.search(r"\bForm\s*1007\b|\b216\b|multi.?family|2-4\s+unit|investment\s+property", text, re.I))


def _is_usda(ctx: ValidationContext) -> bool:
    if ctx.engagement_letter:
        loan_type = (ctx.engagement_letter.loan_type or "").upper()
        if loan_type and "USDA" in loan_type:
            return True
    return bool(re.search(r"\bUSDA\b|rural development", _text(ctx), re.I))


@rule(id="USDA-1", name="Cost Approach")
def validate_usda_cost_approach(ctx: ValidationContext) -> RuleResult:
    if not _is_usda(ctx):
        return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.NOT_APPLICABLE,
                          message="USDA cost-approach rule is not applicable to this loan type; it does not count as PASS.")
    if re.search(r"cost approach", _text(ctx), re.I):
        return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.VERIFY, message="Cost Approach evidence found for USDA review. Verify completion and values.")
    return RuleResult(rule_id="USDA-1", rule_name="Cost Approach", status=RuleStatus.FAIL, message="USDA loan requires Cost Approach, but Cost Approach evidence was not detected.")


@rule(id="MF-1", name="Subject Rent Matching")
def validate_mf_rent_matching(ctx: ValidationContext) -> RuleResult:
    # For single-family properties, rent matching is not applicable.
    if not _is_multifamily(ctx):
        return RuleResult(rule_id="MF-1", rule_name="Subject Rent Matching", status=RuleStatus.NOT_APPLICABLE,
                          message="Single-family property — rent schedule not applicable; this does not count as PASS.")
    if re.search(r"gross monthly rent|subject rent schedule|1007", _text(ctx), re.I):
        return RuleResult(rule_id="MF-1", rule_name="Subject Rent Matching", status=RuleStatus.VERIFY,
                          message="Rent schedule evidence found. Verify rent matches income approach.")
    return _verify("MF-1", "Subject Rent Matching", "Subject rent schedule evidence not detected. Verify if applicable.")


@rule(id="MF-2", name="Operating Income Statement (Form 216)")
def validate_mf_form_216(ctx: ValidationContext) -> RuleResult:
    # For single-family properties, Form 216 is not applicable.
    if not _is_multifamily(ctx):
        return RuleResult(rule_id="MF-2", rule_name="Operating Income Statement", status=RuleStatus.NOT_APPLICABLE,
                          message="Single-family property — Form 216 not applicable; this does not count as PASS.")
    if re.search(r"form\s*216|operating income statement", _text(ctx), re.I):
        return RuleResult(rule_id="MF-2", rule_name="Operating Income Statement", status=RuleStatus.VERIFY,
                          message="Form 216 evidence found. Verify income/expense calculations and rent consistency.")
    return _verify("MF-2", "Operating Income Statement", "Form 216 evidence not detected. Verify when income approach is used.")
