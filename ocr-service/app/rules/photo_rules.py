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


@rule(id="PH-1", name="Required Subject Photos")
def validate_subject_photos(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    missing = _missing([r"Subject\s+Front|Front\s+Exterior", r"Subject\s+Rear|Rear\s+Exterior", r"Subject\s+Street|Street\s+Scene"], text)
    if missing:
        return _verify("PH-1", "Required Subject Photos", "Required subject photo labels not detected. Verify front, rear, and street scene photos.")
    return RuleResult(rule_id="PH-1", rule_name="Required Subject Photos", status=RuleStatus.PASS, message="Required subject photo labels detected.")


@rule(id="PH-2", name="Interior Photos")
def validate_interior_photos(ctx: ValidationContext) -> RuleResult:
    required = [r"Subject\s+Kitchen|\bKitchen\b", r"Subject\s+Living\s+Room|\bLiving\s+Room\b", r"Subject\s+Bedroom|\bBedroom\b", r"Subject\s+Bath(?:room)?|\bBathroom\b"]
    missing = _missing(required, _text(ctx))
    if missing:
        return _verify("PH-2", "Interior Photos", "Core interior photo labels not fully detected. Verify kitchen, living areas, bedrooms, and bathrooms are photographed.")
    return RuleResult(rule_id="PH-2", rule_name="Interior Photos", status=RuleStatus.PASS, message="Core interior photo labels detected.")


@rule(id="PH-3", name="Additional Subject Photos")
def validate_additional_photos(ctx: ValidationContext) -> RuleResult:
    if re.search(r"outbuilding|pool|deferred maintenance|special feature|obsolescence|subject side|crawl|attic", _text(ctx), re.I):
        return RuleResult(rule_id="PH-3", rule_name="Additional Subject Photos", status=RuleStatus.WARNING, message="Additional-feature language detected. Verify required supporting photos are present.")
    return _verify("PH-3", "Additional Subject Photos", "Additional subject photo requirement depends on property features. Verify outbuildings, pools, deferred maintenance, and obsolescence photos if applicable.")


@rule(id="PH-4", name="FHA Specific Photo Requirements")
def validate_fha_photos(ctx: ValidationContext) -> RuleResult:
    missing = _missing([r"Left\s+Side|Subject\s+Side", r"Right\s+Side|Subject\s+Side", r"Attic", r"Crawl"], _text(ctx))
    if missing:
        return _verify("PH-4", "FHA Specific Photo Requirements", f"FHA photo labels not detected: {', '.join(missing)}. Verify FHA side, attic, and crawl-space requirements.")
    return RuleResult(rule_id="PH-4", rule_name="FHA Specific Photo Requirements", status=RuleStatus.PASS, message="FHA-specific photo labels detected.")


@rule(id="PH-5", name="Comparable Photos")
def validate_comparable_photos(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"comparable photo|comp(?:arable)?\s+\d|MLS photo|drive-?by|Comparable\s+Sale\s+#", _text(ctx), re.I):
        return _verify("PH-5", "Comparable Photos", "Comparable photo evidence not detected. Verify MLS/drive-by requirements by loan type.")
    return RuleResult(rule_id="PH-5", rule_name="Comparable Photos", status=RuleStatus.WARNING, message="Comparable photo evidence found. Verify source is acceptable for the loan type.")


@rule(id="PH-6", name="Obsolescence Photo Requirements")
def validate_obsolescence_photos(ctx: ValidationContext) -> RuleResult:
    if re.search(r"obsolescence|external factor|deferred maintenance|damage", _text(ctx), re.I):
        return RuleResult(rule_id="PH-6", rule_name="Obsolescence Photo Requirements", status=RuleStatus.WARNING, message="Obsolescence/condition issue language found. Verify sufficient photos and commentary.")
    return RuleResult(rule_id="PH-6", rule_name="Obsolescence Photo Requirements", status=RuleStatus.PASS, message="No obsolescence photo trigger language detected.")
