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
    return RuleResult(rule_id="SIG-1", rule_name="Signature Requirements", status=RuleStatus.PASS,
                      message="Signature/date evidence detected.", details={"presence_validated": True})


@rule(id="SIG-2", name="Appraiser Information")
def validate_appraiser_info(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    required = {
        "Appraiser Name": r"Name\s+[A-Z][A-Za-z]+|Appraiser\s+Name",
        "Company Name/Address": r"Company\s+Name|Company\s+Address",
        "Certification/License Number": r"State\s+Certification\s*#|State\s+License\s*#|Cert(?:ification)?\s*#?\s*[A-Z]{1,3}\d{4,}",
        "Phone": r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}|Telephone|Phone",
        "Email": r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "Expiration Date": r"Expiration\s+Date.*?(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
        "State": r"\bState\b|\b[A-Z]{2}\s+(?:Certification|License)\b",
    }
    missing = [
        label for label, pattern in required.items()
        if not re.search(pattern, text, re.I | re.S)
    ]
    if missing:
        return _verify("SIG-2", "Appraiser Information", f"Appraiser information incomplete or not extracted: {', '.join(missing)}. Verify all signature page fields are complete.")
    return RuleResult(rule_id="SIG-2", rule_name="Appraiser Information", status=RuleStatus.PASS,
                      message="Appraiser name, company, and certification/license detected.",
                      details={"presence_validated": True})


@rule(id="SIG-3", name="Supervisory Appraiser")
def validate_supervisory_appraiser(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    # Every URAR form has "SUPERVISORY APPRAISER'S CERTIFICATION" boilerplate text.
    # Only flag VERIFY when a supervisory appraiser name is ACTUALLY present.
    # A blank supervisory section means no supervisor is required (certified appraiser).
    supervisor_name = re.search(
        r"(?:Supervisory\s+Appraiser\s+Name|Name\s+of\s+Supervisory\s+Appraiser)[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
        text, re.I,
    )
    if supervisor_name:
        supervisor_context = text[supervisor_name.start():supervisor_name.start() + 1200]
        if not re.search(r"Did\s+Inspect|Did\s+Not\s+Inspect|inspect(?:ed)?\s+property", supervisor_context, re.I):
            return RuleResult(rule_id="SIG-3", rule_name="Supervisory Appraiser", status=RuleStatus.VERIFY,
                              message=f"Supervisory appraiser '{supervisor_name.group(1)}' found. Verify signature, certification, and Did/Did Not Inspect Property checkbox.")
        return RuleResult(rule_id="SIG-3", rule_name="Supervisory Appraiser", status=RuleStatus.VERIFY,
                          message=f"Supervisory appraiser '{supervisor_name.group(1)}' found. Verify signature and certification requirements.")
    return RuleResult(
        rule_id="SIG-3",
        rule_name="Supervisory Appraiser",
        status=RuleStatus.NOT_APPLICABLE,
        message="No supervisory appraiser involvement detected; supervisory signature rule does not count as PASS.",
    )


@rule(id="SIG-4", name="Email Address")
def validate_email_address(ctx: ValidationContext) -> RuleResult:
    if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", _text(ctx), re.I):
        return RuleResult(rule_id="SIG-4", rule_name="Email Address", status=RuleStatus.PASS,
                          message="Email address detected.", details={"presence_validated": True})
    return _verify("SIG-4", "Email Address", "Appraiser email address not detected.")
