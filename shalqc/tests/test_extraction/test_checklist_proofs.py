"""Checklist items that arithmetic can SETTLE must never reach the judge.

Every catalog item whose `check_type` has no dedicated body falls through to
`_body_section_compare`, which returns VERIFY unconditionally and hands the
fields to the LLM. On the 3.6 catalog that is 84 of 90 items — so almost the
whole checklist was decided by a judge even where the answer is a comparison of
two numbers, and the same order is known to vary by ±5 REVIEW cards run to run.

`checklist_arithmetic.prove` existed and implemented three proofs; nothing ever
called it, and three of the four items that declare a proof could not run:

    #34  binds total_living_area + gla, but declared `proof: none`
    #87  declared `bracketing` and bound only `baths` — no comparable column
    #74  declared `bracketing` and bound only `contract_price` — same

`#87` is the one that matters most: the human review of this report recorded it
as a FAIL ("subject has 3 full baths, all six comparables have 2"), and the
proof that would have found it deterministically could not execute.

Values below are the real ones from run 21 of the sample report.
"""
from __future__ import annotations

import pytest

from app.extraction.vision.checklist_arithmetic import prove
from app.rules.catalog import catalog_path_for, load_catalog


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(catalog_path_for("3.6"))


@pytest.fixture()
def fields():
    """Subject + comparable values as run 21 actually read them."""
    f = {"total_living_area": "2,137", "gla": "2,137",
         "bedrooms": "4", "baths": "3", "contract_price": "$300,000"}
    for i, (bed, bath, price) in enumerate(
            [(3, 2, "$320,000"), (3, 2, "$274,500"), (3, 2, "$320,000"),
             (4, 2, "$285,000"), (3, 2, "$306,000"), (3, 2, "$349,900")], start=1):
        f[f"comp_{i}_bedrooms"] = str(bed)
        f[f"comp_{i}_bathrooms"] = str(bath)
        f[f"comp_{i}_sale_price"] = price
    return f


def _by_number(proved):
    return {a.checklist_number: a for a in proved}


def test_every_declared_proof_can_actually_run(catalog):
    """A proof declared but unable to bind is worse than no proof: it looks
    covered and silently abstains."""
    unrunnable = []
    for item in catalog:
        if (item.get("proof") or "none") == "none":
            continue
        names = (item.get("sources") or [{}])[0].get("fields") or []
        if item["proof"] == "bracketing":
            if not any(n.startswith("comp_") for n in names):
                unrunnable.append((item["checklist_number"], "no comparable column"))
            if not any(not n.startswith("comp_") for n in names):
                unrunnable.append((item["checklist_number"], "no subject field"))
        if item["proof"] == "consistency":
            if len([n for n in names if not n.startswith("comp_")]) < 2:
                unrunnable.append((item["checklist_number"], "fewer than two fields"))
    assert not unrunnable, f"declared proofs that cannot bind: {unrunnable}"


def test_square_footage_is_settled_without_a_judge(catalog, fields):
    """TRACKER 4k: this item IS the consistency check. It was `unbound`."""
    a = _by_number(prove(fields, None, catalog))[34]
    assert a.status == "PASS"
    assert a.computation == "|2,137 - 2,137| = 0"


def test_bathroom_bracketing_reproduces_the_human_FAIL(catalog, fields):
    """The finding the review raised by hand, now produced by code.

    Subject 3 full baths against six comparables at 2 — unbracketed in both
    directions, so there is no comparable at or above the subject anywhere in
    the grid.
    """
    a = _by_number(prove(fields, None, catalog))[87]
    assert a.status == "FAIL"
    assert a.computation == "2 <= 3 <= 2"


def test_bedroom_bracketing_passes(catalog, fields):
    """Comp 4 matches the subject at 4, so the count IS bracketed above."""
    a = _by_number(prove(fields, None, catalog))[86]
    assert a.status == "PASS"
    assert a.computation == "3 <= 4 <= 4"


def test_sale_price_bracketing_runs_once_bound(catalog, fields):
    """Subject contract price $300,000 against comps $274,500-$349,900."""
    a = _by_number(prove(fields, None, catalog))[74]
    assert a.status == "PASS", a.reason


def test_a_missing_input_abstains_rather_than_guessing(catalog, fields):
    """Run 21 lost `contract_price` with the rest of contract_history. An
    arithmetic proof with no number must VERIFY, never assume."""
    del fields["contract_price"]
    a = _by_number(prove(fields, None, catalog))[74]
    assert a.status == "VERIFY"
    assert "not read" in a.reason or a.missing


def test_proofs_are_driven_by_declaration_not_checklist_number(catalog, fields):
    """The whole point of the `proof` column: another AMC numbering its
    checklist differently must drive the same code with no edit here."""
    renumbered = []
    for item in catalog:
        copy = dict(item)
        if copy.get("checklist_number") == 87:
            copy["checklist_number"] = 9001
        renumbered.append(copy)
    a = _by_number(prove(fields, None, renumbered))[9001]
    assert a.status == "FAIL"
    assert a.computation == "2 <= 3 <= 2"
