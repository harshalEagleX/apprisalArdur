"""Per-field plausibility gate (app.extraction.field_validators).

Locks in the type-confusion suppressions from the extraction overhaul: a value
that cannot belong to its field (state code in county, zip in a name, APN
fragment in taxes, HOA fee as GLA) is suppressed (value -> None, raw preserved),
while legitimate values survive untouched.
"""

from app.core.result import ExtractionResult
from app.extraction.field_validators import validate_results


def _r(name, value, conf=0.89):
    return ExtractionResult(canonical_name=name, document_type="appraisal_report",
                            value=value, extraction_method="uad_template",
                            confidence=conf, source_page=1)


def _run(d):
    merged = {k: _r(k, v) for k, v in d.items()}
    suppressed = validate_results(merged)
    return merged, suppressed


def test_type_confusion_values_are_suppressed():
    merged, n = _run({
        "county": "TN",                       # state code leaked into county
        "real_estate_taxes": "065",           # APN fragment
        "supervisory_appraiser_name": "24319",  # mailing zip
        "site_area_unit": "sf",
        "site_area": "129.45",                # a $/sf rate, not sq ft
    })
    assert merged["county"].value is None
    assert merged["real_estate_taxes"].value is None
    assert merged["supervisory_appraiser_name"].value is None
    assert merged["site_area"].value is None
    assert n >= 4


def test_raw_text_is_preserved_on_suppression():
    merged, _ = _run({"county": "TN"})
    assert merged["county"].value is None
    assert merged["county"].raw_source_text == "TN"      # P-5: input kept
    assert merged["county"].sanity_check_failed is True


def test_legitimate_values_survive():
    merged, n = _run({
        "county": "Sullivan",
        "real_estate_taxes": "1297",
        "site_area_unit": "sf",
        "site_area": "27311",
        "total_rooms": "7",
        "appraised_value": "356000",
    })
    assert merged["county"].value == "Sullivan"
    assert merged["real_estate_taxes"].value == "1297"
    assert merged["site_area"].value == "27311"
    assert merged["total_rooms"].value == "7"
    assert merged["appraised_value"].value == "356000"
    assert n == 0


def test_gla_equal_to_hoa_is_suppressed_but_distinct_gla_survives():
    # 1073 condo bug: HOA monthly assessment (635) misread as GLA.
    merged, _ = _run({"gla": "635", "hoa_monthly_assessment": "635"})
    assert merged["gla"].value is None
    merged2, _ = _run({"gla": "425", "hoa_monthly_assessment": "635"})
    assert merged2["gla"].value == "425"


def test_plausible_but_wrong_values_are_left_for_anchors_not_range():
    # total_rooms=3 / appraised_value=contract are plausible numbers a range
    # check cannot catch — they must NOT be suppressed here (handled by anchors).
    merged, _ = _run({"total_rooms": "3", "appraised_value": "320000"})
    assert merged["total_rooms"].value == "3"
    assert merged["appraised_value"].value == "320000"
