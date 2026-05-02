"""FHA Assignment Requirements (FHA-1 through FHA-14)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx): return ctx.raw_text or ""
def _verify(rule_id, name, message): return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="FHA-1", name="HUD Minimum Property Requirements")
def validate_fha_mpr(ctx): return _verify("FHA-1", "HUD Minimum Property Requirements", "Verify property meets HUD MPR/MPS or is made Subject To required repairs.")

@rule(id="FHA-2", name="FHA Case Number")
def validate_fha_case_number(ctx):
    if re.search(r"\bFHA Case (?:No\.?|Number)\b.*\d{3}-\d{7}", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-2", rule_name="FHA Case Number", status=RuleStatus.PASS, message="FHA case number evidence detected.")
    return RuleResult(rule_id="FHA-2", rule_name="FHA Case Number", status=RuleStatus.FAIL, message="FHA case number not detected in expected format.")

@rule(id="FHA-3", name="FHA Intended Use and Intended User")
def validate_fha_intended_use(ctx):
    if re.search(r"intended use|intended user|HUD|FHA", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-3", rule_name="FHA Intended Use and Intended User", status=RuleStatus.VERIFY, message="FHA/intended-use evidence found. Verify required FHA statements.")
    return _verify("FHA-3", "FHA Intended Use and Intended User", "FHA intended-use/user statements not detected.")

@rule(id="FHA-4", name="FHA Minimum Property Requirements Statement")
def validate_fha_mpr_statement(ctx): return _verify("FHA-4", "FHA Minimum Property Requirements Statement", "Verify FHA MPR statement is included and supported.")

@rule(id="FHA-5", name="FHA Comparable Sales Dating")
def validate_fha_comp_dating(ctx): return _verify("FHA-5", "FHA Comparable Sales Dating", "Verify comparables 1, 2, and 3 are within 12 months or fully explained.")

@rule(id="FHA-6", name="FHA Repairs")
def validate_fha_repairs(ctx):
    if re.search(r"subject to repairs?|required repair|defective|safety", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-6", rule_name="FHA Repairs", status=RuleStatus.VERIFY, message="Repair/safety language found. Verify FHA repair treatment.")
    return _verify("FHA-6", "FHA Repairs", "Automated FHA repair detection is inconclusive. Verify systems, safety, and Subject To conditions.")

@rule(id="FHA-7", name="Space Heater as Primary Heat")
def validate_fha_space_heater(ctx):
    if re.search(r"space heater", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-7", rule_name="Space Heater as Primary Heat", status=RuleStatus.VERIFY, message="Space heater language found. Verify FHA acceptability as primary heat.")
    return RuleResult(rule_id="FHA-7", rule_name="Space Heater as Primary Heat", status=RuleStatus.PASS, message="No space-heater trigger language detected.")

@rule(id="FHA-8", name="Security Bars on Windows")
def validate_fha_security_bars(ctx):
    if re.search(r"security bars?|release latch", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-8", rule_name="Security Bars on Windows", status=RuleStatus.VERIFY, message="Security bar language found. Verify quick-release/code compliance.")
    return RuleResult(rule_id="FHA-8", rule_name="Security Bars on Windows", status=RuleStatus.PASS, message="No security-bar trigger language detected.")

@rule(id="FHA-9", name="FHA Photo Requirements")
def validate_fha_photos(ctx): return _verify("FHA-9", "FHA Photo Requirements", "Verify FHA front/rear/side/attic/crawl-space photo requirements.")

@rule(id="FHA-10", name="Estimated Remaining Economic Life")
def validate_fha_economic_life(ctx):
    if re.search(r"remaining economic life.*(?:\d+)", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-10", rule_name="Estimated Remaining Economic Life", status=RuleStatus.PASS, message="Remaining economic life evidence detected.")
    return _verify("FHA-10", "Estimated Remaining Economic Life", "Remaining economic life not detected. Verify FHA requirement.")

@rule(id="FHA-11", name="Attic/Crawl Space Inspection")
def validate_fha_attic_crawl(ctx):
    if re.search(r"attic|crawl space", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-11", rule_name="Attic/Crawl Space Inspection", status=RuleStatus.VERIFY, message="Attic/crawl-space evidence found. Verify head-and-shoulders inspection comments/photos.")
    return _verify("FHA-11", "Attic/Crawl Space Inspection", "Attic/crawl-space inspection evidence not detected.")

@rule(id="FHA-12", name="Well and Septic (FHA)")
def validate_fha_well_septic(ctx):
    if re.search(r"well|septic", _text(ctx), re.I):
        return RuleResult(rule_id="FHA-12", rule_name="Well and Septic (FHA)", status=RuleStatus.VERIFY, message="Well/septic language found. Verify FHA distance, hookup, and marketability requirements.")
    return RuleResult(rule_id="FHA-12", rule_name="Well and Septic (FHA)", status=RuleStatus.PASS, message="No well/septic evidence detected.")

@rule(id="FHA-13", name="FHA Appliances")
def validate_fha_appliances(ctx): return _verify("FHA-13", "FHA Appliances", "Verify built-in appliances were operated and operational status is stated.")

@rule(id="FHA-14", name="FHA Sketch Requirements")
def validate_fha_sketch(ctx): return _verify("FHA-14", "FHA Sketch Requirements", "Verify sketch includes all structures and covered/uncovered designations.")
