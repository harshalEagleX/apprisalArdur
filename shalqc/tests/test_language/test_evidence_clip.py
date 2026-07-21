"""
Evidence chips are glance targets, not reading panes. `_clip_display` strips
leading extraction noise and clips runaway narrative values — WITHOUT ever
altering a structured value (a negative like "-6.7" keeps its sign, a bare
decimal like ".2 ac" keeps its value). Coordinates are carried by the packet
entry, so clipping is display-only and never moves a bbox.
"""

from __future__ import annotations

from app.language.validate_v2 import (
    _EVIDENCE_DISPLAY_MAX,
    _clip_display,
    _located_evidence,
)


def test_structured_values_untouched():
    for v in ["-6.7", "-17.4", ".2 ac", ".75 ac", "0.2", "C2", "1600000",
              "N;Mtn;Wtr", "2.10 ac"]:
        assert _clip_display(v) == v


def test_leading_noise_stripped():
    assert _clip_display(". Covered") == "Covered"
    assert _clip_display("- pending") == "pending"
    assert _clip_display("-::- -:SITE COMMENTS:- The lot is level") == "The lot is level"


def test_long_narrative_clipped_and_clean():
    narr = (".          The neighborhood values appear to have stabilized after "
            "several years of increases and a recent decline. Listing prices are "
            "typically one to two percent above recent comparable sales in the area.")
    out = _clip_display(narr)
    assert out.startswith("The neighborhood values")
    assert out.endswith("…")
    assert len(out) <= _EVIDENCE_DISPLAY_MAX + 1  # + the ellipsis
    assert out[0] not in ".,;:-—–"


def test_clip_is_display_only_coordinates_preserved():
    class _P:
        values = {
            "neighborhood_description": {
                "v": ". " + "word " * 100, "page": 12,
                "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.01},
                "lq": "exact", "source": "Source.XML", "confidence": 0.9,
            }
        }
    row = _located_evidence(_P(), {})[0]
    assert row["page"] == 12
    assert row["bbox"] == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.01}
    assert row["location_quality"] == "exact"
    assert row["value"].startswith("word")  # leading ". " gone
    assert len(row["value"]) <= _EVIDENCE_DISPLAY_MAX + 1
