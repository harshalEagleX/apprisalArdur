"""
extraction.vision.structural_router (srt-1.0.0) — section discovery from pixels.

Replaces positional windows, and replaces most of triage.

**Why this exists.** A section is currently located by a proportional window over
the extractable pages. That is layout-tolerant in the sense that it never crashes,
and wrong in the way that matters: UAD 3.6 is a single dynamic URAR whose sections
expand, contract and repeat with property type and scope of work, so a window
computed from document position lands on the wrong pages as soon as the next
report is a condo, a 2-4, or an FHA assignment. A VLM handed the wrong page does
not error — it returns plausible values for fields that are not there.

This is not hypothetical. `improvements` spanned pp. 7-14, its window landed on
[11,12,13], and `gla`, `bedrooms`, `baths`, `year_built`, quality and condition
were all reported ABSENT while the call returned valid JSON.

**What replaces it.** Section tabs in the URAR are black rounded rectangles drawn
by the form engine, not by the appraiser, so they are geometrically invariant.
Measured across all 40 pages of the Turner Rd report: the page-top tab sits at
y = 0.0482 on all 38 tabbed pages — min, max and mean identical, zero variance —
and the two pages with no tab are exactly the cover and one boilerplate page.
So section structure can be recovered from pixels, per document, for free.

**Three things this buys that triage does not.**

1. It costs no model call to find the bands, and one call per ~14 bands to read
   their labels — about four calls for a 40-page report, against triage's
   per-page-batch pass.
2. It finds sections that START MID-PAGE. Page 19 alone opens Subject Listing
   Information (y=4.8%), Sales Contract (47.5%) and Prior Sale and Transfer
   History (74.3%). A per-page heading list cannot express that, and a window
   cannot see it at all.
3. The SAME detector returns the sales grid's row-group bands, which is the
   row-label template `grid_reconcile` needs to catch a transposed adjustment.
   Sum is invariant to row permutation, so without labels a transposition
   certifies clean — which is exactly what comp_4 did.

**The one-pixel bug this module exists to not have.** An earlier form of this
detector filtered bands with `6 <= height_px <= 40` at 100 DPI. On page 21 the
`Quality and Condition` row-group renders 5px tall and was silently dropped; on
page 23 the identical band renders 6px and survived. It also merged runs with a
4px gap, when every band is a PAIR of runs (main band plus a 4-5px companion).
Net effect: 64 bands found where there are 70, losing one section tab and five
row-groups — including `Outbuilding`, which is where the unsupported adjustments
a QC review is supposed to flag actually live.

Every threshold here is therefore a FRACTION OF PAGE HEIGHT, never a pixel
constant. Verified byte-identical output at 100, 150 and 200 DPI.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.vision.budget import BudgetExceeded, BudgetGovernor
from app.extraction.vision.provider import VisionProvider
from app.extraction.vision.render import RenderedPage, render_region

__version__ = "srt-1.0.0"

logger = logging.getLogger(__name__)

# Geometry, as fractions of page dimensions. Measured off the form's own rules.
_TAB_X0, _TAB_X1 = 0.145, 0.30
_DARK_LEVEL = 90          # 8-bit grey below this is ink
_DARK_COVERAGE = 0.75     # fraction of the x-window that must be ink
# Joins a band to its companion run. At 4px (the naive value) the pair stays
# split and both halves fall under the height floor — see the module docstring.
_MERGE_GAP_FRAC = 0.0127
_MIN_H_FRAC, _MAX_H_FRAC = 0.0036, 0.0545
# Section tabs are narrow rounded rects (0.18-0.22 of page width); grid row-group
# bands span the table (0.70). The classes do not overlap, so band KIND is
# geometry and never costs a model call.
_KIND_SPLIT_FRAC = 0.45
_RUN_BREAK_FRAC = 0.02    # horizontal ink gap that ends a band's extent

# Bands per label-reading call. Fourteen crops stack into one contact sheet that
# stays legible; batching is what turns ~50 calls into ~4.
_SHEET_SIZE = 14
_SHEET_DPI = 260
_LABEL_TOKENS = 400

# Above this share of blank pages the geometry assumption does not hold for this
# vendor's renderer, and the caller must degrade rather than trust the map.
_BLANK_PAGE_ALARM = 0.20
# Below this many pages the share above is noise, not signal — one untabbed
# cover in a short excerpt is not evidence about the renderer.
_MIN_PAGES_FOR_RATIO = 8


@dataclass(frozen=True)
class SectionBand:
    """One detected band: a section tab, or a grid row-group header."""

    page: int          # 1-based
    y0: int            # pixel rows, at the detection DPI
    y1: int
    page_h: int
    width_frac: float
    kind: str          # "section_tab" | "row_group"
    label: Optional[str] = None
    continued: bool = False

    @property
    def y_frac(self) -> float:
        return self.y0 / self.page_h

    def clip(self, pad_frac: float = 0.006) -> Dict[str, float]:
        """Fractional clip for rendering this band, with a little vertical air."""
        y0 = max(0.0, self.y0 / self.page_h - pad_frac)
        y1 = min(1.0, self.y1 / self.page_h + pad_frac)
        return {"x": 0.12, "y": y0, "w": 0.50, "h": max(y1 - y0, 0.004)}


# ── pass 1: detection (deterministic, zero model cost) ────────────────────────

def _band_kind(gray, y0: int, y1: int, x_start: int, width: int) -> Tuple[str, float]:
    """Classify by how far right the band's OWN ink extends.

    Measured on the densest row of the band's FIRST run — not the midpoint, and
    not the densest row of the whole merged span. A band is a merged pair whose
    second run is the section's underline RULE, which spans nearly the full page
    width. Sampling the merged span therefore measures the rule and classifies
    every section tab as a row-group; sampling the midpoint lands in the white
    gap between the two and measures nothing.
    """
    import numpy as np

    ink = gray[y0:y1] < _DARK_LEVEL
    if not ink.size:
        return "section_tab", 0.0

    limit = int(width * _RUN_BREAK_FRAC)
    extents = []
    for row in ink:
        last, gap = x_start, 0
        for x in range(x_start, width):
            if row[x]:
                last, gap = x, 0
            else:
                gap += 1
                if gap > limit:
                    break
        extents.append((last - x_start) / width)

    # MEDIAN across the run's rows, not any single row. A tab's rows all measure
    # ~0.18-0.22 except where the underline rule bleeds in at ~0.70, and which
    # rows those are shifts with render DPI. One sampled row therefore makes the
    # classification resolution-dependent; the median does not.
    frac = float(np.median(extents))
    return ("section_tab" if frac < _KIND_SPLIT_FRAC else "row_group"), round(frac, 3)


def find_bands(pdf_path, page_no: int, dpi: int = 100) -> List[SectionBand]:
    """Detect section tabs and row-group bands on one 1-indexed page.

    Never raises: a page that cannot be rasterised yields no bands, which the
    caller reads as "inherit from the previous page" rather than as a failure.
    """
    try:
        import fitz
        import numpy as np
    except ImportError:  # pragma: no cover - dependency guard
        logger.warning("structural_router: PyMuPDF/numpy unavailable")
        return []

    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_no - 1]
        pm = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        gray = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width)
    except Exception as exc:
        logger.warning("structural_router: page %d unreadable: %s", page_no, exc)
        return []

    h, w = gray.shape
    x0, x1 = int(w * _TAB_X0), int(w * _TAB_X1)
    ink = (gray[:, x0:x1] < _DARK_LEVEL).mean(axis=1) > _DARK_COVERAGE

    runs: List[List[int]] = []
    start = None
    for y, is_ink in enumerate(ink):
        if is_ink and start is None:
            start = y
        elif not is_ink and start is not None:
            runs.append([start, y])
            start = None
    if start is not None:
        runs.append([start, h])

    # Merge each band with its companion run, but remember where the band's OWN
    # run ended — the companion is the section's underline rule and measuring
    # across it would classify every tab as a full-width row-group.
    gap = int(round(h * _MERGE_GAP_FRAC))
    merged: List[List[int]] = []          # [start, end, first_run_end]
    for s, e in runs:
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = e
        else:
            merged.append([s, e, e])

    lo, hi = int(round(h * _MIN_H_FRAC)), int(round(h * _MAX_H_FRAC))
    out: List[SectionBand] = []
    for s, e, first_end in merged:
        if not (lo <= e - s <= hi):
            continue
        kind, frac = _band_kind(gray, s, first_end, x0, w)
        out.append(SectionBand(page=page_no, y0=s, y1=e, page_h=h,
                               width_frac=frac, kind=kind))
    return out


def detect_all(pdf_path, pages: List[int], dpi: int = 100) -> Dict[int, List[SectionBand]]:
    return {p: find_bands(pdf_path, p, dpi=dpi) for p in pages}


# ── pass 2: labelling (batched — ~4 calls for a 40-page report) ───────────────

_LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "bands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer",
                              "description": "1-based position, top to bottom"},
                    "label": {"type": "string",
                              "description": "the band's printed text, verbatim, "
                                             "WITHOUT any '(continued)' suffix"},
                    "continued": {"type": "boolean",
                                  "description": "true if the band reads '(continued)'"},
                },
                "required": ["index", "label", "continued"],
            },
        }
    },
    "required": ["bands"],
}

_LABEL_INSTRUCTION = (
    "Each row of this image is one heading strip cropped from an appraisal form, "
    "stacked top to bottom in order.\n"
    "For each strip, report its printed heading text exactly as shown.\n"
    "Rules:\n"
    "1. Report the heading only — ignore any body text to the right of it.\n"
    "2. Strip the '(continued)' suffix from `label` and set `continued` true instead.\n"
    "3. Return exactly one entry per strip, numbered from 1 in the order shown.\n"
    "4. If a strip is illegible, return an empty label rather than guessing."
)


def _compose_sheet(crops: List[RenderedPage]) -> Optional[RenderedPage]:
    """Stack band crops into one contact sheet.

    Batching is the whole economy of this pass: labelled one at a time these are
    ~50 calls whose latency is dominated by per-call overhead, since each carries
    only a sliver of image and returns a handful of tokens.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - dependency guard
        logger.warning("structural_router: Pillow unavailable — cannot batch labels")
        return None

    try:
        imgs = [Image.open(io.BytesIO(base64.b64decode(c.b64))) for c in crops]
        pad = 12
        width = max(i.width for i in imgs)
        height = sum(i.height + pad for i in imgs) + pad
        canvas = Image.new("RGB", (width, height), "white")
        y = pad
        for im in imgs:
            canvas.paste(im, (0, y))
            y += im.height + pad
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
    except Exception as exc:
        logger.warning("structural_router: sheet composition failed: %s", exc)
        return None

    return RenderedPage(page=crops[0].page,
                        b64=base64.b64encode(png).decode("ascii"),
                        media_type="image/png", width=canvas.width,
                        height=canvas.height, dpi=_SHEET_DPI)


def label_bands(pdf_path, bands: List[SectionBand], provider: VisionProvider,
                governor: Optional[BudgetGovernor] = None,
                ) -> Tuple[List[SectionBand], Dict[str, Any]]:
    """Read every band's printed heading. Returns (labelled bands, meta)."""
    meta: Dict[str, Any] = {"sheets": 0, "calls": [], "errors": []}
    if not bands:
        return [], meta

    labelled: List[SectionBand] = []
    for i in range(0, len(bands), _SHEET_SIZE):
        chunk = bands[i:i + _SHEET_SIZE]
        crops = [c for c in (render_region(pdf_path, b.page, dpi=_SHEET_DPI,
                                           clip=b.clip()) for b in chunk)
                 if c is not None]
        sheet = _compose_sheet(crops) if len(crops) == len(chunk) else None
        if sheet is None:
            meta["errors"].append(f"sheet {i // _SHEET_SIZE}: render failed")
            labelled.extend(chunk)
            continue

        if governor is not None:
            try:
                governor.check(sheet.tokens, _LABEL_TOKENS)
            except BudgetExceeded as exc:
                meta["errors"].append(str(exc))
                labelled.extend(bands[i:])
                break

        resp = provider.transcribe([sheet], _LABEL_INSTRUCTION, _LABEL_SCHEMA,
                                   max_tokens=_LABEL_TOKENS, effort="low")
        meta["sheets"] += 1
        meta["calls"].append({"sheet": i // _SHEET_SIZE, "ok": resp.ok,
                              "output_tokens": resp.output_tokens,
                              "error": resp.error})
        if not resp.ok:
            meta["errors"].append(resp.error or "unknown")
            labelled.extend(chunk)
            continue

        by_index = {}
        for entry in (resp.data.get("bands") or []):
            try:
                by_index[int(entry.get("index"))] = entry
            except (TypeError, ValueError):
                continue
        for n, band in enumerate(chunk, start=1):
            entry = by_index.get(n) or {}
            raw = (entry.get("label") or "").strip()
            labelled.append(SectionBand(
                page=band.page, y0=band.y0, y1=band.y1, page_h=band.page_h,
                width_frac=band.width_frac, kind=band.kind,
                label=raw or None, continued=bool(entry.get("continued")),
            ))
    return labelled, meta


# ── pass 3: the map ───────────────────────────────────────────────────────────

def build_section_map(bands: List[SectionBand], pages: List[int],
                      ) -> Tuple[Dict[int, List[str]], Dict[str, List[int]]]:
    """Bands -> (page_sections, section_pages).

    `page_sections` matches the shape the triage pass produces, so this drops in
    wherever triage output is consumed.

    A page with no tab INHERITS the previous page's section — it is a
    continuation whose heading simply did not repeat, not a gap. On the Turner Rd
    report that is the cover (p1, which inherits nothing) and p38.
    """
    tabs_by_page: Dict[int, List[str]] = {}
    for b in bands:
        if b.kind != "section_tab" or not b.label:
            continue
        tabs_by_page.setdefault(b.page, []).append(b.label)

    page_sections: Dict[int, List[str]] = {}
    carried: List[str] = []
    for page in sorted(pages):
        here = tabs_by_page.get(page)
        if here:
            page_sections[page] = list(here)
            carried = [here[-1]]          # only the LAST section spills over
        elif carried:
            page_sections[page] = list(carried)
        else:
            page_sections[page] = []      # cover page: nothing to inherit

    section_pages: Dict[str, List[int]] = {}
    for page, names in page_sections.items():
        for name in names:
            section_pages.setdefault(name, []).append(page)
    for name in section_pages:
        section_pages[name] = sorted(set(section_pages[name]))
    return page_sections, section_pages


def row_group_template(bands: List[SectionBand]) -> Dict[int, List[str]]:
    """Grid row-group labels per page — the binding `grid_reconcile` lacks.

    Sum is invariant to row permutation, so an adjustment sitting in the wrong
    row still certifies. Only a label template makes transposition detectable.
    """
    out: Dict[int, List[str]] = {}
    for b in bands:
        if b.kind == "row_group" and b.label:
            out.setdefault(b.page, []).append(b.label)
    return out


def check_health(bands_by_page: Dict[int, List[SectionBand]]) -> List[str]:
    """Alarms for the failure mode this module is most exposed to: silently
    finding FEWER bands than exist.

    A detector that can drop a record without erroring must be able to prove it
    did not. Structurally identical pages must yield identical structure, so
    asymmetry across a grid page-pair is the alarm — it is the only visible
    symptom the one-pixel height bug ever produced.
    """
    alarms: List[str] = []
    if not bands_by_page:
        return ["no pages inspected"]

    blank = [p for p, b in bands_by_page.items() if not b]
    # No tab anywhere is conclusive at any document length. The PROPORTION test
    # is not: on a 40-page report two untabbed pages is 5%, but on a four-page
    # excerpt one untabbed cover is 25% and would condemn a perfectly good map.
    # So the ratio only speaks once there are enough pages for it to mean
    # anything.
    if len(blank) == len(bands_by_page):
        alarms.append(
            f"geometry does not apply: no band on any of {len(bands_by_page)} "
            "pages — this renderer does not draw section tabs. Degrade to "
            "per-page heading reads, never to positional windows, which are "
            "cheap and silently wrong."
        )
    elif (len(bands_by_page) >= _MIN_PAGES_FOR_RATIO
            and len(blank) / len(bands_by_page) > _BLANK_PAGE_ALARM):
        alarms.append(
            f"geometry does not apply: {len(blank)}/{len(bands_by_page)} pages "
            "carry no band. Degrade to per-page heading reads — never to "
            "positional windows, which are cheap and silently wrong."
        )

    grid_pages = sorted(p for p, b in bands_by_page.items()
                        if any(x.kind == "row_group" for x in b))
    # Grid pages come in pairs (comps 1-3, then 4-6), so page N and page N+2 are
    # the same layout with different comparables and must match band for band.
    for a, b in zip(grid_pages, grid_pages[2:]):
        if len(bands_by_page[a]) != len(bands_by_page[b]):
            alarms.append(
                f"asymmetric grid pair: p{a} has {len(bands_by_page[a])} bands, "
                f"p{b} has {len(bands_by_page[b])}. A row-group was dropped, so "
                "the row-label template is incomplete and transposition checks "
                "cannot bind."
            )
    return alarms


def route(pdf_path, pages: List[int], provider: VisionProvider,
          governor: Optional[BudgetGovernor] = None, dpi: int = 100,
          ) -> Dict[str, Any]:
    """Full router pass: detect, label, map, self-check.

    Returns a dict carrying `page_sections` (triage-compatible), `section_pages`,
    `row_groups`, `health` and `meta`. `usable` is False when the health check
    found something that makes the map untrustworthy, and the caller should then
    degrade explicitly rather than consume a map that may be missing sections.
    """
    bands_by_page = detect_all(pdf_path, pages, dpi=dpi)
    health = check_health(bands_by_page)

    flat = [b for p in sorted(bands_by_page) for b in bands_by_page[p]]
    labelled, meta = label_bands(pdf_path, flat, provider, governor)
    page_sections, section_pages = build_section_map(labelled, pages)

    tabs = sum(1 for b in labelled if b.kind == "section_tab")
    rows = sum(1 for b in labelled if b.kind == "row_group")
    unlabelled = sum(1 for b in labelled if not b.label)
    if unlabelled:
        health.append(f"{unlabelled} of {len(labelled)} bands could not be labelled")

    return {
        "page_sections": page_sections,
        "section_pages": section_pages,
        "row_groups": row_group_template(labelled),
        "bands": {"total": len(labelled), "section_tabs": tabs, "row_groups": rows,
                  "unlabelled": unlabelled},
        "no_tab_pages": [p for p, b in bands_by_page.items() if not b],
        "health": health,
        "usable": not any(h.startswith(("geometry does not apply", "asymmetric"))
                          for h in health),
        "meta": meta,
    }
