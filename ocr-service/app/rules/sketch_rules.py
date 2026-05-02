"""Floor Plan Sketch Rules (SK-1 through SK-5)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _verify(rule_id, name, message):
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="SK-1", name="Sketch Location")
def validate_sketch_location(ctx: ValidationContext) -> RuleResult:
    if re.search(r"floor plan|sketch|building sketch|ANSI standards|measured per ANSI", _text(ctx), re.I):
        return RuleResult(rule_id="SK-1", rule_name="Sketch Location", status=RuleStatus.PASS, message="Sketch/floor-plan evidence detected.")
    return _verify("SK-1", "Sketch Location", "Sketch/floor-plan page not detected. Verify sketch is on the appraisal software sketch page.")


@rule(id="SK-2", name="Floor Coverage")
def validate_floor_coverage(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"first floor|second floor|main level|basement|upper level|lower level|one[-\s]?story|#\s*of\s*Stories\s+1", _text(ctx), re.I):
        return _verify("SK-2", "Floor Coverage", "Floor labels not detected on sketch. Verify all floors are included.")
    return RuleResult(rule_id="SK-2", rule_name="Floor Coverage", status=RuleStatus.VERIFY, message="Floor-label evidence found. Verify all floors are represented.")


@rule(id="SK-3", name="Dimensions")
def validate_sketch_dimensions(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?|\d+'\s*-\s*\d+\"|measured per ANSI|ANSI standards", _text(ctx), re.I):
        return _verify("SK-3", "Dimensions", "Exterior sketch dimensions not detected. Verify all exterior dimensions and room labels.")
    return RuleResult(rule_id="SK-3", rule_name="Dimensions", status=RuleStatus.PASS, message="Dimension-like sketch evidence detected.")


@rule(id="SK-4", name="Outbuildings and Structures")
def validate_sketch_outbuildings(ctx: ValidationContext) -> RuleResult:
    if re.search(r"garage|outbuilding|porch|deck|patio|balcony|pool", _text(ctx), re.I):
        return RuleResult(rule_id="SK-4", rule_name="Outbuildings and Structures", status=RuleStatus.VERIFY, message="Structure/feature language found. Verify all contributing structures are shown on sketch with dimensions.")
    return _verify("SK-4", "Outbuildings and Structures", "Automated structure detection is inconclusive. Verify garages, outbuildings, decks, porches, patios, and balconies.")


@rule(id="SK-5", name="Area Calculations")
def validate_area_calculations(ctx: ValidationContext) -> RuleResult:
    if re.search(r"gross living area|GLA|area calculation|total area", _text(ctx), re.I):
        return RuleResult(rule_id="SK-5", rule_name="Area Calculations", status=RuleStatus.VERIFY, message="Area-calculation evidence found. Verify it matches reported GLA.")
    return _verify("SK-5", "Area Calculations", "Area calculations not detected. Verify sketch area totals match GLA.")
