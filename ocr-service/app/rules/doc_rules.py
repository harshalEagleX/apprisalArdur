"""Additional Documentation Rules (DOC-1 through DOC-4)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="DOC-1", name="Appraiser License")
def validate_appraiser_license(ctx: ValidationContext) -> RuleResult:
    if re.search(r"license|certification|certified residential|state certified", _text(ctx), re.I):
        return RuleResult(rule_id="DOC-1", rule_name="Appraiser License", status=RuleStatus.VERIFY, message="License/certification evidence found. Verify license is current and valid.")
    return _verify("DOC-1", "Appraiser License", "Appraiser license/certification evidence not detected.")


@rule(id="DOC-2", name="E&O Insurance")
def validate_eo_insurance(ctx: ValidationContext) -> RuleResult:
    if re.search(r"errors?\s*&\s*omissions|E&O|insurance", _text(ctx), re.I):
        return RuleResult(rule_id="DOC-2", rule_name="E&O Insurance", status=RuleStatus.VERIFY, message="Insurance evidence found. Verify client requirement if applicable.")
    return _verify("DOC-2", "E&O Insurance", "E&O insurance evidence not detected. Verify if client requires it.")


@rule(id="DOC-3", name="UAD Data Set")
def validate_uad_data_set(ctx: ValidationContext) -> RuleResult:
    if re.search(r"\bUAD\b|Uniform Appraisal Dataset", _text(ctx), re.I):
        return RuleResult(rule_id="DOC-3", rule_name="UAD Data Set", status=RuleStatus.PASS, message="UAD evidence detected.")
    return _verify("DOC-3", "UAD Data Set", "UAD data evidence not detected. Verify client delivery requirements.")


@rule(id="DOC-4", name="Trainee Signatures")
def validate_trainee_signatures(ctx: ValidationContext) -> RuleResult:
    if re.search(r"trainee|supervisory appraiser", _text(ctx), re.I):
        return RuleResult(rule_id="DOC-4", rule_name="Trainee Signatures", status=RuleStatus.VERIFY, message="Trainee/supervisory appraiser evidence found. Verify required signatures and roles.")
    return RuleResult(rule_id="DOC-4", rule_name="Trainee Signatures", status=RuleStatus.PASS, message="No trainee/supervisory signature trigger language detected.")
