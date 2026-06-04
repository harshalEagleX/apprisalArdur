"""Unit tests for checkbox label -> field mapping (multi-word + left-label)."""

from app.ocr.checkbox_extractor import map_label_to_field as m


def test_multiword_demand_supply():
    assert m("In Balance", "appraisal") == ("demand_supply", "In Balance")
    assert m("Over Supply", "appraisal") == ("demand_supply", "Over Supply")
    assert m("Shortage", "appraisal") == ("demand_supply", "Shortage")


def test_multiword_marketing_time():
    assert m("Under 3 mths", "appraisal") == ("marketing_time", "Under 3 mths")
    assert m("3-6 mths", "appraisal") == ("marketing_time", "3-6 mths")


def test_multiword_built_up():
    assert m("Over 75%", "appraisal") == ("built_up", "Over 75%")
    assert m("Under 25%", "appraisal") == ("built_up", "Under 25%")


def test_short_token_does_not_false_match():
    # Regression: "In" used to substring-match "de mINimis" -> property_rights.
    assert m("In", "appraisal") is None


def test_utility_left_label():
    # Utilities are left-labelled; a checked box on the row => present.
    assert m("", "appraisal", left_label="Electricity") == ("utilities_electricity", "True")
    assert m("", "appraisal", left_label="Gas") == ("utilities_gas", "True")
    assert m("", "appraisal", left_label="Sewer") == ("utilities_sewer", "True")


def test_existing_single_word_still_maps():
    assert m("Suburban", "appraisal") == ("location", "Suburban")
    assert m("Fee Simple", "appraisal") == ("property_rights", "Fee Simple")
