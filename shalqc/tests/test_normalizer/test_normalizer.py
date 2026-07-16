"""
Normalizer tests (nrm-1.0.0) — SHALqc.md §4 / §12 DoD #1.

These are the acceptance checks for "false FAILs fixed here, once": the address
suffix / enum / unit / boolean / name / date classes SHALqc.md §4 names must
all normalize away, so no rule downstream can false-FAIL on them.
"""

from app.extraction.schema import schema_loader as S
from app.normalize import compare, normalize
from app.normalize.dates import parse_date, to_iso


def fd(name):
    return S.get_field(name)


def test_address_suffix_normalizes():
    assert compare(fd("property_address"), "7243 Foxtail Mdw Ct",
                   "7243 Foxtail Meadow Ct").verdict == "match"


def test_state_name_vs_code():
    assert compare(fd("state"), "Texas", "TX").verdict == "match"
    assert normalize("state_code", "california") == "CA"


def test_enum_synonym():
    assert compare("enum", "Owner", "OwnerOccupied").verdict == "match"
    assert normalize("enum", "Det.") == "Detached"


def test_boolean_categorical():
    # True == Public for utilities (SHALqc.md §4 boolean↔categorical)
    assert normalize("boolean", "True") == normalize("boolean", "Public") == "True"
    assert normalize("boolean", "No") == "False"


def test_units_stripped():
    assert normalize("currency", "4800 sf") == "4800"
    assert normalize("currency", "$250,000.00") == "250000"


def test_number_word():
    assert normalize("integer", "One") == "1"


def test_name_order_insensitive():
    assert compare(fd("borrower_name"), "RATHNASEKARA KARUNARATNE",
                   "Karunaratne, Rathnasekara").verdict == "match"


def test_name_containment_suffix_only_is_review_not_mismatch():
    # missing generational suffix alone → review, never mismatch (§4 names)
    mr = compare(fd("borrower_name"), "John Smith Jr", "John Smith", kind="name_containment")
    assert mr.verdict in ("match", "review")


def test_company_designator_ignored():
    assert compare(fd("lender_name"), "Extreme Loans", "Extreme Loans, LLC").verdict == "match"


def test_county_suffix_stripped():
    assert compare(fd("county"), "Harris County", "Harris").verdict == "match"


def test_dates_to_iso_and_pivot():
    assert to_iso("04/27/2026") == "2026-04-27"
    assert to_iso("4/5/26") == "2026-04-05"        # 2-digit year pivots to 20xx
    assert parse_date("not a date") is None


def test_low_similarity_never_auto_matches():
    mr = compare(fd("city"), "Humble", "Dallas")
    assert mr.verdict == "mismatch"


# ── P5 / F3: person-aware name comparison (multi-person, order- & credential-safe) ──

from app.normalize.normalizer import match_band, canonicalize


def test_multi_person_names_match_order_insensitively():
    assert match_band("David & Marissa Stiehl", "Marissa and David Stiehl", "person") == "match"
    assert match_band("David Stiehl and Marissa Stiehl", "David & Marissa Stiehl", "person") == "match"


def test_trailing_credential_is_dropped_dynamically_not_a_mismatch():
    # no credential list is hardcoded — MNAA is recognized by ALL-CAPS acronym shape
    assert match_band("Wilmer Eichler, MNAA", "Wilmer Eichler", "person") == "match"
    assert match_band("Wilmer Eichler Jr, SRA", "Wilmer Eichler", "person") in ("match", "review")


def test_wrong_person_is_a_real_mismatch():
    # the F3 false-FAIL cause was a WRONG anchor; a genuinely different person must
    # still mismatch (the comparator must not collapse everyone to "match").
    assert match_band("David Marissa Stiehl", "Carolyn Paine", "person") == "mismatch"


def test_missing_one_borrower_is_not_a_silent_match():
    # two borrowers on one side, one on the other → not a clean match
    assert match_band("David and Marissa Stiehl", "David Stiehl", "person") in ("review", "match")
    assert match_band("David Stiehl", "David and Marissa Stiehl", "person") == "match"  # subset side is required


def test_canonicalize_person_collapses_shared_surname_and_order():
    a = canonicalize("David & Marissa Stiehl", "person")
    b = canonicalize("Marissa Stiehl and David Stiehl", "person")
    assert a == b                                   # byte-identical on a real match
    assert a == "david marissa stiehl"              # flat, sorted, deduped — no doubled surname
