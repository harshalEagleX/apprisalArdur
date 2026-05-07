"""Additional Documentation Rules (DOC-1 through DOC-4)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="DOC-1", name="Appraiser License")
def validate_appraiser_license(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    # Require a state certification number in a standard format (letters+digits)
    # rather than just any mention of "license" which could be boilerplate.
    if re.search(r"(?:State\s+Certification\s*#?|License\s*#?|Cert\s*#?)\s*[A-Z]{1,3}\d{4,}", text, re.I):
        # Validate expiration date — if it appears past today, auto-pass
        exp_match = re.search(r"Expiration\s+Date.*?(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})", text, re.I | re.S)
        if exp_match:
            try:
                from datetime import datetime
                exp_str = exp_match.group(1)
                for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        exp_date = datetime.strptime(exp_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    exp_date = None
                if exp_date and exp_date > datetime.now():
                    return RuleResult(rule_id="DOC-1", rule_name="Appraiser License", status=RuleStatus.PASS,
                                      message=f"Appraiser certification found and valid through {exp_str}.")
            except Exception:
                pass
        return RuleResult(rule_id="DOC-1", rule_name="Appraiser License", status=RuleStatus.VERIFY,
                          message="License/certification evidence found. Verify license is current and valid.")
    if re.search(r"license|certification|certified residential|state certified", text, re.I):
        return RuleResult(rule_id="DOC-1", rule_name="Appraiser License", status=RuleStatus.VERIFY,
                          message="License/certification evidence found. Verify license is current and valid.")
    return _verify("DOC-1", "Appraiser License", "Appraiser license/certification evidence not detected.")


@rule(id="DOC-2", name="E&O Insurance")
def validate_eo_insurance(ctx: ValidationContext) -> RuleResult:
    # Per QC checklist: E&O insurance is NOT required. Rule auto-passes regardless.
    # "E & O Insurance" appears as a form LABEL on URAR photo pages — not documentation.
    return RuleResult(rule_id="DOC-2", rule_name="E&O Insurance", status=RuleStatus.PASS,
                      message="E&O insurance is not a required deliverable per QC checklist.")


@rule(id="DOC-3", name="UAD Data Set")
def validate_uad_data_set(ctx: ValidationContext) -> RuleResult:
    if re.search(r"\bUAD\b|Uniform Appraisal Dataset", _text(ctx), re.I):
        return RuleResult(rule_id="DOC-3", rule_name="UAD Data Set", status=RuleStatus.PASS, message="UAD evidence detected.")
    return _verify("DOC-3", "UAD Data Set", "UAD data evidence not detected. Verify client delivery requirements.")


@rule(id="DOC-4", name="Trainee Signatures")
def validate_trainee_signatures(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    # "Supervisory Appraiser" is printed on every URAR form as a boilerplate section.
    # Only flag if the word "trainee" explicitly appears — indicating a trainee appraiser
    # is involved and a supervisory signature is required.
    if re.search(r"\btrainee\b", text, re.I):
        return RuleResult(rule_id="DOC-4", rule_name="Trainee Signatures", status=RuleStatus.VERIFY,
                          message="Trainee appraiser language found. Verify supervisory appraiser signature and role requirements.")
    return RuleResult(rule_id="DOC-4", rule_name="Trainee Signatures", status=RuleStatus.PASS,
                      message="No trainee appraiser involvement detected.")
