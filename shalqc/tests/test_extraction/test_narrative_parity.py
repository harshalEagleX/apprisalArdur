"""Plausibility must not destroy values it read correctly.

2026-07-18 binding audit. Chasing why EQ-23 "Boundaries" hedged on 5 of 7 orders
and EQ-13 "Subject Listed/Sold within 12 Months" on 7 of 7, the answer was not the
checklist or the judge — extraction had already read both values and then thrown
them away:

    neighborhood_boundaries  XML, conf 0.97, "Neighborhood boundaries are to the
                             north by Dry Creek Rd, to the east by the North Fork
                             American River, to the south and to the west by
                             Hwy-49."      → suppressed as "grid cell bleed"
    days_on_market           "7;Per Metrolist"  → suppressed as "not numeric"

Both are the shape guards mistaking correct data for corruption. The guards
themselves are right — they still suppress has_full_basement="&" and
basement_outside_entry="Sump Pump Window" — they were just applied too widely.
"""

import pytest


# ── the two narrative-token lists must agree ────────────────────────────────

def test_narrative_token_parity_between_schema_and_language_layers():
    """`FieldDefinition._is_narrative` (extraction) and `_NARRATIVE_NAME`
    (app/language/narrative.py) describe the SAME concept at two layers. They
    drifted — "boundaries" was in the language list but not the schema one — and a
    correctly-extracted XML value was suppressed as a result. Keep them aligned."""
    from app.extraction.schema import NARRATIVE_NAME_TOKENS
    from app.language.narrative import _NARRATIVE_NAME

    for token in NARRATIVE_NAME_TOKENS:
        assert _NARRATIVE_NAME.search(token), (
            f"{token!r} marks a narrative field in extraction but the language "
            f"layer does not recognise it")


def test_boundaries_is_treated_as_narrative():
    from app.extraction.schema import schema_loader
    fd = schema_loader.get_field("neighborhood_boundaries")
    assert fd is not None
    assert fd._is_narrative, "a boundaries field is free prose, not a short string"


# ── UAD "<value>;<source>" cells ────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("7;Per Metrolist", "7"),
    ("120;MLS", "120"),
    ("1,250;Public Records", "1,250"),
    ("$185,000;Tax Records", "$185,000"),
])
def test_uad_numeric_prefix_is_parsed(raw, expected):
    from app.extraction.plausibility import _uad_numeric_prefix
    assert _uad_numeric_prefix(raw) == expected


@pytest.mark.parametrize("raw", [
    "Fee Simple;Leasehold",       # an enum cell — must NOT reduce to a digit
    "ArmLth;Conv",
    "Per Metrolist",
    "",
    ";7",
])
def test_non_numeric_cells_are_left_alone(raw):
    from app.extraction.plausibility import _uad_numeric_prefix
    assert _uad_numeric_prefix(raw) is None


# ── the guards must still catch real corruption ─────────────────────────────

def test_boolean_junk_is_still_suppressed():
    """The guards were applied too widely, not wrongly — these must keep failing."""
    from app.extraction.plausibility import _boolean_plausible
    assert not _boolean_plausible("&")
    assert not _boolean_plausible("Sump Pump Window")
    assert _boolean_plausible("Yes")


def test_a_real_boundaries_value_survives_the_full_plausibility_pass():
    """End-to-end on the actual ESCA-0019968 value: read from XML at 0.97 and
    previously suppressed as grid-bleed."""
    from app.extraction.plausibility import validate_fields
    from app.extraction.result import ExtractedField, Source

    ef = ExtractedField(
        canonical_name="neighborhood_boundaries",
        value=("Neighborhood boundaries are to the north by Dry Creek Rd, to the "
               "east by the North Fork American River, to the south and to the "
               "west by Hwy-49."),
        source=Source.XML, confidence=0.97)
    assert ef.found      # value present and not yet suppressed
    validate_fields({"neighborhood_boundaries": ef})
    assert not ef.suppressed, ef.suppression_reason


def test_unschematized_narrative_field_is_exempt_from_grid_bleed():
    """2026-07-18, found by sweeping suppressions across 8 orders:
    `conforms_to_neighborhood_comment` is NOT in field_schema.yaml, so it fell to
    the unschematized branch — which applied the grid-bleed guard with no narrative
    exemption at all. It was suppressed on 4 of 8 orders, every one read from the
    AUTHORITATIVE XML at 0.97 and every one real prose. Same defect as
    neighborhood_boundaries, one code branch over.

    The exemption follows the field's NATURE, not whether it happens to be
    registered in the schema."""
    from app.extraction.plausibility import validate_fields
    from app.extraction.result import ExtractedField, Source

    ef = ExtractedField(
        canonical_name="conforms_to_neighborhood_comment",
        value=("The subject property conforms well with the market area. No adverse "
               "conditions were noted. Subject value is slightly below the "
               "predominant value in the area."),
        source=Source.XML, confidence=0.97)
    validate_fields({"conforms_to_neighborhood_comment": ef})
    assert not ef.suppressed, ef.suppression_reason


def test_unschematized_non_narrative_grid_bleed_is_still_suppressed():
    """The guard must keep catching real bleed — a rental row that swept up every
    comp's cell into one field."""
    from app.extraction.plausibility import validate_fields
    from app.extraction.result import ExtractedField, Source

    ef = ExtractedField(canonical_name="rental_amount",
                        value="$ $ 1,975 $ 2,500 $ 2,300",
                        source=Source.PDF_DIGITAL, confidence=0.9)
    validate_fields({"rental_amount": ef})
    assert ef.suppressed


# ── prose must not read as grid bleed ───────────────────────────────────────

def test_prose_repeating_function_words_is_not_grid_bleed():
    """Third instance of this defect (after neighborhood_boundaries and
    conforms_to_neighborhood_comment). ESWA-0002168's additional_features is 157
    chars — under the length ceiling — and "Has"x2 + "with"x2 satisfied the
    "2 distinct repeated tokens" rule, so EQ-49 told the reviewer "Additional
    Features field is blank" about a filled field.

    Grid bleed repeats the cell's own CONTENT; English repeats FUNCTION words."""
    from app.extraction.plausibility import _repeated_grid_cell
    assert not _repeated_grid_cell(
        "Home is mostly in original condtion with little evidence of remodeling or "
        "updating over it's lifespan. Has detached garage. Has finished attic with "
        "two bedrooms.")
    assert not _repeated_grid_cell(
        "The subject property conforms well with the market area. No adverse "
        "conditions were noted.")


def test_real_grid_bleed_is_still_detected():
    """The guard must keep its teeth — these are genuine multi-cell bleed."""
    from app.extraction.plausibility import _repeated_grid_cell
    assert _repeated_grid_cell("Porch/Patio Porch/Deck Porch/Pat/Deck")
    assert _repeated_grid_cell("Fee Simple Fee Simple")
    assert _repeated_grid_cell("2Balcony 2Balcony 2Balcony")


def test_legitimate_single_cell_untouched():
    from app.extraction.plausibility import _repeated_grid_cell
    assert not _repeated_grid_cell("Concrete Slab Foundation")


# ── a NAME must not be a slice of running prose ─────────────────────────────

def test_name_field_rejects_a_sentence_fragment():
    """2026-07-19: ESWA-0002168 read project_name="work," off the form — a word
    sliced out of running prose. It manufactured a phantom condo: EQ-119
    ("complete the shaded areas IF the subject is a Condo/Co-Op") saw a populated
    project_name on a DETACHED single-family (dwelling_type='Det.',
    is_pud_checked='No') and hedged."""
    from app.extraction.plausibility import _sentence_fragment
    assert _sentence_fragment("work,")
    assert _sentence_fragment("estate work;")


def test_real_names_with_internal_punctuation_survive():
    """Narrow by design — a comma INSIDE a name is normal."""
    from app.extraction.plausibility import _sentence_fragment
    for name in ("Sunset Villas", "MCA, Inc.", "Gary N. James Appraiser",
                 "Kastle River Appraisals", "N/A"):
        assert not _sentence_fragment(name), name


def test_project_name_fragment_is_suppressed_end_to_end():
    from app.extraction.plausibility import validate_fields
    from app.extraction.result import ExtractedField, Source

    junk = ExtractedField(canonical_name="project_name", value="work,",
                          source=Source.PDF_DIGITAL, confidence=0.9)
    real = ExtractedField(canonical_name="appraiser_company_name", value="MCA, Inc.",
                          source=Source.PDF_DIGITAL, confidence=0.9)
    validate_fields({"project_name": junk, "appraiser_company_name": real})
    assert junk.suppressed
    assert not real.suppressed
