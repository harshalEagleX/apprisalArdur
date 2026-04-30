"""Reconciliation, Cost, and Income Approach Rules."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _verify(rule_id: str, name: str, message: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="R-1", name="Value Reconciliation")
def validate_value_reconciliation(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"reconciliation|indicated value by sales comparison|sales comparison approach", text, re.I):
        return _verify("R-1", "Value Reconciliation", "Reconciliation section was not extracted. Verify all used approaches are reconciled.")
    if not re.search(r"weight|weighted|most reliable|best indicator|given.*consideration|supportive and reasonable conclusion|opinion of market value", text, re.I):
        return RuleResult(rule_id="R-1", rule_name="Value Reconciliation", status=RuleStatus.WARNING, message="Reconciliation text found, but weighting/rationale language was not detected.")
    return RuleResult(rule_id="R-1", rule_name="Value Reconciliation", status=RuleStatus.PASS, message="Reconciliation rationale evidence found.")


@rule(id="R-2", name="Final Opinion of Value")
def validate_final_value(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"(?:final opinion of value|appraised value|opinion of value|Indicated Value by Sales Comparison Approach|APPRAISED VALUE OF SUBJECT PROPERTY)\s*[:$]?\s*\$?\d[\d,]+", text, re.I):
        return RuleResult(rule_id="R-2", rule_name="Final Opinion of Value", status=RuleStatus.PASS, message="Final opinion of value evidence found.")
    return _verify("R-2", "Final Opinion of Value", "Final opinion of value was not extracted. Verify it is clearly stated.")


@rule(id="CA-1", name="Cost Approach Requirement")
def validate_cost_approach_req(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"\bUSDA\b|rural development", text, re.I) and not re.search(r"cost approach", text, re.I):
        return RuleResult(rule_id="CA-1", rule_name="Cost Approach Requirement", status=RuleStatus.FAIL, message="USDA loan detected but Cost Approach was not found.")
    return _verify("CA-1", "Cost Approach Requirement", "Cost Approach requirement depends on loan/client conditions. Verify applicability and completion.")


@rule(id="CA-2", name="Cost Approach Completion")
def validate_cost_approach_completion(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"cost approach", text, re.I):
        return _verify("CA-2", "Cost Approach Completion", "Cost Approach section not extracted. Verify if required.")
    missing = [label for label in ["opinion of site value|site value", "cost new|replacement cost new", "depreciation", "indicated value"] if not re.search(label, text, re.I)]
    if missing:
        return RuleResult(rule_id="CA-2", rule_name="Cost Approach Completion", status=RuleStatus.WARNING, message=f"Cost Approach found, but these fields were not detected: {', '.join(missing)}.")
    return RuleResult(rule_id="CA-2", rule_name="Cost Approach Completion", status=RuleStatus.PASS, message="Cost Approach completion evidence found.")


@rule(id="IA-1", name="Subject Rent Matching")
def validate_income_rent_matching(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"gross monthly rent|subject rent schedule|form\s*1007", text, re.I):
        return _verify("IA-1", "Subject Rent Matching", "Income/rent schedule fields not extracted. Verify rent matching if income approach is used.")
    return RuleResult(rule_id="IA-1", rule_name="Subject Rent Matching", status=RuleStatus.WARNING, message="Rent schedule evidence found. Verify income approach rent matches Form 1007.")


@rule(id="IA-2", name="Operating Income Statement (Form 216)")
def validate_form_216(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"form\s*216|operating income statement", text, re.I):
        return RuleResult(rule_id="IA-2", rule_name="Operating Income Statement", status=RuleStatus.PASS, message="Form 216 / operating income evidence found.")
    return _verify("IA-2", "Operating Income Statement", "Form 216 not extracted. Verify it is completed when income approach is used.")
