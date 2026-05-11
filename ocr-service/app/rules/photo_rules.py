"""Photograph & Image Processing Rules (PH-1 through PH-6)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _missing(labels, text):
    return [label for label in labels if not re.search(label, text, re.I)]


def _verify(rule_id, name, message):
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


def _loan_type(ctx: ValidationContext) -> str:
    if ctx.engagement_letter:
        return (ctx.engagement_letter.loan_type or "Conventional").upper()
    return "Conventional"


@rule(id="PH-1", name="Required Subject Photos")
def validate_subject_photos(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    missing = _missing([r"Subject\s+Front|Front\s+Exterior", r"Subject\s+Rear|Rear\s+Exterior", r"Subject\s+Street|Street\s+Scene"], text)
    if missing:
        return _verify("PH-1", "Required Subject Photos", "Required subject photo labels not detected. Verify front, rear, and street scene photos.")
    # presence_validated signals to the rule engine that text-presence evidence
    # is the only available proof type for this rule — no reference document exists.
    return RuleResult(rule_id="PH-1", rule_name="Required Subject Photos", status=RuleStatus.PASS,
                      message="Required subject photo labels detected.",
                      details={"presence_validated": True})


@rule(id="PH-2", name="Interior Photos")
def validate_interior_photos(ctx: ValidationContext) -> RuleResult:
    required = [r"Subject\s+Kitchen|\bKitchen\b", r"Subject\s+Living\s+Room|\bLiving\s+Room\b", r"Subject\s+Bedroom|\bBedroom\b", r"Subject\s+Bath(?:room)?|\bBathroom\b"]
    missing = _missing(required, _text(ctx))
    if missing:
        return _verify("PH-2", "Interior Photos", "Core interior photo labels not fully detected. Verify kitchen, living areas, bedrooms, and bathrooms are photographed.")
    return RuleResult(rule_id="PH-2", rule_name="Interior Photos", status=RuleStatus.PASS,
                      message="Core interior photo labels detected.",
                      details={"presence_validated": True})


@rule(id="PH-3", name="Additional Subject Photos")
def validate_additional_photos(ctx: ValidationContext) -> RuleResult:
    if re.search(r"outbuilding|pool|deferred maintenance|special feature|obsolescence|subject side|crawl|attic", _text(ctx), re.I):
        return RuleResult(rule_id="PH-3", rule_name="Additional Subject Photos", status=RuleStatus.VERIFY, message="Additional-feature language detected. Verify required supporting photos are present.")
    return _verify("PH-3", "Additional Subject Photos", "Additional subject photo requirement depends on property features. Verify outbuildings, pools, deferred maintenance, and obsolescence photos if applicable.")


@rule(id="PH-4", name="FHA Specific Photo Requirements")
def validate_fha_photos(ctx: ValidationContext) -> RuleResult:
    missing = _missing([r"Left\s+Side|Subject\s+Side", r"Right\s+Side|Subject\s+Side", r"Attic", r"Crawl"], _text(ctx))
    if missing:
        return _verify("PH-4", "FHA Specific Photo Requirements", f"FHA photo labels not detected: {', '.join(missing)}. Verify FHA side, attic, and crawl-space requirements.")
    return RuleResult(rule_id="PH-4", rule_name="FHA Specific Photo Requirements", status=RuleStatus.PASS,
                      message="FHA-specific photo labels detected.", details={"presence_validated": True})


@rule(id="PH-5", name="Comparable Photos")
def validate_comparable_photos(ctx: ValidationContext) -> RuleResult:
    lt = _loan_type(ctx)
    # For conventional loans: MLS photos with drive-by commentary are acceptable.
    # Only FHA requires actual drive-by photos.
    if "FHA" not in lt:
        return RuleResult(rule_id="PH-5", rule_name="Comparable Photos", status=RuleStatus.NOT_APPLICABLE,
                          message="FHA drive-by comparable-photo rule is not applicable to this non-FHA loan type.")
    if not re.search(r"comparable photo|comp(?:arable)?\s+\d|MLS photo|drive-?by|Comparable\s+Sale\s+#", _text(ctx), re.I):
        return _verify("PH-5", "Comparable Photos", "Comparable photo evidence not detected. FHA requires drive-by photos for all comparables.")
    return RuleResult(rule_id="PH-5", rule_name="Comparable Photos", status=RuleStatus.VERIFY,
                      message="Comparable photo evidence found. Verify drive-by photos meet FHA requirements.")


@rule(id="PH-6", name="Obsolescence Photo Requirements")
def validate_obsolescence_photos(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    # C1/C2 condition = new/nearly new property — no external obsolescence by definition.
    # Only flag if the condition is C3+ AND obsolescence language is found.
    condition = getattr(getattr(ctx.report, "improvements", None), "condition_rating", "") or ""
    is_new = re.match(r"C[12]", condition)
    if is_new:
        return RuleResult(rule_id="PH-6", rule_name="Obsolescence Photo Requirements", status=RuleStatus.PASS,
                          message=f"C1/C2 condition — no obsolescence expected for new construction.",
                          details={"structured_validation": True},
                          compared_fields=["condition_rating"],
                          compared_values={"condition_rating": condition},
                          comparison_method="condition_rating_trigger_check")
    # For older properties, check for obsolescence language that requires photos
    if re.search(r"external obsolescence|adverse.*external|deferred maintenance.*signif|damage.*structure", text, re.I):
        return RuleResult(rule_id="PH-6", rule_name="Obsolescence Photo Requirements", status=RuleStatus.VERIFY,
                          message="Obsolescence/condition issue language found. Verify sufficient photos and commentary.")
    return _verify(
        "PH-6",
        "Obsolescence Photo Requirements",
        "No significant obsolescence trigger language was detected, but adverse/obsolescence photo applicability is not structurally validated. Verify if additional photos are required.",
    )
