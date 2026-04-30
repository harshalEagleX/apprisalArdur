"""Maps Section Rules (M-1 through M-4)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _verify(rule_id, name, message):
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="M-1", name="Location Map")
def validate_location_map(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"location map|subject.*comparables|comparable.*map", _text(ctx), re.I):
        return _verify("M-1", "Location Map", "Location map evidence not detected. Verify subject, all comparables, and neighborhood boundaries are shown.")
    return RuleResult(rule_id="M-1", rule_name="Location Map", status=RuleStatus.PASS, message="Location map evidence detected.")


@rule(id="M-2", name="Aerial Map")
def validate_aerial_map(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"aerial map|aerial view|satellite", _text(ctx), re.I):
        return _verify("M-2", "Aerial Map", "Aerial map evidence not detected. Verify if needed for external obsolescence/location review.")
    return RuleResult(rule_id="M-2", rule_name="Aerial Map", status=RuleStatus.PASS, message="Aerial map evidence detected.")


@rule(id="M-3", name="Plat Map")
def validate_plat_map(ctx: ValidationContext) -> RuleResult:
    if ctx.report.site.dimensions and ctx.report.site.shape and "irregular" not in (ctx.report.site.shape or "").lower():
        return RuleResult(rule_id="M-3", rule_name="Plat Map", status=RuleStatus.SKIPPED, message="Plat map not required based on extracted regular site dimensions/shape.")
    if not re.search(r"plat map|survey|site plan", _text(ctx), re.I):
        return _verify("M-3", "Plat Map", "Plat map evidence not detected. Verify if site is irregular or dimensions are incomplete.")
    return RuleResult(rule_id="M-3", rule_name="Plat Map", status=RuleStatus.PASS, message="Plat/survey evidence detected.")


@rule(id="M-4", name="Flood Map")
def validate_flood_map(ctx: ValidationContext) -> RuleResult:
    if ctx.report.site.fema_flood_hazard and not re.search(r"flood map|FEMA map|flood hazard", _text(ctx), re.I):
        return RuleResult(rule_id="M-4", rule_name="Flood Map", status=RuleStatus.FAIL, message="Subject is marked in a flood hazard area, but flood map evidence was not detected.")
    if re.search(r"flood map|FEMA map|flood hazard", _text(ctx), re.I):
        return RuleResult(rule_id="M-4", rule_name="Flood Map", status=RuleStatus.PASS, message="Flood map/FEMA evidence detected.")
    return _verify("M-4", "Flood Map", "Flood map requirement could not be determined from extracted fields. Verify FEMA zone/map page.")
