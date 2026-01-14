"""
Improvement Section Rules (I-1 through I-13)
Validation rules for the Improvements section of appraisal reports.
"""

import re
from typing import List, Optional

from app.models.appraisal import ValidationContext
from app.rule_engine.engine import DataMissingException, RuleResult, RuleStatus, rule


def _check_addenda(ctx: ValidationContext, keywords: List[str]) -> bool:
    if not ctx.addenda_text:
        return False
    addenda_lower = ctx.addenda_text.lower()
    return any(kw.lower() in addenda_lower for kw in keywords)


def _is_addenda_referenced(text: Optional[str]) -> bool:
    if not text:
        return False
    patterns = [
        r"see\s+(?:attached\s+)?addend[um|a]",
        r"refer\s+to\s+(?:attached\s+)?addend[um|a]",
        r"see\s+attached",
    ]
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in patterns)


def _non_empty(value: Optional[str]) -> bool:
    return bool(value and str(value).strip())


def _is_none_selected(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"none", "no", "n/a", "na"}


def _contains_any(text: Optional[str], keywords: List[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(k.lower() in low for k in keywords)


@rule(id="I-1", name="General Description")
def validate_improvement_general_description(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    missing = []
    if imp.units_count is None:
        missing.append("Units")
    if not _non_empty(imp.stories):
        missing.append("Stories")
    if not _non_empty(imp.improvement_type):
        missing.append("Type")
    if not _non_empty(imp.construction_status):
        missing.append("Existing/Proposed/Under Construction")
    if not _non_empty(imp.design_style):
        missing.append("Design Style")
    if imp.year_built is None:
        missing.append("Year Built")
    if imp.effective_age is None:
        missing.append("Effective Age")

    if missing:
        raise DataMissingException(", ".join(missing))

    return RuleResult(
        rule_id="I-1",
        rule_name="General Description",
        status=RuleStatus.PASS,
        message="General Description fields are completed."
    )


@rule(id="I-2", name="Foundation")
def validate_improvement_foundation(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    missing = []
    if not _non_empty(imp.foundation):
        missing.append("Foundation")

    # Evidence checkboxes should be explicitly answered when present in form
    evidence_fields = [
        ("Evidence of Dampness", imp.evidence_dampness),
        ("Evidence of Settlement", imp.evidence_settlement),
        ("Evidence of Infestation", imp.evidence_infestation),
    ]
    for label, val in evidence_fields:
        if val is None:
            missing.append(label)

    if missing:
        raise DataMissingException(", ".join(missing))

    # Sales grid match is not currently possible with extracted data; keep as VERIFY reminder.
    return RuleResult(
        rule_id="I-2",
        rule_name="Foundation",
        status=RuleStatus.VERIFY,
        message="Foundation fields are present. Verify Foundation matches Sales Comparison grid section.",
        review_required=True,
    )


@rule(id="I-3", name="Exterior Description")
def validate_improvement_exterior_description(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    missing = []
    if not _non_empty(imp.foundation_walls):
        missing.append("Foundation Walls")
    if not _non_empty(imp.exterior_walls):
        missing.append("Exterior Walls")
    if not _non_empty(imp.roof_surface):
        missing.append("Roof Surface")
    if not _non_empty(imp.gutters_downspouts):
        missing.append("Gutters & Downspouts")
    if not _non_empty(imp.window_type):
        missing.append("Window Type")
    if not _non_empty(imp.storm_sash_screens):
        missing.append("Storm Sash/Screens")

    if missing:
        raise DataMissingException(", ".join(missing))

    return RuleResult(
        rule_id="I-3",
        rule_name="Exterior Description",
        status=RuleStatus.VERIFY,
        message="Exterior Description fields are present. Verify values match Sales Comparison grid section.",
        review_required=True,
    )


@rule(id="I-4", name="Interior Description")
def validate_improvement_interior_description(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    missing = []
    for name, val in [
        ("Floors", imp.floors),
        ("Walls", imp.walls),
        ("Trim/Finish", imp.trim_finish),
        ("Bath Floor", imp.bath_floor),
        ("Bath Wainscot", imp.bath_wainscot),
    ]:
        if not _non_empty(val):
            missing.append(name)

    if missing:
        raise DataMissingException(", ".join(missing))

    # Car storage rule
    if _is_none_selected(imp.car_storage):
        cars = [imp.driveway_cars, imp.garage_cars, imp.carport_cars]
        if any((c or 0) != 0 for c in cars):
            return RuleResult(
                rule_id="I-4",
                rule_name="Interior Description",
                status=RuleStatus.FAIL,
                message="Car Storage is 'None' but one or more '# of cars' fields are not 0."
            )
        if _non_empty(imp.driveway_surface):
            return RuleResult(
                rule_id="I-4",
                rule_name="Interior Description",
                status=RuleStatus.FAIL,
                message="Car Storage is 'None' but Driveway Surface is populated; should be blank."
            )

    # Driveway note - heuristic
    if _is_none_selected(imp.car_storage) and _non_empty(imp.driveway_surface):
        return RuleResult(
            rule_id="I-4",
            rule_name="Interior Description",
            status=RuleStatus.WARNING,
            message="Car Storage is 'None' but driveway surface suggests a driveway exists. Verify Car Storage selection.",
            review_required=True,
        )

    return RuleResult(
        rule_id="I-4",
        rule_name="Interior Description",
        status=RuleStatus.PASS,
        message="Interior Description fields are completed and car storage consistency checks passed."
    )


@rule(id="I-5", name="Utilities")
def validate_improvement_utilities(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if not _non_empty(imp.utilities_status):
        raise DataMissingException("Utilities status")

    low = imp.utilities_status.lower().strip()
    if not any(k in low for k in ["on", "off", "not on", "not operating", "unknown", "n/a", "na"]):
        return RuleResult(
            rule_id="I-5",
            rule_name="Utilities",
            status=RuleStatus.WARNING,
            message="Utilities status is present but does not clearly state whether utilities were ON at time of inspection. Verify wording.",
            details={"utilities_status": imp.utilities_status},
            review_required=True,
        )

    return RuleResult(
        rule_id="I-5",
        rule_name="Utilities",
        status=RuleStatus.PASS,
        message="Utilities status indicates whether utilities were ON/OFF at time of inspection."
    )


@rule(id="I-6", name="Appliances")
def validate_improvement_appliances(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    # Field must be completed as applicable; treat missing list as VERIFY (extraction often weak)
    if imp.built_in_appliances is None:
        raise DataMissingException("Built-in Appliances")

    # FHA requirement: operational statement
    stmt = imp.built_in_appliances_operational_statement or ""

    if imp.built_in_appliances and not _non_empty(stmt):
        # allow addenda ref
        if _is_addenda_referenced(stmt) and _check_addenda(ctx, ["operate", "operational", "tested", "working", "not working"]):
            return RuleResult(
                rule_id="I-6",
                rule_name="Appliances",
                status=RuleStatus.PASS,
                message="Built-in appliance operational statement was found in addenda."
            )

        return RuleResult(
            rule_id="I-6",
            rule_name="Appliances",
            status=RuleStatus.WARNING,
            message="Built-in appliances are listed but an operational status statement is missing. FHA requires the appraiser to operate built-in appliances and state operational status.",
            review_required=True,
        )

    return RuleResult(
        rule_id="I-6",
        rule_name="Appliances",
        status=RuleStatus.PASS,
        message="Appliance field appears completed; verify only built-in items are included."
    )


@rule(id="I-7", name="Above Grade Room Count")
def validate_improvement_above_grade_room_count(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    missing = []
    for name, val in [
        ("Total Rooms", imp.total_rooms),
        ("Bedrooms", imp.bedrooms),
        ("Baths", imp.baths),
        ("GLA", imp.gla),
    ]:
        if val is None:
            missing.append(name)

    if missing:
        raise DataMissingException(", ".join(missing))

    # Below-grade exclusion / Sales grid match not currently extractable; keep VERIFY.
    return RuleResult(
        rule_id="I-7",
        rule_name="Above Grade Room Count",
        status=RuleStatus.VERIFY,
        message="Above-grade room count fields are present. Verify below-grade areas are excluded and counts match Sales Comparison grid.",
        review_required=True,
    )


@rule(id="I-8", name="Additional Features")
def validate_improvement_additional_features(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if imp.additional_features is None:
        raise DataMissingException("Additional features")

    val = (imp.additional_features or "").strip()
    if not val:
        return RuleResult(
            rule_id="I-8",
            rule_name="Additional Features",
            status=RuleStatus.WARNING,
            message="Additional features field is blank. If none, state 'NONE'.",
            review_required=True,
        )

    if val.upper() == "NONE":
        return RuleResult(
            rule_id="I-8",
            rule_name="Additional Features",
            status=RuleStatus.PASS,
            message="Additional features correctly states NONE."
        )

    # If present, encourage energy efficient items; do not fail if missing.
    if not _contains_any(val, ["energy", "efficient", "insulation", "solar", "low-e", "heat pump", "tankless"]):
        return RuleResult(
            rule_id="I-8",
            rule_name="Additional Features",
            status=RuleStatus.WARNING,
            message="Additional features provided but no obvious energy efficient items detected. Verify energy-efficient items are listed if present.",
            review_required=True,
        )

    return RuleResult(
        rule_id="I-8",
        rule_name="Additional Features",
        status=RuleStatus.PASS,
        message="Additional features field is populated and includes energy-related items."
    )


@rule(id="I-9", name="Property Condition Rating")
def validate_improvement_condition_rating(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if not _non_empty(imp.condition_rating):
        raise DataMissingException("Condition of the Property (C1-C6)")

    rating = imp.condition_rating.strip().upper()
    if rating not in {"C1", "C2", "C3", "C4", "C5", "C6"}:
        return RuleResult(
            rule_id="I-9",
            rule_name="Property Condition Rating",
            status=RuleStatus.FAIL,
            message=f"Condition rating '{imp.condition_rating}' is not UAD compliant (must be C1-C6)."
        )

    # Cross-validation w/ photos is not available here; keep VERIFY reminder.
    return RuleResult(
        rule_id="I-9",
        rule_name="Property Condition Rating",
        status=RuleStatus.VERIFY,
        message="Condition rating is UAD compliant. Verify rating matches photos/commentary and is supported by effective age.",
        review_required=True,
    )


@rule(id="I-10", name="Adverse Conditions Affecting Livability")
def validate_improvement_adverse_conditions_livability(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if imp.adverse_conditions_affecting_livability is None:
        raise DataMissingException("Adverse conditions affecting livability (Yes/No)")

    if imp.adverse_conditions_affecting_livability:
        desc = imp.adverse_conditions_commentary or ""
        if not (len(desc.strip()) > 10 or (_is_addenda_referenced(desc) and _check_addenda(ctx, ["livability", "unsafe", "health", "safety", "structural", "soundness"]))):
            return RuleResult(
                rule_id="I-10",
                rule_name="Adverse Conditions Affecting Livability",
                status=RuleStatus.WARNING,
                message="Adverse conditions are marked YES but supporting commentary is missing or insufficient.",
                review_required=True,
            )

    return RuleResult(
        rule_id="I-10",
        rule_name="Adverse Conditions Affecting Livability",
        status=RuleStatus.PASS,
        message="Adverse conditions affecting livability answered."
    )


@rule(id="I-11", name="Neighborhood Conformity")
def validate_improvement_neighborhood_conformity(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if imp.conforms_to_neighborhood is None:
        raise DataMissingException("Does property conform to neighborhood? (Yes/No)")

    if imp.conforms_to_neighborhood is False:
        comment = imp.neighborhood_conformity_commentary or ""

        keywords = ["does not conform", "nonconform", "overbuilt", "rebuilt", "destroyed", "50%", "zoning", "marketability"]
        if _is_addenda_referenced(comment):
            if _check_addenda(ctx, keywords):
                return RuleResult(
                    rule_id="I-11",
                    rule_name="Neighborhood Conformity",
                    status=RuleStatus.PASS,
                    message="Neighborhood conformity is NO and required explanation appears to be provided in addenda."
                )
            return RuleResult(
                rule_id="I-11",
                rule_name="Neighborhood Conformity",
                status=RuleStatus.WARNING,
                message="Neighborhood conformity is NO and refers to addenda, but key explanation keywords were not found in addenda.",
                review_required=True,
            )

        if len(comment.strip()) < 30:
            return RuleResult(
                rule_id="I-11",
                rule_name="Neighborhood Conformity",
                status=RuleStatus.FAIL,
                message="Neighborhood conformity is NO but extensive commentary is missing."
            )

        if not _contains_any(comment, ["why", "does not", "nonconform", "overbuilt", "rebuilt", "destroyed", "50%"]):
            return RuleResult(
                rule_id="I-11",
                rule_name="Neighborhood Conformity",
                status=RuleStatus.WARNING,
                message="Neighborhood conformity is NO but commentary may not address required topics (why, rebuildability if destroyed >50%, overbuilt, zoning/marketability).",
                review_required=True,
            )

    return RuleResult(
        rule_id="I-11",
        rule_name="Neighborhood Conformity",
        status=RuleStatus.PASS,
        message="Neighborhood conformity answered."
    )


@rule(id="I-12", name="Additions to Subject")
def validate_improvement_additions(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if imp.additions_present is None:
        return RuleResult(
            rule_id="I-12",
            rule_name="Additions to Subject",
            status=RuleStatus.SKIPPED,
            message="Additions presence was not detected."
        )

    if imp.additions_present:
        comment = imp.additions_commentary or ""
        required_topics = ["permitted", "permit", "conform", "quality", "functional", "utility", "marketability", "zoning"]
        safety_topics = ["health", "safety", "hazard", "unsafe", "remediation", "remove", "cost to cure", "subject to"]

        if _is_addenda_referenced(comment):
            if _check_addenda(ctx, required_topics):
                return RuleResult(
                    rule_id="I-12",
                    rule_name="Additions to Subject",
                    status=RuleStatus.PASS,
                    message="Additions are present and required commentary appears in addenda."
                )
            return RuleResult(
                rule_id="I-12",
                rule_name="Additions to Subject",
                status=RuleStatus.WARNING,
                message="Additions are present and refers to addenda, but required topics were not found.",
                review_required=True,
            )

        if len(comment.strip()) < 30:
            return RuleResult(
                rule_id="I-12",
                rule_name="Additions to Subject",
                status=RuleStatus.FAIL,
                message="Additions are present but required commentary is missing (permitted, conformity, marketability/zoning)."
            )

        if not _contains_any(comment, required_topics):
            return RuleResult(
                rule_id="I-12",
                rule_name="Additions to Subject",
                status=RuleStatus.WARNING,
                message="Additions commentary may be missing required topics (permit status, conformity/utility, marketability/zoning).",
                review_required=True,
            )

        if _contains_any(comment, safety_topics):
            return RuleResult(
                rule_id="I-12",
                rule_name="Additions to Subject",
                status=RuleStatus.VERIFY,
                message="Additions commentary suggests a potential health/safety issue. Verify appraisal is made 'Subject To' remediation/removal with cost to cure.",
                review_required=True,
            )

    return RuleResult(
        rule_id="I-12",
        rule_name="Additions to Subject",
        status=RuleStatus.PASS,
        message="Additions to subject rule passed based on detected flags/commentary."
    )


@rule(id="I-13", name="Security Bars")
def validate_improvement_security_bars(ctx: ValidationContext) -> RuleResult:
    imp = ctx.report.improvements

    if imp.security_bars_present is None:
        return RuleResult(
            rule_id="I-13",
            rule_name="Security Bars",
            status=RuleStatus.SKIPPED,
            message="Security bars presence was not detected."
        )

    if imp.security_bars_present:
        comment = imp.security_bars_commentary or ""
        keywords = ["release", "latch", "quick", "egress", "code", "building code", "local code"]

        if _is_addenda_referenced(comment):
            if _check_addenda(ctx, keywords):
                return RuleResult(
                    rule_id="I-13",
                    rule_name="Security Bars",
                    status=RuleStatus.PASS,
                    message="Security bars are present and safety/code commentary appears in addenda."
                )
            return RuleResult(
                rule_id="I-13",
                rule_name="Security Bars",
                status=RuleStatus.WARNING,
                message="Security bars are present and refers to addenda, but safety/code keywords were not found.",
                review_required=True,
            )

        if not _contains_any(comment, keywords):
            return RuleResult(
                rule_id="I-13",
                rule_name="Security Bars",
                status=RuleStatus.WARNING,
                message="Security bars are present. Commentary should address safety release latches and/or code compliance.",
                review_required=True,
            )

    return RuleResult(
        rule_id="I-13",
        rule_name="Security Bars",
        status=RuleStatus.PASS,
        message="Security bars rule passed based on detected flags/commentary."
    )
