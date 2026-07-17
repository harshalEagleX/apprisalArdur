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


# ── P2 / F7: form-caption "(s)" artifact is suppressed, never bound as a value ──

def test_caption_artifact_detected():
    from app.extraction.plausibility import _caption_artifact, _string_plausible
    assert _caption_artifact("Report data source(s) used, offering price(s), and date(s)")
    assert _caption_artifact("offering price(s)")
    assert not _caption_artifact("Corelogic, GeoData")          # no (s) artifact
    assert not _string_plausible("used, offering price(s),")    # caption fragment → implausible
    assert _string_plausible("Corelogic, GeoData")             # a real data-source value survives


def test_gate_suppresses_caption_bound_as_value():
    # F7: a reader that grabbed the URAR caption into data_source is suppressed →
    # the field reads MISSING (found=False), never a garbage-value REVIEW.
    merged = {
        "data_source": ExtractedField(
            canonical_name="data_source", value="used, offering price(s), and date(s)",
            raw_value="used, offering price(s), and date(s)",
            source=Source.PDF_DIGITAL, confidence=0.6, page=2),
    }
    _generic_schema_gate(merged)
    ef = merged["data_source"]
    assert ef.found is False
    assert ef.suppressed is True


# ── P2 / F2: a legal-desc/page fragment bled into a person-name field is suppressed ──

def test_name_shape_helpers():
    from app.extraction.plausibility import _looks_like_person_name_field, _name_shaped
    assert _looks_like_person_name_field("co_borrower_name")
    assert _looks_like_person_name_field("borrower_name")
    assert not _looks_like_person_name_field("lender_name")     # company, not a person
    assert not _name_shaped("2 PGS 102-104")                    # legal-desc fragment
    assert _name_shaped("Laura Brantley and Eric Brantley")     # real names survive
    assert _name_shaped("O'Brien-Smith III")


def test_gate_suppresses_legal_desc_fragment_in_name_field():
    merged = {
        "co_borrower_name": ExtractedField(
            canonical_name="co_borrower_name", value="2 PGS 102-104",
            raw_value="2 PGS 102-104", source=Source.PDF_DIGITAL, confidence=0.6, page=1),
        "borrower_name": ExtractedField(
            canonical_name="borrower_name", value="Laura Brantley and Eric Brantley",
            raw_value="Laura Brantley and Eric Brantley", source=Source.XML, confidence=0.97, page=1),
    }
    _generic_schema_gate(merged)
    assert merged["co_borrower_name"].found is False           # garbage suppressed → MISSING
    assert merged["borrower_name"].found is True               # real name untouched


# ── P2 / F8: grid cell-bleed (a row concatenated across columns) is suppressed ──

def test_repeated_grid_cell_detector():
    from app.extraction.plausibility import _repeated_grid_cell
    # exact-repeat bleed (445 Sparrow) and NEAR-duplicate bleed (H8354/ESMI) — the
    # latter repeats on shared stems (Porch/Patio/Deck) once we split on / and ,
    assert _repeated_grid_cell("CvPor,CvPat CvPor,CvPat Prch/Patio/Deck 0 Prch/Patio/Deck 0")
    assert _repeated_grid_cell("Porch/Patio Porch/Deck 0 Porch/Pat/Deck 2,000 Porch/Patio")
    assert _repeated_grid_cell("2Balcony 2Balcony 2Balcony")     # one token x3 = bled (order 11)
    assert not _repeated_grid_cell("Concrete Slab Foundation")   # legit multi-word
    assert not _repeated_grid_cell("Prch/Patio/Deck")           # legit single cell
    assert not _repeated_grid_cell("Wood/Vinyl Siding")         # legit, slash-separated
    assert not _repeated_grid_cell("Central Air, Central Heat") # one repeated token only
    assert not _repeated_grid_cell("Residential Residential")    # single repeated token
    assert not _repeated_grid_cell("Wood Brick Stone Vinyl")     # all distinct


def test_gate_suppresses_grid_cell_bleed():
    merged = {
        "porch_patio_deck": ExtractedField(
            canonical_name="porch_patio_deck",
            value="CvPor,CvPat CvPor,CvPat Prch/Patio/Deck 0 Prch/Patio/Deck 0",
            raw_value="CvPor,CvPat CvPor,CvPat Prch/Patio/Deck 0 Prch/Patio/Deck 0",
            source=Source.PDF_DIGITAL, confidence=0.6, page=3),
    }
    _generic_schema_gate(merged)
    assert merged["porch_patio_deck"].found is False           # row-bleed → MISSING, not garbage


# ── F7 residual (445 Sparrow): data-source names bled into mls_number ──────────

def test_mls_number_rejects_provider_name_bleed():
    from app.extraction.plausibility import _valid_mls_number
    # verified across 10 RANDOM orders: an MLS number has a digit; the bleed never does
    assert _valid_mls_number("A12345", {}) is True                 # has a digit → id
    assert _valid_mls_number("#VALO2126558/LO", {}) is True
    assert _valid_mls_number("57050211542", {}) is True
    for bleed in ["Corelogic, GeoData,", "results of", "General Row", "increased", "correct"]:
        assert _valid_mls_number(bleed, {}) is False               # no digit → not an id


def test_gate_suppresses_mls_provider_bleed():
    from app.extraction.plausibility import validate_fields
    merged = {
        "mls_number": ExtractedField(
            canonical_name="mls_number", value="Corelogic, GeoData,",
            raw_value="Corelogic, GeoData,", source=Source.PDF_DIGITAL, confidence=0.6, page=2),
    }
    validate_fields(merged)
    assert merged["mls_number"].found is False
