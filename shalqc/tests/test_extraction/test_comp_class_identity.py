"""A comparable's arithmetic identity depends on its CLASS, and a verifier gap
is not an extraction failure.

Run 18 marked comparable 6 UNREAD and stamped 0.55 confidence on all 48 of its
fields. Every figure in it had been read correctly:

    line adjustments sum to      -8,200   == the printed net
    349,900 - 8,200 = 341,700            == the printed adjusted price

What actually happened is that comp 6 is a PENDING listing. Its sale-price cell
prints an em-dash, so `sale + net == adjusted` could not run; its net cell was
never read, so `sum(lines) == net` could not run either. Both checks were
`skipped`, `skipped` collapsed into `verified: false`, and a region that was
entirely correct was reported as unusable — a false-VERIFY generator on every
check touching the listing comparable.

Two distinct defects, pinned separately here:

  * the identity was not comp-class aware (a pending listing is priced off its
    LIST price — the report says so itself on p32);
  * `skipped`, `not applicable` and `failed` were one bit when they are three.

The risk in fixing this is building a rubber stamp, so the tests that matter
most are the ones proving a genuinely broken pending column still FAILS.
"""
from __future__ import annotations

from app.extraction.verify import CERTIFIED, base_price, reconcile_comp, verify_comp_column

# Comparable 6 of the sample report, exactly as run 18 read it.
_PENDING_COMP = {
    "listing_status": "Pending",
    "list_price": "$349,900",
    "sale_price": "—",          # em-dash: a pending listing has no sale price
    "adjusted_price": "$341,700",
    # net_adjustment_total absent — the summary cell was never read
    "bathrooms": {"value": "2", "adjustment": "$9,000"},
    "bedrooms": {"value": "3", "adjustment": "$0"},
    "contract_date": {"value": "07/2026", "adjustment": "$(15,400)"},
    "gla": {"value": "1,668", "adjustment": "$19,700"},
    "outbuilding": {"value": "None", "adjustment": "$(2,500)"},
    "porch_patio_deck": {"value": "Patio", "adjustment": "$5,000"},
    "site_size": {"value": "2.10 Ac", "adjustment": "$(20,500)"},
    "vehicle_storage": {"value": "Garage | 1", "adjustment": "$(3,500)"},
    "view": {"value": "Residential", "adjustment": "$0"},
    "year_built": {"value": "1994", "adjustment": "$0"},
}

_CLOSED_COMP = {
    "listing_status": "Settled Sale",
    "sale_price": "$320,000",
    "list_price": "$330,000",
    "adjusted_price": "$318,300",
    "net_adjustment_total": "$(1,700)",
    "contract_date": {"value": "08/2025", "adjustment": "$3,500"},
    "site_size": {"value": "2.75 Ac", "adjustment": "$(23,800)"},
    "bathrooms": {"value": "2", "adjustment": "$9,000"},
    "gla": {"value": "1,860", "adjustment": "$11,600"},
    "porch_patio_deck": {"value": "Deck", "adjustment": "$5,000"},
    "vehicle_storage": {"value": "Garage | 2", "adjustment": "$(12,000)"},
    "outbuilding": {"value": "Shed", "adjustment": "$5,000"},
}


def test_pending_listing_is_priced_off_list_price():
    assert base_price(_PENDING_COMP) == (349_900.0, "list_price")


def test_closed_sale_is_priced_off_sale_price():
    """Both prices are present on a closed comp; the sale price must win."""
    assert base_price(_CLOSED_COMP) == (320_000.0, "sale_price")


def test_the_correct_pending_comparable_now_verifies():
    """The regression. This column was read perfectly and reported as unusable."""
    res = verify_comp_column(_PENDING_COMP, 6)
    assert res.verified, f"errors={res.errors} skipped={res.skipped}"
    assert res.checks_run >= 1
    assert not res.errors


def test_a_broken_pending_comparable_still_fails():
    """The check that keeps the fix honest.

    Deriving the net from the adjusted price could easily make every column pass
    by construction. It does not: the derived net is compared against the LINE
    ITEMS, which are an independent reading of the page.
    """
    broken = dict(_PENDING_COMP)
    broken["gla"] = {"value": "1,668", "adjustment": "$29,700"}   # +10,000
    res = verify_comp_column(broken, 6)
    assert not res.verified
    assert res.errors


def test_a_transposed_pending_column_is_caught_by_magnitude_not_by_sum():
    """Sum is invariant to permutation, so a pure row swap is NOT caught here —
    that is the row-label template's job. What IS caught is a swap that changes
    the total, which is the common case when a value lands in the wrong row and
    displaces a different one."""
    swapped = dict(_PENDING_COMP)
    swapped["site_size"] = {"value": "2.10 Ac", "adjustment": "$(3,500)"}
    swapped["vehicle_storage"] = {"value": "Garage | 1", "adjustment": "$(20,500)"}
    # A clean swap preserves the sum, so this must still pass arithmetic.
    assert verify_comp_column(swapped, 6).verified

    displaced = dict(_PENDING_COMP)
    displaced["site_size"] = {"value": "2.10 Ac", "adjustment": "$(3,500)"}
    assert not verify_comp_column(displaced, 6).verified


def test_closed_comparable_runs_both_identities():
    res = verify_comp_column(_CLOSED_COMP, 1)
    assert res.verified
    assert res.checks_run == 2
    assert not res.skipped and not res.not_applicable


def test_a_missing_input_is_skipped_not_a_verifier_gap():
    """Absent data and an absent RULE are different states."""
    empty = {"listing_status": "Settled Sale"}
    res = verify_comp_column(empty, 3)
    assert not res.verified
    assert res.skipped
    assert not res.verifier_gap        # nothing was inapplicable — data was absent


def test_derived_net_does_not_re_check_the_identity_it_came_from():
    """`adjusted == base + net` is circular once the net was derived from it.
    Recording it as `skipped` understates what was proven; it is not applicable."""
    res = verify_comp_column(_PENDING_COMP, 6)
    assert any("derived" in n for n in res.not_applicable)
    assert "adjusted_vs_base_plus_net" not in res.skipped


def test_reconciliation_certifies_the_pending_comparable():
    """The path that actually emitted `UNREAD` in run 18.

    `reconcile_comp` derived its net as `adjusted - sale_price`, which is None
    for a listing, so it had no net to reconcile the line items against and
    reported the region unread with an empty `proven` list.
    """
    comp = dict(_PENDING_COMP, _pages=[23, 24])
    rec = reconcile_comp(comp, 6, pages_expected=[23, 24])

    assert rec.status == CERTIFIED, f"{rec.status}: {rec.errors}"
    assert rec.net == -8_200.0
    assert rec.net_derived == -8_200.0        # 341,700 - 349,900
    assert rec.line_sum_read == -8_200.0
    assert not rec.errors


def test_reconciliation_still_reports_a_real_conflict_on_a_listing():
    comp = dict(_PENDING_COMP, _pages=[23, 24])
    comp["gla"] = {"value": "1,668", "adjustment": "$29,700"}
    rec = reconcile_comp(comp, 6, pages_expected=[23, 24])
    assert rec.status != CERTIFIED
    assert rec.errors


def test_unknown_status_falls_back_without_silently_preferring_list_price():
    """With no status and both prices present, the sale price is the safer
    assumption — a listing without a status is far rarer than a closed sale."""
    both = {"sale_price": "$300,000", "list_price": "$310,000"}
    assert base_price(both) == (300_000.0, "sale_price")

    listing_only = {"list_price": "$310,000"}
    assert base_price(listing_only) == (310_000.0, "list_price")
