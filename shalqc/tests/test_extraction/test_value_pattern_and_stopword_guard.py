"""Source-agnostic plausibility guards in the generic schema gate.

A layout/label-proximity reader can lift a word sitting next to a field's printed
label and hand it back as the value. Two shapes that are never a real answer:
  * reasonable_exposure_time = "reasonablly"  — fails the field's declared
    value_pattern (a duration needs a number + a time unit). EQ-122 read it as an
    invalid exposure time.
  * prior_sale_analysis_comment = "or"         — a lone stopword lifted from prose.
    EQ-80/EQ-86 read it as the appraiser's analysis.
Both must be suppressed (the raw value survives in raw_value, never trusted).
"""
from app.extraction.plausibility import _generic_schema_gate
from app.extraction.result import ExtractedField, Source


def _ef(name: str, value: str) -> ExtractedField:
    return ExtractedField(canonical_name=name, value=value, source=Source.PDF_DIGITAL,
                          confidence=0.7, page=1, location_quality="page")


def test_value_pattern_rejects_non_duration_exposure_time():
    merged = {"reasonable_exposure_time": _ef("reasonable_exposure_time", "reasonablly")}
    assert _generic_schema_gate(merged) == 1
    assert not merged["reasonable_exposure_time"].found


def test_value_pattern_keeps_a_real_duration():
    for good in ["3-5 months", "0-90 days", "90 days", "6-12 weeks"]:
        merged = {"reasonable_exposure_time": _ef("reasonable_exposure_time", good)}
        assert _generic_schema_gate(merged) == 0, good
        assert merged["reasonable_exposure_time"].found


def test_lone_stopword_rejected_even_for_a_narrative_field():
    merged = {"prior_sale_analysis_comment": _ef("prior_sale_analysis_comment", "or")}
    assert _generic_schema_gate(merged) == 1
    assert not merged["prior_sale_analysis_comment"].found


def test_real_analysis_comment_survives():
    merged = {"prior_sale_analysis_comment": _ef(
        "prior_sale_analysis_comment",
        "No prior sales of the subject in the past 36 months per public record.")}
    assert _generic_schema_gate(merged) == 0
    assert merged["prior_sale_analysis_comment"].found
