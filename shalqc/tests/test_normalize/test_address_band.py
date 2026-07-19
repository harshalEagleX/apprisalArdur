"""Cross-document ADDRESS comparison banding.

2026-07-18: EQ-98 / EQ-111 / EQ-F (Company Address, Lender/Client Address) hedged
to REVIEW on nearly every order because the address band was exact token-set
equality — any extra token dropped it to "review". Measured on ESMD-0002883 the
two sides were:

    report:     "3814 BEL PRE ROAD, SILVER SPRING, MD 20906"
    engagement: "3814 BEL PRE ROAD Suite 10, SILVER SPRINGS, MD 20906"

The same building — differing only by a suite number stated on one document and a
city spelling variant the ZIP already disambiguates. Neither is an address
mismatch, and a reviewer opening that card learns nothing.

The widening is deliberately conservative: a match still requires the same ZIP5
and the same primary street number, which together with the street name form a
USPS delivery point, so it cannot merge two genuinely different addresses. An
address NEVER bands "mismatch" — a difference is a soft signal for a human, never
an auto-reject.
"""

import pytest

from app.normalize.normalizer import match_band


def band(a, b):
    return match_band(a, b, "address")


# ── differences that are not differences ─────────────────────────────────────

def test_secondary_unit_on_one_side_only():
    """The real ESMD-0002883 pair: suite number + city plural."""
    assert band("3814 BEL PRE ROAD, SILVER SPRING, MD 20906",
                "3814 BEL PRE ROAD Suite 10, SILVER SPRINGS, MD 20906") == "match"


def test_hash_unit_number_is_dropped():
    assert band("502 GIUSEPPE CT #12, ROSEVILLE, CA 95678",
                "502 Giuseppe Court, Roseville, CA 95678") == "match"


def test_street_suffix_abbreviation():
    assert band("3315 Gordonia Circle SE, Southport, NC 28461",
                "3315 Gordonia Cir SE, Southport, NC 28461") == "match"


def test_zip_plus_four_collapses():
    assert band("1416 N Potomac St, Hagerstown, MD 21742",
                "1416 N Potomac Street Hagerstown MD 21742-1234") == "match"


def test_city_plural_variant_when_zip_and_number_agree():
    assert band("100 Main St, Springfield, IL 62704",
                "100 Main St, Springfields, IL 62704") == "match"


# ── real differences must survive as REVIEW ──────────────────────────────────

def test_different_street_number_is_not_a_match():
    assert band("3814 BEL PRE ROAD, SILVER SPRING, MD 20906",
                "3815 BEL PRE ROAD, SILVER SPRING, MD 20906") == "review"


def test_different_zip_is_not_a_match():
    assert band("3814 BEL PRE ROAD, SILVER SPRING, MD 20906",
                "3814 BEL PRE ROAD, SILVER SPRING, MD 20907") == "review"


def test_different_street_name_is_not_a_match():
    assert band("3814 BEL PRE ROAD, SILVER SPRING, MD 20906",
                "3814 OAK PRE ROAD, SILVER SPRING, MD 20906") == "review"


def test_different_street_type_is_not_a_match():
    """St vs Ave is a genuinely different street, not a formatting variant."""
    assert band("100 Main St, Springfield, IL 62704",
                "100 Main Ave, Springfield, IL 62704") == "review"


def test_address_never_bands_mismatch():
    """An address difference is always a human decision, never an auto-reject."""
    for a, b in (("3814 Bel Pre Rd, Silver Spring, MD 20906",
                  "9 Nowhere Lane, Elsewhere, CA 90001"),
                 ("", "100 Main St")):
        assert band(a, b) in {"match", "review"}


# ── the unit-swallowing must not eat real words ─────────────────────────────

def test_designator_does_not_swallow_a_following_word():
    """'floor' / 'lot' are designators, but only a SHORT numeric-bearing token
    after one is the unit value — a following WORD must survive."""
    from app.normalize.normalizer import _address_core
    assert "plan" in _address_core("100 Main St Floor Plan Drive")
