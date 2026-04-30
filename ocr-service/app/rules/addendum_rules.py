"""Addendum & Commentary Rules (ADD-1 through ADD-9)."""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult
from app.models.appraisal import ValidationContext


def _text(ctx: ValidationContext) -> str:
    return ctx.raw_text or ""


def _verify(rule_id: str, name: str, message: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True)


@rule(id="ADD-1", name="Commentary Standards")
def validate_commentary_standards(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"addendum|comments?|sales comparison|reconciliation", text, re.I):
        return _verify("ADD-1", "Commentary Standards", "Addendum/commentary text not extracted. Verify headers and report-specific commentary.")
    if re.search(r"typical for the area|no adverse conditions were noted|see attached addendum", text, re.I):
        return RuleResult(rule_id="ADD-1", rule_name="Commentary Standards", status=RuleStatus.WARNING, message="Potential canned/generic commentary detected. Verify addendum is specific to this report.")
    return RuleResult(rule_id="ADD-1", rule_name="Commentary Standards", status=RuleStatus.PASS, message="Addendum/commentary evidence found.")


@rule(id="ADD-2", name="Comparable Selection Commentary")
def validate_comp_selection_commentary(ctx: ValidationContext) -> RuleResult:
    commentary = ctx.report.sales_comparison.summary_commentary or _text(ctx)
    if not re.search(r"selected because|selected based on|most similar|proximity|bracket", commentary, re.I):
        return _verify("ADD-2", "Comparable Selection Commentary", "Comparable selection reasoning was not detected. Verify the appraiser explains why comps were chosen.")
    return RuleResult(rule_id="ADD-2", rule_name="Comparable Selection Commentary", status=RuleStatus.PASS, message="Comparable selection rationale evidence found.")


@rule(id="ADD-3", name="Dated Sales Commentary")
def validate_dated_sales_commentary(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"dated sale|over\s+12\s+months|distant comparable|outside.*neighborhood", text, re.I):
        return RuleResult(rule_id="ADD-3", rule_name="Dated Sales Commentary", status=RuleStatus.WARNING, message="Dated/distant comparable language found. Verify detailed explanation is adequate.")
    return _verify("ADD-3", "Dated Sales Commentary", "Automated dated/distant sale detection is inconclusive. Verify if any comps need explanatory commentary.")


@rule(id="ADD-4", name="Market Conditions Addendum (1004MC)")
def validate_1004mc_req(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"1004MC|Market Conditions Addendum", text, re.I):
        return RuleResult(rule_id="ADD-4", rule_name="Market Conditions Addendum (1004MC)", status=RuleStatus.PASS, message="1004MC / Market Conditions Addendum evidence found.")
    return _verify("ADD-4", "Market Conditions Addendum (1004MC)", "1004MC not extracted. Verify it is included for FHA/USDA or client-required assignments.")


@rule(id="ADD-5", name="1004MC Inventory Analysis")
def validate_1004mc_inventory(ctx: ValidationContext) -> RuleResult:
    if not re.search(r"Inventory\s+Analysis|Absorption\s+Rate|Months\s+of\s+Housing\s+Supply|Total\s+#\s+of\s+Comparable", _text(ctx), re.I):
        return _verify("ADD-5", "1004MC Inventory Analysis", "1004MC inventory fields not extracted. Verify lightly shaded areas are completed or explained.")
    return RuleResult(rule_id="ADD-5", rule_name="1004MC Inventory Analysis", status=RuleStatus.WARNING, message="1004MC inventory evidence found. Verify all required shaded areas are complete.")


@rule(id="ADD-6", name="1004MC Comparables Matching")
def validate_1004mc_matching(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"Total\s+#\s+of\s+Comparable\s+Sales", text, re.I) and re.search(r"There\s+are\s+\d+\s+comparable", text, re.I):
        return RuleResult(rule_id="ADD-6", rule_name="1004MC Comparables Matching", status=RuleStatus.WARNING, message="1004MC and sales-grid comparable counts were detected. Verify the counts match exactly.")
    return _verify("ADD-6", "1004MC Comparables Matching", "1004MC-to-sales-grid count matching requires extracted 1004MC counts. Verify active listing and sales totals match the grid.")


@rule(id="ADD-7", name="1004MC Overall Trend")
def validate_1004mc_trend(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if re.search(r"\bIncreasing\b.*\bStable\b.*\bDeclining\b", text, re.I | re.S):
        if re.search(r"\bStable\b", text, re.I):
            return RuleResult(rule_id="ADD-7", rule_name="1004MC Overall Trend", status=RuleStatus.WARNING, message="1004MC trend grid detected. Verify selected trends are supported and time adjustments are applied/explained.")
        return _verify("ADD-7", "1004MC Overall Trend", "1004MC trend grid detected but selected trend could not be determined.")
    return _verify("ADD-7", "1004MC Overall Trend", "1004MC trend fields not extracted. Verify trends with at least two data points.")


@rule(id="ADD-8", name="1004MC Condo/Co-Op")
def validate_1004mc_condo(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if ctx.report.form_type == "1073" or re.search(r"condo|co-?op", text, re.I):
        return _verify("ADD-8", "1004MC Condo/Co-Op", "Condo/Co-op language detected. Verify all condo/co-op 1004MC shaded areas are completed.")
    return RuleResult(rule_id="ADD-8", rule_name="1004MC Condo/Co-Op", status=RuleStatus.SKIPPED, message="Not a condo/co-op report based on extracted evidence.")


@rule(id="ADD-9", name="USPAP 2014 Addendum")
def validate_uspap_addendum(ctx: ValidationContext) -> RuleResult:
    text = _text(ctx)
    if not re.search(r"USPAP|exposure time|appraisal report|restricted appraisal report", text, re.I):
        return _verify("ADD-9", "USPAP 2014 Addendum", "USPAP addendum fields not extracted. Verify report type, exposure time, and prior-service certification.")
    missing = []
    if not re.search(r"Appraisal\s+Report|Restricted\s+Appraisal\s+Report", text, re.I):
        missing.append("reporting option")
    if not re.search(r"Exposure\s+Time.*\d+\s*(?:Days?|months?)", text, re.I | re.S):
        missing.append("reasonable exposure time")
    if missing:
        return _verify("ADD-9", "USPAP 2014 Addendum", f"USPAP addendum found but missing/unclear: {', '.join(missing)}.")
    return RuleResult(rule_id="ADD-9", rule_name="USPAP 2014 Addendum", status=RuleStatus.WARNING, message="USPAP addendum evidence found. Verify checked option and certifications are complete.")
