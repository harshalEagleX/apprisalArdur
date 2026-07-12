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
