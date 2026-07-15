"""Regression: the generic schema gate must CANONICALIZE a terse-but-valid enum
(MISMO's "Purchase") to the schema's verbose allowed value ("Purchase
Transaction") and keep it — not suppress it as implausible. Before 2026-07-13
the verbatim compare dropped the appraiser's real 0.97-confidence XML answer,
and every conditional check keyed on it hedged to REVIEW."""

from app.extraction.plausibility import _canonicalize_enum, _generic_schema_gate
from app.extraction.result import ExtractedField, Source


class _FD:
    def __init__(self, allowed):
        self.allowed_values = allowed


def test_terse_mismo_token_canonicalizes():
    fd = _FD(["Purchase Transaction", "Refinance Transaction", "Other"])
    assert _canonicalize_enum(fd, "Purchase") == "Purchase Transaction"
    assert _canonicalize_enum(fd, "Refinance") == "Refinance Transaction"


def test_camelcase_mismo_token_canonicalizes():
    # MISMO also emits camelCase enums with no space
    assert _canonicalize_enum(_FD(["Fee Simple", "Leasehold"]), "FeeSimple") == "Fee Simple"
    # …and a longer camelCase form maps to the shorter allowed value it contains
    assert _canonicalize_enum(_FD(["Owner", "Tenant", "Vacant"]), "OwnerOccupied") == "Owner"


def test_mismo_controlled_vocab_synonyms():
    # MISMO enumerations whose display form the schema states differently
    assert _canonicalize_enum(_FD(["Over 75%", "25-75%", "Under 25%"]), "Over75Percent") == "Over 75%"
    assert _canonicalize_enum(_FD(["Under 3 mths", "3-6 mths", "Over 6 mths"]), "UnderThreeMonths") == "Under 3 mths"
    assert _canonicalize_enum(_FD(["Det.", "Att.", "S-Det./End Unit"]), "Detached") == "Det."
    assert _canonicalize_enum(_FD(["One", "One with Accessory Unit"]), "1") == "One"
    # GSESaleType (note the hyphenated schema value)
    assert _canonicalize_enum(_FD(["Arms-Length", "Non Arms-Length", "REO"]), "ArmsLengthSale") == "Arms-Length"
    assert _canonicalize_enum(_FD(["Arms-Length", "Non Arms-Length"]), "NonArmsLengthSale") == "Non Arms-Length"


def test_synonym_never_fires_for_field_that_disallows_it():
    # a synonym target is returned ONLY if the field actually allows it
    assert _canonicalize_enum(_FD(["Det.", "Att."]), "Over75Percent") is None


def test_exact_value_passes_through():
    fd = _FD(["Purchase Transaction", "Refinance Transaction"])
    assert _canonicalize_enum(fd, "Purchase Transaction") == "Purchase Transaction"


def test_concatenated_checkbox_join_still_rejected():
    fd = _FD(["FWA", "HWBB", "Radiant"])
    assert _canonicalize_enum(fd, "FWA HWBB Radiant") is None  # a join of 3 → ambiguous/none


def test_ambiguous_and_garbage_reject():
    fd = _FD(["Purchase Transaction", "Refinance Transaction", "Other"])
    assert _canonicalize_enum(fd, "Transaction") is None       # subset of two → ambiguous
    assert _canonicalize_enum(fd, "zzz") is None


def test_gate_rewrites_value_in_place():
    # a full field named assignment_type flowing through the real gate is rewritten
    merged = {
        "assignment_type": ExtractedField(
            canonical_name="assignment_type", value="Purchase", raw_value="Purchase",
            source=Source.XML, confidence=0.97, page=1),
    }
    _generic_schema_gate(merged)
    ef = merged["assignment_type"]
    assert ef.found is True
    assert ef.value == "Purchase Transaction"
