"""The sales-grid crop must MEASURE its column boundaries, not assume them.

The assumed geometry (`label_and_column_clips`) treats the grid as spanning the
full page width with a 28% label column. On the UAD 3.6 report that is wrong in
both directions at once: the grid occupies x in [0.153, 0.847] in five equal
columns, so comparable 1's crop landed at [0.446, 0.654] where the column really
sits at [0.431, 0.569] — clipping its own cell on the left and swallowing 62% of
the next comparable on the right.

That one error produced both halves of what was recorded as an unavoidable
padding trade-off: a truncated address (values are right-aligned, so overflow
runs off the LEFT edge) and a bled neighbouring column. These tests pin the
measurement so the assumption cannot creep back.

The fixture is a synthetic PDF drawn to the same geometry rather than the real
report, which is 15 MB and untracked.
"""
from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from app.extraction.vision.render import (  # noqa: E402
    detect_grid_columns, grid_column_clips, label_and_column_clips)

# Fractional x boundaries measured off page 21 of the sample report: label,
# subject, then three comparables, all 0.1385 wide.
_TRUE_BOUNDS = [0.153, 0.2915, 0.430, 0.5685, 0.707, 0.8455]
_ROWS = 30


@pytest.fixture()
def grid_pdf(tmp_path):
    """A page carrying a five-column table drawn as row rules, like the report."""
    path = tmp_path / "grid.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    width, top, bottom = 612.0, 100.0, 700.0
    for i in range(_ROWS):
        y = top + i * (bottom - top) / _ROWS
        # One rule per cell, so each boundary is restated on every row — the
        # repetition is what the detector keys on.
        for a, b in zip(_TRUE_BOUNDS, _TRUE_BOUNDS[1:]):
            page.draw_line(fitz.Point(a * width, y), fitz.Point(b * width, y))
    doc.save(path)
    doc.close()
    return path


def test_detects_every_column_boundary(grid_pdf):
    bounds = detect_grid_columns(grid_pdf, 1)
    assert bounds is not None, "a five-column table must be detected"
    # All six boundaries, including the last — an extrapolated step accumulates
    # rounding drift and used to drop the final comparable off the end.
    assert len(bounds) == len(_TRUE_BOUNDS)
    for got, want in zip(bounds, _TRUE_BOUNDS):
        assert abs(got - want) < 0.01, f"boundary {got} != {want}"


def test_measured_crop_contains_one_comparable_and_all_of_it(grid_pdf):
    for comp in (1, 2, 3):
        _labels, column = grid_column_clips(grid_pdf, 1, comp, 4)
        left, right = column["x"], column["x"] + column["w"]
        want_l, want_r = _TRUE_BOUNDS[comp + 1], _TRUE_BOUNDS[comp + 2]
        col_w = want_r - want_l
        # Covers the whole column: nothing of its own cell is clipped away.
        assert left <= want_l + 0.005, f"comp {comp} clips its own left edge"
        assert right >= want_r - 0.005, f"comp {comp} clips its own right edge"
        # And barely overruns it: a sliver of the neighbour is tolerable, most of
        # one is the 22%-padding failure that returned 14 line adjustments for 7.
        assert left > want_l - col_w * 0.25, f"comp {comp} bleeds into the previous column"
        assert right < want_r + col_w * 0.25, f"comp {comp} bleeds into the next column"


def test_measured_beats_assumed_on_the_real_geometry(grid_pdf):
    """The assumption is wrong in BOTH directions — that is the whole point."""
    _l, assumed = label_and_column_clips(1, 4)
    _l2, measured = grid_column_clips(grid_pdf, 1, 1, 4)
    comp1_l, comp1_r = _TRUE_BOUNDS[2], _TRUE_BOUNDS[3]
    comp2_r = _TRUE_BOUNDS[4]

    # Assumed: starts inside comp 1 (clipping it) and ends inside comp 2 (bleeding).
    assert assumed["x"] > comp1_l, "the assumed crop is expected to clip comp 1"
    assert comp1_r < assumed["x"] + assumed["w"] < comp2_r, \
        "the assumed crop is expected to reach into comp 2"

    # Measured: covers comp 1 exactly and stops before comp 2's far edge.
    assert measured["x"] <= comp1_l
    assert measured["x"] + measured["w"] < comp1_r + (comp1_r - comp1_l) * 0.25


def test_falls_back_when_the_page_has_no_grid(tmp_path):
    path = tmp_path / "prose.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792).insert_text((72, 72), "no table here")
    doc.save(path)
    doc.close()

    assert detect_grid_columns(path, 1) is None
    # The caller still gets usable clips rather than an exception.
    labels, column = grid_column_clips(path, 1, 1, 4)
    assert (labels, column) == label_and_column_clips(1, 4)
