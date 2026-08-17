"""A checklist may not reference a field nobody extracts.

`_labels_from_sources` used to drop an unknown binding name SILENTLY. The
consequence is subtle and expensive: an item listing four fields where two are
unknown compiles cleanly, reports as bound, and decides on half its evidence —
which is exactly the failure mode for items that need several values at once.
The septic finding needs `site.apparent_defects` AND `utilities_operating` AND
`contract.analysis_comment` AND `reconciliation.value_condition`; any one of
them alone reads "fine".

It also wasted real work. Six 3.6 items were bound by hand against
`comp_proximity`, `comp_location`, `comp_property_rights` and `location_type`.
Every one was discarded without a word, the YAML said `binding: bound`, and the
compiler reported them unbound — two readings of the same file disagreeing with
nothing in between to explain it.

**The naming contract** (measured, not assumed):

    comp_1_gla  comp_N_gla  comp_1_sale_price   known
    comp_gla    comp_proximity  comp_location   NOT known

Comparable fields are `comp_N_<field>` or `comp_1_..comp_6_<field>`. The short
`comp_<field>` form does not resolve.
"""
from __future__ import annotations

import pytest

from app.language import compiler as C


@pytest.fixture(autouse=True)
def _clear():
    C._UNKNOWN_BINDINGS.clear()
    yield
    C._UNKNOWN_BINDINGS.clear()


def _labels(*fields):
    return C._labels_from_sources([{"doc": "appraisal", "fields": list(fields)}])[0]


def test_an_unknown_binding_is_recorded_not_swallowed():
    """The regression. Silence here is what let bad bindings ship."""
    assert _labels("definitely_not_a_field") == []
    assert "definitely_not_a_field" in C._UNKNOWN_BINDINGS


def test_a_partial_binding_reports_the_half_it_dropped():
    """The dangerous case: enough resolves that the item looks bound, so the
    loss is invisible without the report."""
    got = _labels("gla", "comp_property_rights")
    assert got == ["gla"]
    assert "comp_property_rights" in C._UNKNOWN_BINDINGS


def test_the_comparable_naming_contract():
    """comp_N_<field>, never comp_<field>.

    A per-comparable name CANONICALISES to the N form — comp_1_gla and comp_N_gla
    are the same label — so a rule written against one comparable applies to all
    six without being restated.
    """
    assert _labels("comp_1_gla") == ["comp_N_gla"]
    assert _labels("comp_N_gla") == ["comp_N_gla"]
    assert _labels("comp_gla") == []
    assert "comp_gla" in C._UNKNOWN_BINDINGS


def test_known_fields_pass_through_clean():
    for f, expected in (("gla", "gla"), ("sale_type", "sale_type"),
                        ("street_ownership", "street_ownership"),
                        ("property_rights", "property_rights"),
                        ("comp_1_sale_price", "comp_N_sale_price")):
        C._UNKNOWN_BINDINGS.clear()
        assert _labels(f) == [expected], f
        assert not C._UNKNOWN_BINDINGS, f


def test_the_shipped_36_checklist_has_no_unknown_bindings():
    """The gate that matters: every name the live 3.6 checklist references must
    resolve to a field the extractor actually produces.

    Items legitimately bound to NOTHING are a different problem (they can only
    ever be REVIEW) and are not this test's business. This one only asserts that
    nothing is being dropped on the floor.
    """
    rows = C.load_checklist(C.checklist_for("EQUITYSOLUTIONS", "3.6"))
    assert rows, "3.6 checklist did not load"
    for row in rows:
        C._labels_from_sources(row.get("sources") or [])
    assert not C._UNKNOWN_BINDINGS, (
        "3.6 checklist references fields that are not known labels: "
        f"{sorted(C._UNKNOWN_BINDINGS)} — use comp_N_<field> for comparables, "
        "or add the label to the field schema")


def test_engagement_and_contract_sources_still_flag_other_docs():
    """Unrelated behaviour that shares this function — kept honest."""
    _, needs_other = C._labels_from_sources(
        [{"doc": "engagement", "fields": ["borrower_name"]}])
    assert needs_other is True
