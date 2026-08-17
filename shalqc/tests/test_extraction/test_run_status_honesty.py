"""A run may only report COMPLETE when nothing was lost.

This status is the one signal telling a caller whether verdicts from the run are
publishable, so every way of losing evidence has to reach it. Three different
guards can stop a section short, and each one was found reporting green:

  * run 18  — two sections returned NOTHING, and the run printed DONE at
              "coverage 125.7%" (fields emitted over schema size).
  * run 20  — `market` and `contract_history` hit the wall-clock deadline and
              abandoned 21 fields between them; status COMPLETE.
  * run 21  — `contract_history` exhausted the split-depth bound, returned 6
              fields and abandoned 16; timed_out was False; status COMPLETE.

The consequence is identical in all three: fields nobody saw. So the status keys
on the LOSS, not on which limit produced it.
"""
from __future__ import annotations

import pytest

from app.extraction.vision.runner import _finalise_status


def _run(resilience: dict) -> dict:
    report: dict = {"degradations": []}
    _finalise_status(report, {"resilience": resilience,
                              "sections_attempted": list(resilience)})
    return report


def test_a_clean_run_is_complete():
    r = _run({"site": {"fields": 18, "missing": [], "timed_out": False},
              "sketch": {"fields": 4, "missing": [], "timed_out": False}})
    assert r["status"] == "COMPLETE"
    assert not r["degradations"]


def test_an_empty_section_is_incomplete():
    """Run 18: a section that returned nothing is not a section with no findings."""
    r = _run({"site": {"fields": 18, "missing": [], "timed_out": False},
              "outbuilding_storage": {"fields": 0, "missing": [], "timed_out": False}})
    assert r["status"] == "INCOMPLETE"
    assert r["empty_sections"] == ["outbuilding_storage"]
    assert "outbuilding_storage" in r["incomplete_reason"]


def test_a_deadline_hit_is_incomplete():
    """Run 20: bounding a slow section is correct, but it drops evidence."""
    r = _run({"site": {"fields": 18, "missing": [], "timed_out": False},
              "market": {"fields": 9, "missing": ["a"] * 10, "timed_out": True}})
    assert r["status"] == "INCOMPLETE"
    assert r["timed_out_sections"] == ["market"]
    assert "deadline" in r["incomplete_reason"]


def test_depth_exhaustion_is_incomplete_even_without_a_timeout():
    """Run 21: the gap this test exists for. `timed_out` was False and 16 fields
    were still gone, because the split-depth bound stopped the read instead."""
    r = _run({"site": {"fields": 18, "missing": [], "timed_out": False},
              "contract_history": {"fields": 6, "missing": ["f"] * 16,
                                   "timed_out": False}})
    assert r["status"] == "INCOMPLETE"
    assert r["lossy_sections"] == {"contract_history": 16}
    assert "contract_history (16)" in r["incomplete_reason"]


def test_a_section_is_not_double_counted():
    """A section that timed out AND has missing fields is one loss, not two."""
    r = _run({"market": {"fields": 9, "missing": ["a"] * 10, "timed_out": True}})
    assert r["timed_out_sections"] == ["market"]
    assert "market" not in r["lossy_sections"]


@pytest.mark.parametrize("resilience", [
    {"a": {"fields": 0, "missing": [], "timed_out": False}},
    {"a": {"fields": 3, "missing": ["x"], "timed_out": False}},
    {"a": {"fields": 3, "missing": [], "timed_out": True}},
])
def test_every_loss_path_reaches_the_status(resilience):
    """Whichever guard fires, the caller must be told not to publish."""
    r = _run(resilience)
    assert r["status"] == "INCOMPLETE"
    assert r["degradations"], "an incomplete run must say so in degradations"
