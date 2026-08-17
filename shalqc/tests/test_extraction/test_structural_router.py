"""The section router must find EVERY band, and prove it when it cannot.

Section tabs are drawn by the form engine, so their geometry is invariant and a
section map can be recovered from pixels with no model call. The failure mode
that matters is not a crash — it is finding FEWER bands than exist, silently.

An earlier detector filtered bands with `6 <= height_px <= 40` at 100 DPI and
merged runs across a 4px gap. Both constants were wrong by one pixel:

  * every band is a PAIR of runs (main band plus a 4-5px companion below), and a
    4px merge gap leaves the pair split so both halves fall under the floor;
  * a row-group that renders 5px on one page and 6px on the next is dropped from
    the first and kept on the second.

On the real report that lost one section tab and five grid row-groups, including
the `Outbuilding` group — the rows carrying adjustments a QC review exists to
flag. Nothing errored; the map was just short.

These tests pin the thresholds as fractions of page height so the pixel
constants cannot creep back, and pin the asymmetry alarm that was the only
visible symptom.

The fixture is a synthetic PDF drawn to the measured geometry rather than the
real 40-page report, which is 15 MB and untracked.
"""
from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("numpy")

from app.extraction.vision.structural_router import (  # noqa: E402
    SectionBand, build_section_map, check_health, find_bands, row_group_template)

_PAGE_W, _PAGE_H = 612.0, 792.0
# Fractional x extents measured off the report: tabs are narrow rounded rects,
# grid row-group bands span the table.
_X0 = 0.145
_TAB_RIGHT = _X0 + 0.19
_ROW_RIGHT = _X0 + 0.70
# At 100 DPI a 792pt page is 1100px, so one pixel is 0.72pt.
_PT_PER_PX_100 = _PAGE_H / 1100.0


def _band(page, y_frac: float, *, height_px: float, right: float,
          companion: bool = True, rule: bool = False) -> None:
    """Draw one band at the given height IN 100-DPI PIXELS, with the companion
    run the real form renders just below it.

    `rule` adds the near-full-width underline the form draws beside a section
    tab. It is the reason band kind cannot be read off a single sampled row.
    """
    y0 = y_frac * _PAGE_H
    h = height_px * _PT_PER_PX_100
    page.draw_rect(fitz.Rect(_X0 * _PAGE_W, y0, right * _PAGE_W, y0 + h),
                   color=(0, 0, 0), fill=(0, 0, 0))
    if rule:
        page.draw_rect(
            fitz.Rect(_X0 * _PAGE_W, y0 + h - _PT_PER_PX_100,
                      0.92 * _PAGE_W, y0 + h),
            color=(0, 0, 0), fill=(0, 0, 0))
    if companion:
        gap = 5 * _PT_PER_PX_100
        page.draw_rect(
            fitz.Rect(_X0 * _PAGE_W, y0 + h + gap,
                      right * _PAGE_W, y0 + h + gap + 4 * _PT_PER_PX_100),
            color=(0, 0, 0), fill=(0, 0, 0))


@pytest.fixture()
def router_pdf(tmp_path):
    """Four pages mirroring the report's real structure.

    p1 no tab (cover) · p2 three tabs · p3 grid page with five row-groups, one of
    which renders at the 5px height that used to be dropped · p4 the paired grid
    page, which must match p3 band for band.
    """
    path = tmp_path / "router.pdf"
    doc = fitz.open()

    doc.new_page(width=_PAGE_W, height=_PAGE_H)  # p1: cover, no tab

    p2 = doc.new_page(width=_PAGE_W, height=_PAGE_H)
    for y in (0.0482, 0.443, 0.800):
        _band(p2, y, height_px=7, right=_TAB_RIGHT)

    for _ in range(2):  # p3 and p4: identical layout, different comparables
        pg = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        _band(pg, 0.0482, height_px=7, right=_TAB_RIGHT)
        for y, h in ((0.089, 6), (0.475, 16), (0.572, 7), (0.667, 16), (0.777, 5)):
            _band(pg, y, height_px=h, right=_ROW_RIGHT)

    doc.save(str(path))
    doc.close()
    return path


def test_five_pixel_band_is_detected(router_pdf):
    """The regression. A row-group rendering 5px at 100 DPI is real and must be
    found; the old `6 <= h` floor dropped exactly this band."""
    bands = find_bands(router_pdf, 3, dpi=100)
    assert len(bands) == 6, f"expected 6 bands, got {[b.y_frac for b in bands]}"

    short = [b for b in bands if 0.77 <= b.y_frac <= 0.79]
    assert short, "the 5px row-group was dropped — the height floor is too high"
    assert short[0].kind == "row_group"


def test_grid_pages_are_symmetric(router_pdf):
    """Structurally identical pages must yield identical structure. Asymmetry was
    the only visible symptom the one-pixel bug ever produced."""
    assert len(find_bands(router_pdf, 3)) == len(find_bands(router_pdf, 4))


@pytest.mark.parametrize("dpi", [100, 150, 200])
def test_thresholds_are_dpi_independent(router_pdf, dpi):
    """Every threshold is a fraction of page height, so band counts must not move
    with render resolution. A pixel constant would fail at least one of these."""
    assert len(find_bands(router_pdf, 3, dpi=dpi)) == 6
    assert len(find_bands(router_pdf, 2, dpi=dpi)) == 3


def test_band_kind_comes_from_width_not_a_model(router_pdf):
    """Tabs and row-groups separate on width with no overlap, so kind never costs
    a call."""
    bands = find_bands(router_pdf, 3, dpi=100)
    tabs = [b for b in bands if b.kind == "section_tab"]
    rows = [b for b in bands if b.kind == "row_group"]
    assert len(tabs) == 1 and len(rows) == 5
    assert max(b.width_frac for b in tabs) < min(b.width_frac for b in rows)


@pytest.fixture()
def ruled_tab_pdf(tmp_path):
    """A section tab carrying the form's near-full-width underline rule."""
    path = tmp_path / "ruled.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=_PAGE_W, height=_PAGE_H)
    _band(pg, 0.0482, height_px=7, right=_TAB_RIGHT, rule=True)
    _band(pg, 0.400, height_px=16, right=_ROW_RIGHT)
    doc.save(str(path))
    doc.close()
    return path


@pytest.mark.parametrize("dpi", [100, 150, 200])
def test_underline_rule_does_not_reclassify_a_tab(ruled_tab_pdf, dpi):
    """A tab's underline rule spans ~0.92 of the page, so any single sampled row
    can measure the RULE instead of the tab and call it a row-group. Which rows
    those are moves with render DPI, so sampling made the classification
    resolution-dependent — 50/20 at 100 DPI drifting to 46/24 at 200. The kind
    must come from the median across the run's rows."""
    bands = find_bands(ruled_tab_pdf, 1, dpi=dpi)
    kinds = [b.kind for b in bands]
    assert kinds == ["section_tab", "row_group"], f"at {dpi} DPI got {kinds}"


def test_sections_starting_mid_page_are_found(router_pdf):
    """Page 19 of the real report opens three sections, two of them below the
    header band. Scanning only the top of the page misses them."""
    bands = find_bands(router_pdf, 2, dpi=100)
    assert len(bands) == 3
    assert max(b.y_frac for b in bands) > 0.5


def test_untabbed_page_inherits_the_previous_section():
    """A page with no tab is a continuation whose heading did not repeat, not a
    gap. The cover inherits nothing, because there is nothing before it."""
    bands = [
        SectionBand(page=2, y0=53, y1=70, page_h=1100, width_frac=0.18,
                    kind="section_tab", label="Site"),
        SectionBand(page=4, y0=53, y1=70, page_h=1100, width_frac=0.18,
                    kind="section_tab", label="Sketch"),
    ]
    page_sections, section_pages = build_section_map(bands, [1, 2, 3, 4])

    assert page_sections[1] == []            # cover: nothing to carry
    assert page_sections[2] == ["Site"]
    assert page_sections[3] == ["Site"]      # inherited, no tab of its own
    assert page_sections[4] == ["Sketch"]
    assert section_pages["Site"] == [2, 3]


def test_only_the_last_section_on_a_page_spills_over():
    """When three sections open on one page, the page after continues the LAST of
    them — not all three."""
    bands = [
        SectionBand(page=1, y0=53, y1=70, page_h=1100, width_frac=0.18,
                    kind="section_tab", label=name)
        for name in ("Subject Listing Information", "Sales Contract",
                     "Prior Sale and Transfer History")
    ]
    page_sections, _ = build_section_map(bands, [1, 2])
    assert len(page_sections[1]) == 3
    assert page_sections[2] == ["Prior Sale and Transfer History"]


def test_health_alarms_on_a_dropped_row_group():
    """The alarm that would have caught the original bug on the real report."""
    def _grid(page, n):
        return [SectionBand(page=page, y0=100 * i, y1=100 * i + 8, page_h=1100,
                            width_frac=0.70, kind="row_group") for i in range(n)]

    healthy = {21: _grid(21, 6), 22: _grid(22, 6), 23: _grid(23, 6), 24: _grid(24, 6)}
    assert check_health(healthy) == []

    dropped = dict(healthy)
    dropped[21] = _grid(21, 5)
    alarms = check_health(dropped)
    assert any("asymmetric grid pair" in a for a in alarms)


def test_health_alarms_when_geometry_does_not_apply():
    """A different vendor's renderer may not draw tabs at all. That must degrade
    loudly, never back to positional windows."""
    alarms = check_health({p: [] for p in range(1, 11)})
    assert any("geometry does not apply" in a for a in alarms)


def test_one_untabbed_cover_in_a_short_excerpt_is_not_an_alarm():
    """The blank-page test is a PROPORTION, and a proportion needs a sample.

    Two untabbed pages in a 40-page report is 5%; the same two in an eight-page
    excerpt is 25% and would condemn a perfectly good map. Only the
    all-pages-blank case is conclusive at any length.
    """
    tab = [SectionBand(page=0, y0=53, y1=70, page_h=1100, width_frac=0.18,
                       kind="section_tab")]
    short = {1: [], 2: tab, 3: tab, 4: tab}
    assert check_health(short) == []

    # The real report's shape: 2 untabbed of 40 is well inside tolerance.
    long_doc = {p: (tab if p not in (1, 38) else []) for p in range(1, 41)}
    assert check_health(long_doc) == []


class _StubProvider:
    """Returns labels in reading order, so the batching contract is exercised
    without a network call."""

    name = "stub"
    model = "stub"

    def __init__(self, labels):
        self._labels = list(labels)
        self.calls = 0
        self.images_seen = 0

    def transcribe(self, images, instruction, schema, *, max_tokens=4000,
                   effort="low"):
        from app.extraction.vision.provider import VisionResponse

        self.calls += 1
        self.images_seen += len(images)
        take, self._labels = self._labels[:14], self._labels[14:]
        return VisionResponse(
            data={"bands": [
                {"index": i, "label": lab, "continued": lab.endswith("*")}
                for i, lab in enumerate(take, start=1)
            ]},
            output_tokens=len(take) * 8,
        )


def test_route_produces_a_triage_compatible_map(router_pdf):
    """The router's output must drop in wherever triage's `page_sections` was
    consumed, or it is a rewrite rather than a replacement."""
    from app.extraction.vision.structural_router import route

    # p1 none · p2 three tabs · p3 tab + 5 row-groups · p4 tab + 5 row-groups
    labels = (["Assignment Information", "Subject Property", "Site"]
              + ["Sales Comparison Approach", "General Information", "Site",
                 "Dwelling(s)", "Unit(s)", "Quality and Condition"]
              + ["Sales Comparison Approach", "Property Amenities",
                 "Vehicle Storage", "Outbuilding", "Summary",
                 "Overall Quality and Condition"])
    provider = _StubProvider(labels)

    out = route(router_pdf, [1, 2, 3, 4], provider)

    assert out["usable"]
    assert out["bands"]["total"] == 15
    assert out["bands"]["section_tabs"] == 3 + 1 + 1
    assert out["bands"]["row_groups"] == 10
    assert out["no_tab_pages"] == [1]

    # Triage-compatible: {page: [section names]}
    assert out["page_sections"][2] == ["Assignment Information",
                                       "Subject Property", "Site"]
    assert out["page_sections"][3] == ["Sales Comparison Approach"]
    assert out["section_pages"]["Sales Comparison Approach"] == [3, 4]

    # Row groups are kept separately — they are the grid's row-label template,
    # not sections, and must never be routed to as if they were.
    assert "General Information" not in out["section_pages"]
    assert len(out["row_groups"][3]) == 5


def test_labelling_is_batched_not_one_call_per_band(router_pdf):
    """Fifteen bands must cost two calls, not fifteen. Per-call overhead
    dominates a request that carries a sliver of image and returns a few tokens."""
    from app.extraction.vision.structural_router import route

    provider = _StubProvider(["X"] * 15)
    route(router_pdf, [1, 2, 3, 4], provider)
    assert provider.calls == 2
    assert provider.images_seen == 2      # one composed sheet per call


def test_row_group_template_is_the_transposition_binding():
    """Sum is invariant to row permutation, so the label template is the only
    thing that makes a transposed adjustment detectable."""
    bands = [
        SectionBand(page=21, y0=98, y1=114, page_h=1100, width_frac=0.70,
                    kind="row_group", label="General Information"),
        SectionBand(page=21, y0=523, y1=539, page_h=1100, width_frac=0.70,
                    kind="row_group", label="Site"),
        SectionBand(page=21, y0=53, y1=70, page_h=1100, width_frac=0.18,
                    kind="section_tab", label="Sales Comparison Approach"),
    ]
    template = row_group_template(bands)
    assert template == {21: ["General Information", "Site"]}
