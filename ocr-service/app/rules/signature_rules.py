"""Signature Page Rules (SIG-1 through SIG-4)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="SIG-1", name="Signature Requirements")
def validate_signatures(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"signature of appraiser|appraiser signature|APPRAISER\s+.*Signature|Date of Signature|Date Signed|signed", text, re.I | re.S):
        return _verify("SIG-1", "Signature Requirements", "Appraiser signature evidence not detected. Verify signature and report date.")
    if not re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text):
        return RuleResult(rule_id="SIG-1", rule_name="Signature Requirements", status=RuleStatus.VERIFY, message="Signature evidence found, but date pattern was not detected.")
    return RuleResult(rule_id="SIG-1", rule_name="Signature Requirements", status=RuleStatus.PASS, message="Signature/date evidence detected.")


@rule(id="SIG-2", name="Appraiser Information")
def validate_appraiser_info(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    required = [
        r"Name\s+[A-Z][A-Za-z]+|Appraiser\s+Name",
        r"Company\s+Name|Company\s+Address",
        r"State\s+Certification\s+#|State\s+License\s+#|License",
    ]
    if not all(re.search(pattern, text, re.I) for pattern in required):
        return _verify("SIG-2", "Appraiser Information", "Appraiser/company/license information not detected.")
    return RuleResult(rule_id="SIG-2", rule_name="Appraiser Information", status=RuleStatus.VERIFY, message="Appraiser information evidence found. Verify all fields are complete.")


@rule(id="SIG-3", name="Supervisory Appraiser")
def validate_supervisory_appraiser(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"SUPERVISORY APPRAISER.*(?:Name|Signature).{0,80}\S", text, re.I | re.S):
        return RuleResult(rule_id="SIG-3", rule_name="Supervisory Appraiser", status=RuleStatus.VERIFY, message="Supervisory appraiser evidence found. Verify signature/certification requirements.")
    return RuleResult(rule_id="SIG-3", rule_name="Supervisory Appraiser", status=RuleStatus.SKIPPED, message="No supervisory appraiser evidence detected.")


@rule(id="SIG-4", name="Email Address")
def validate_email_address(ctx: ValidationContext) -> RuleResult:
    if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", _text(ctx), re.I):
        return RuleResult(rule_id="SIG-4", rule_name="Email Address", status=RuleStatus.PASS, message="Email address detected.")
    return _verify("SIG-4", "Email Address", "Appraiser email address not detected.")
