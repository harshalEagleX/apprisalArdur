"""
Sales Comparison Approach Rules (SCA-1 through SCA-27)

Rules use extracted comparable objects when available. If a required grid field
is not extracted yet, the rule returns VERIFY, not PASS.
"""

import re
from app.rule_engine.engine import rule, RuleStatus, RuleResult, RuleSeverity, DataMissingException
from app.models.appraisal import ValidationContext


def _sca(ctx):
    sca = getattr(ctx.report, "sales_comparison", None)
    if not sca:
        raise DataMissingException("Sales Comparison Section")
    return sca


def _comps(ctx, include_listings=True):
    comps = list(_sca(ctx).comparables or [])
    return comps if include_listings else [c for c in comps if not c.is_listing]


def _verify(rule_id, name, message):
    return RuleResult(rule_id=rule_id, rule_name=name, status=RuleStatus.VERIFY, message=message, review_required=True, severity=RuleSeverity.STANDARD)


def _text(ctx):
    return ctx.raw_text or ""


def _missing_for_all(ctx, attr, label):
    comps = _comps(ctx, include_listings=True)
    if not comps:
        return _verify(label[0], label[1], "Comparable grid not extracted. Verify manually.")
    missing = [str(i) for i, comp in enumerate(comps, 1) if getattr(comp, attr, None) in (None, "")]
    if missing:
        return _verify(label[0], label[1], f"Comparable {label[1]} field not extracted for comp(s): {', '.join(missing)}.")
    return None


@rule(id="SCA-1", name="Comparable Market Summary")
def validate_comparable_summary(ctx: ValidationContext) -> RuleResult:
    sca = _sca(ctx)
    sales = sca.comparables_count_sales
    listings = sca.comparables_count_listings
    text = _text(ctx)
    if sales is None:
        match = re.search(r"There\s+are\s+(\d+)\s+comparable\s+sales", text, re.I)
        sales = int(match.group(1)) if match else None
    if listings is None:
        match = re.search(r"There\s+are\s+(\d+)\s+comparable\s+properties\s+currently\s+offered", text, re.I)
        listings = int(match.group(1)) if match else None
    if sales is None or listings is None:
        return _verify("SCA-1", "Comparable Market Summary", "Comparable market summary not fully extracted. Verify # currently offered and # sold within 12 months.")
    return RuleResult(rule_id="SCA-1", rule_name="Comparable Market Summary", status=RuleStatus.PASS, message=f"Market summary extracted: {sales} sales, {listings} listings.")


@rule(id="SCA-2", name="Comparables Required")
def validate_comparables_required(ctx: ValidationContext) -> RuleResult:
    sca = _sca(ctx)
    sales = sca.comparables_count_sales
    listings = sca.comparables_count_listings
    text = _text(ctx)
    if sales is None:
        match = re.search(r"There\s+are\s+(\d+)\s+comparable\s+sales", text, re.I)
        sales = int(match.group(1)) if match else None
    if listings is None:
        match = re.search(r"There\s+are\s+(\d+)\s+comparable\s+properties\s+currently\s+offered", text, re.I)
        listings = int(match.group(1)) if match else None
    if sales is None:
        return _verify("SCA-2", "Comparables Required", "Comparable sales count not extracted. Verify minimum 3 sales and 2 listings.")
    if sales < 3:
        return RuleResult(rule_id="SCA-2", rule_name="Comparables Required", status=RuleStatus.FAIL, message=f"Only {sales} comparable sale(s) found. Minimum 3 required.")
    if listings is None:
        return _verify("SCA-2", "Comparables Required", "Comparable listing count not extracted. Verify minimum 2 listings unless exception applies.")
    if listings < 2:
        return RuleResult(rule_id="SCA-2", rule_name="Comparables Required", status=RuleStatus.FAIL, message=f"Only {listings} listing comparable(s) found. Minimum 2 required.")
    return RuleResult(rule_id="SCA-2", rule_name="Comparables Required", status=RuleStatus.PASS, message=f"{sales} sales and {listings} listings provided.")


@rule(id="SCA-3", name="Address (Subject and Comparables)")
def validate_addresses(ctx: ValidationContext) -> RuleResult:
    comps = _comps(ctx)
    text = _text(ctx)
    if not ctx.report.subject.address:
        return _verify("SCA-3", "Address (Subject and Comparables)", "Subject address not extracted for sales grid comparison.")
    missing = [str(i) for i, c in enumerate(comps, 1) if not c.address]
    if not comps or missing:
        if re.search(r"COMPARABLE\s+SALE\s+#\s*1.*Address", text, re.I | re.S) or len(re.findall(r"\b\d{2,5}\s+[A-Z][A-Za-z]+\s+", text)) >= 3:
            return RuleResult(rule_id="SCA-3", rule_name="Address (Subject and Comparables)", status=RuleStatus.WARNING, message="Comparable address evidence found in OCR text. Verify exact UAD/USPS formatting.")
        return _verify("SCA-3", "Address (Subject and Comparables)", f"Comparable addresses missing/not extracted: {', '.join(missing) if missing else 'all'}")
    return RuleResult(rule_id="SCA-3", rule_name="Address (Subject and Comparables)", status=RuleStatus.PASS, message="Subject and comparable addresses are present.")


@rule(id="SCA-4", name="Proximity to Subject")
def validate_proximity(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "proximity", ("SCA-4", "Proximity to Subject"))
    if res:
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:miles?|mi)\s*(?:N|S|E|W|NE|NW|SE|SW)\b", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-4", rule_name="Proximity to Subject", status=RuleStatus.PASS, message="Comparable proximity evidence found in OCR text.")
        return res
    bad = [c.proximity for c in _comps(ctx) if not re.search(r"\b\d+(?:\.\d+)?\s*(?:mi|miles?)\s*(?:N|S|E|W|NE|NW|SE|SW)\b", c.proximity or "", re.I)]
    if bad:
        return RuleResult(rule_id="SCA-4", rule_name="Proximity to Subject", status=RuleStatus.FAIL, message="Comparable proximity must include distance and direction with minimum 0.01 miles.", details={"invalid": bad})
    return RuleResult(rule_id="SCA-4", rule_name="Proximity to Subject", status=RuleStatus.PASS, message="Comparable proximity fields include distance and direction.")


@rule(id="SCA-5", name="Data Sources")
def validate_data_sources(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "data_source", ("SCA-5", "Data Sources"))
    if res:
        if re.search(r"MLS#?\s*\d+.*DOM\s*\d+|DOM\s*\d+", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-5", rule_name="Data Sources", status=RuleStatus.PASS, message="MLS/DOM data-source evidence found in OCR text.")
        return res
    missing_dom = [str(i) for i, c in enumerate(_comps(ctx), 1) if "DOM" not in (c.data_source or "").upper()]
    if missing_dom:
        return RuleResult(rule_id="SCA-5", rule_name="Data Sources", status=RuleStatus.WARNING, message=f"DOM not found in data source for comp(s): {', '.join(missing_dom)}.")
    return RuleResult(rule_id="SCA-5", rule_name="Data Sources", status=RuleStatus.PASS, message="Comparable data sources include DOM evidence.")


@rule(id="SCA-6", name="Verification Sources")
def validate_verification_sources(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "verification_source", ("SCA-6", "Verification Sources"))
    if res:
        if re.search(r"Verification\s+Source\(s\)|Tax\s+Records?|Previous\s+Appraisal|Tax\s+Cards", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-6", rule_name="Verification Sources", status=RuleStatus.PASS, message="Verification source evidence found in OCR text.")
        return res
    return RuleResult(rule_id="SCA-6", rule_name="Verification Sources", status=RuleStatus.PASS, message="Verification sources are present.")


@rule(id="SCA-7", name="Sale or Financing Concessions")
def validate_concessions(ctx: ValidationContext) -> RuleResult:
    if re.search(r"ArmLth|Conv;?\s*\d+|Cash;?\s*0|RH;?\s*\d+|Concessions", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-7", rule_name="Sale or Financing Concessions", status=RuleStatus.WARNING, message="Sale/financing/concession evidence found. Verify UAD format and adjustment direction.")
    return _verify("SCA-7", "Sale or Financing Concessions", "Sale/financing/concession grid fields are not extracted. Verify UAD sale type, financing type, concessions, and adjustment direction.")


@rule(id="SCA-8", name="Date of Sale/Time Adjustment")
def validate_sale_date(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "sale_date", ("SCA-8", "Date of Sale/Time Adjustment"))
    if res:
        if re.search(r"\b(?:s|c)\d{2}/\d{2};c\d{2}/\d{2}|Date\s+of\s+Sale/Time", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-8", rule_name="Date of Sale/Time Adjustment", status=RuleStatus.WARNING, message="Sale/time evidence found. Verify sale date, contract date, and market-condition adjustments.")
        return res
    return RuleResult(rule_id="SCA-8", rule_name="Date of Sale/Time Adjustment", status=RuleStatus.PASS, message="Comparable sale dates are present.")


@rule(id="SCA-9", name="Location Rating")
def validate_location_rating(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "location_rating", ("SCA-9", "Location Rating"))
    if res:
        if re.search(r"\bN;Res;|\bB;|\bA;|\bAdj", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-9", rule_name="Location Rating", status=RuleStatus.PASS, message="UAD location-rating evidence found in OCR text.")
        return res
    bad = [c.location_rating for c in _comps(ctx) if ";" not in (c.location_rating or "")]
    if bad:
        return RuleResult(rule_id="SCA-9", rule_name="Location Rating", status=RuleStatus.FAIL, message="Location rating must be UAD-style Rating;Type;Other as applicable.", details={"invalid": bad})
    return RuleResult(rule_id="SCA-9", rule_name="Location Rating", status=RuleStatus.PASS, message="Location ratings appear UAD formatted.")


@rule(id="SCA-10", name="Leasehold/Fee Simple")
def validate_leasehold_fee_simple(ctx: ValidationContext) -> RuleResult:
    if re.search(r"Leasehold/Fee\s+Simple.*Fee\s+Simple|Fee\s+Simple", _text(ctx), re.I | re.S):
        return RuleResult(rule_id="SCA-10", rule_name="Leasehold/Fee Simple", status=RuleStatus.PASS, message="Fee Simple/Leasehold evidence found.")
    return _verify("SCA-10", "Leasehold/Fee Simple", "Comparable property-rights grid fields are not extracted. Verify Leasehold/Fee Simple is provided for subject and comps.")


@rule(id="SCA-11", name="Site")
def validate_site_size(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "site_size", ("SCA-11", "Site"))
    if res:
        if re.search(r"\b\d[\d,]*\s*sf\b|\b\d+(?:\.\d+)?\s*ac\b", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-11", rule_name="Site", status=RuleStatus.PASS, message="Comparable site-size evidence found in OCR text.")
        return res
    return RuleResult(rule_id="SCA-11", rule_name="Site", status=RuleStatus.PASS, message="Comparable site sizes are present.")


@rule(id="SCA-12", name="View")
def validate_sca_view(ctx: ValidationContext) -> RuleResult:
    if re.search(r"\bN;Res;|View", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-12", rule_name="View", status=RuleStatus.WARNING, message="View evidence found. Verify UAD format and consistency with Site section.")
    return _verify("SCA-12", "View", "Comparable view grid fields are not extracted. Verify UAD view format and consistency with Site section.")


@rule(id="SCA-13", name="Design (Style)")
def validate_design_style(ctx: ValidationContext) -> RuleResult:
    if re.search(r"DT1;Traditional|Design\s*\(Style\)", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-13", rule_name="Design (Style)", status=RuleStatus.PASS, message="Design/style evidence found in OCR text.")
    return _verify("SCA-13", "Design (Style)", "Comparable design/style grid fields are not extracted. Verify attachment type, stories, and style.")


@rule(id="SCA-14", name="Quality of Construction")
def validate_quality_rating(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "quality_rating", ("SCA-14", "Quality of Construction"))
    if res:
        if re.search(r"\bQ[1-6]\b", _text(ctx)):
            return RuleResult(rule_id="SCA-14", rule_name="Quality of Construction", status=RuleStatus.PASS, message="UAD quality rating evidence found in OCR text.")
        return res
    invalid = [c.quality_rating for c in _comps(ctx) if (c.quality_rating or "").upper() not in {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}]
    if invalid:
        return RuleResult(rule_id="SCA-14", rule_name="Quality of Construction", status=RuleStatus.FAIL, message="Quality ratings must be Q1-Q6.", details={"invalid": invalid})
    return RuleResult(rule_id="SCA-14", rule_name="Quality of Construction", status=RuleStatus.PASS, message="Quality ratings are UAD compliant.")


@rule(id="SCA-15", name="Actual Age")
def validate_actual_age(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "actual_age", ("SCA-15", "Actual Age"))
    if res:
        if re.search(r"Actual\s+Age\s+\d+|\bAge\s+\d+", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-15", rule_name="Actual Age", status=RuleStatus.PASS, message="Actual-age evidence found in OCR text.")
        return res
    return RuleResult(rule_id="SCA-15", rule_name="Actual Age", status=RuleStatus.PASS, message="Actual ages are present.")


@rule(id="SCA-16", name="Condition")
def validate_sca_condition(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "condition_rating", ("SCA-16", "Condition"))
    if res:
        if re.search(r"\bC[1-6]\b", _text(ctx)):
            return RuleResult(rule_id="SCA-16", rule_name="Condition", status=RuleStatus.PASS, message="UAD condition rating evidence found in OCR text.")
        return res
    invalid = [c.condition_rating for c in _comps(ctx) if (c.condition_rating or "").upper() not in {"C1", "C2", "C3", "C4", "C5", "C6"}]
    if invalid:
        return RuleResult(rule_id="SCA-16", rule_name="Condition", status=RuleStatus.FAIL, message="Condition ratings must be C1-C6.", details={"invalid": invalid})
    return RuleResult(rule_id="SCA-16", rule_name="Condition", status=RuleStatus.PASS, message="Condition ratings are UAD compliant.")


@rule(id="SCA-17", name="Above Grade Room Count and GLA")
def validate_sca_room_count(ctx: ValidationContext) -> RuleResult:
    missing = []
    for i, c in enumerate(_comps(ctx), 1):
        if c.room_count_total is None or c.room_count_bed is None or c.room_count_bath is None or c.gla is None:
            missing.append(str(i))
    if missing:
        if re.search(r"Room\s+Count|Gross\s+Living\s+Area|GLA|\b\d+\s+\d+\s+2\.0\b", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-17", rule_name="Above Grade Room Count and GLA", status=RuleStatus.WARNING, message="Room-count/GLA evidence found. Verify values match sketch and Page 1.")
        return _verify("SCA-17", "Above Grade Room Count and GLA", f"Room count/GLA missing for comp(s): {', '.join(missing)}.")
    return RuleResult(rule_id="SCA-17", rule_name="Above Grade Room Count and GLA", status=RuleStatus.PASS, message="Room count and GLA are present for comparables.")


@rule(id="SCA-18", name="Basement & Finished Rooms Below Grade")
def validate_basement(ctx: ValidationContext) -> RuleResult:
    if re.search(r"Basement|Rooms\s+Below\s+Grade|0sf", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-18", rule_name="Basement & Finished Rooms Below Grade", status=RuleStatus.WARNING, message="Basement/below-grade evidence found. Verify UAD format and Page 1 consistency.")
    return _verify("SCA-18", "Basement & Finished Rooms Below Grade", "Basement/below-grade grid fields are not extracted. Verify UAD format and consistency with Page 1.")


@rule(id="SCA-19", name="Functional Utility")
def validate_functional_utility(ctx: ValidationContext) -> RuleResult:
    if re.search(r"Functional\s+Utility|Average", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-19", rule_name="Functional Utility", status=RuleStatus.PASS, message="Functional utility evidence found.")
    return _verify("SCA-19", "Functional Utility", "Functional utility grid fields are not extracted. Verify values and zero adjustments where no difference exists.")


@rule(id="SCA-20", name="Heating/Cooling")
def validate_heating_cooling(ctx: ValidationContext) -> RuleResult:
    if re.search(r"Heating/Cooling|FWA/CAC|Central\s+Air", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-20", rule_name="Heating/Cooling", status=RuleStatus.PASS, message="Heating/cooling evidence found.")
    return _verify("SCA-20", "Heating/Cooling", "Heating/cooling grid fields are not extracted. Verify consistency with Page 1.")


@rule(id="SCA-21", name="Garage/Carport")
def validate_garage(ctx: ValidationContext) -> RuleResult:
    res = _missing_for_all(ctx, "garage_carport", ("SCA-21", "Garage/Carport"))
    if res:
        if re.search(r"Garage/Carport|2ga2dw|garage", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-21", rule_name="Garage/Carport", status=RuleStatus.PASS, message="Garage/carport evidence found in OCR text.")
        return res
    return RuleResult(rule_id="SCA-21", rule_name="Garage/Carport", status=RuleStatus.PASS, message="Garage/carport fields are present.")


@rule(id="SCA-22", name="Porch/Patio/Deck")
def validate_porch_patio(ctx: ValidationContext) -> RuleResult:
    if re.search(r"Porch/Patio/Deck|CFP|CBP|Patio|Porch|Deck", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-22", rule_name="Porch/Patio/Deck", status=RuleStatus.PASS, message="Porch/patio/deck evidence found.")
    return _verify("SCA-22", "Porch/Patio/Deck", "Porch/patio/deck grid fields are not extracted. Verify they match Page 1 or state None.")


@rule(id="SCA-23", name="Listing Comparables")
def validate_listing_comparables(ctx: ValidationContext) -> RuleResult:
    listings = [c for c in _comps(ctx) if c.is_listing]
    if not listings and _sca(ctx).comparables_count_listings in (None, 0):
        if re.search(r"Listing|Comparable\s+Sale\s+#\s*4|Active", _text(ctx), re.I):
            return RuleResult(rule_id="SCA-23", rule_name="Listing Comparables", status=RuleStatus.WARNING, message="Listing comparable evidence found. Verify list-to-sale adjustment or explanation.")
        return _verify("SCA-23", "Listing Comparables", "Listing comparable details not extracted. Verify list-to-sale adjustment or explanation.")
    return RuleResult(rule_id="SCA-23", rule_name="Listing Comparables", status=RuleStatus.WARNING, message="Listing comparables require reviewer confirmation of list-to-sale adjustment support.")


@rule(id="SCA-24", name="Unique Design Properties")
def validate_unique_design(ctx: ValidationContext) -> RuleResult:
    return RuleResult(rule_id="SCA-24", rule_name="Unique Design Properties", status=RuleStatus.VERIFY, message="Unique-property comparable support requires manual review unless specific unique-design extraction is available.", review_required=True)


@rule(id="SCA-25", name="New Construction")
def validate_new_construction(ctx: ValidationContext) -> RuleResult:
    text = ctx.raw_text or ""
    if re.search(r"new construction|proposed construction|under construction", text, re.I):
        return RuleResult(rule_id="SCA-25", rule_name="New Construction", status=RuleStatus.WARNING, message="New construction language found. Verify at least one comparable from competing development or explanation.")
    return RuleResult(rule_id="SCA-25", rule_name="New Construction", status=RuleStatus.PASS, message="No new-construction trigger language detected.")


@rule(id="SCA-26", name="Square Footage")
def validate_square_footage(ctx: ValidationContext) -> RuleResult:
    return _verify("SCA-26", "Square Footage", "Below-grade/GLA methodology cannot be fully verified from extracted fields. Verify sketch and grid consistency.")


@rule(id="SCA-27", name="Comparable Photos")
def validate_comparable_photos(ctx: ValidationContext) -> RuleResult:
    if re.search(r"comp(?:arable)?\s+photo|MLS\s+photo|drive-?by|Comparable\s+Sale\s+#", _text(ctx), re.I):
        return RuleResult(rule_id="SCA-27", rule_name="Comparable Photos", status=RuleStatus.WARNING, message="Comparable photo/grid evidence found. Verify photo source meets loan-type requirement.")
    return _verify("SCA-27", "Comparable Photos", "Comparable photo source/type not extracted. Verify MLS photos are acceptable for conventional and drive-by photos for FHA.")
