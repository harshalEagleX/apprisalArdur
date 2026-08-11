"""
extraction.page_map (pmp-1.0.0) — structural page profiling: a table of contents
without reading a word.

Answers two questions before any model is called, for free:

  1. **What KIND of document is this?** digital (real text layer) | flattened
     (glyphs drawn as vector outlines — the PDFium/print-to-PDF case) | scanned
     (page images). This decides the whole extraction strategy, and it is the
     difference between "pdf_digital will work" and "pdf_digital will silently
     return 0 fields and nobody will notice".

  2. **Which pages are worth spending a vision call on?** A 40-page UAD 3.6
     report is ~40% photo sheets carrying no extractable field. Dropping them
     here is the single biggest cost lever in the 3.6 path — and it costs one
     pass of PyMuPDF metadata, no API key, no network.

Deliberately structural, never textual. The counts below (images, drawings,
chars, fonts) survive a flattened PDF where every text-based heuristic reads
zero. `classify_document` on the 2026-08-03 sample returns "flattened" from
0 chars + 0 fonts + 27k drawings/page, which is exactly the signal that the
glyphs are bezier outlines rather than text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__version__ = "pmp-1.0.0"

logger = logging.getLogger(__name__)

# Document classes.
DIGITAL, FLATTENED, SCANNED = "digital", "flattened", "scanned"

# Page kinds.
TEXT_DENSE, PHOTO_GRID, MIXED, BLANK = "text_dense", "photo_grid", "mixed", "blank"

# A page with this many chars is carrying real text, not stray artifacts.
_DIGITAL_CHARS_PER_PAGE = 200
# Vector-drawing density that means "glyphs were flattened to outlines". A genuine
# scan is a single big image with almost no drawings; a flattened page is tens of
# thousands of tiny curves. The sample runs ~27,000 on a dense page.
_FLATTENED_DRAWS_PER_PAGE = 500

# Photo-sheet detection. Comp/subject photo pages carry many embedded images and
# little vector work; a data page is the inverse.
#
# **The image threshold is set from measured data, and it is deliberately
# conservative.** On the 2026-08-03 sample the two populations separate cleanly
# on IMAGE COUNT, not on drawing count:
#
#     true photo sheets (pp. 5,6,10-12,25,27-37) : 18-112 images, ~300-500 draws
#     data pages with thumbnails (pp. 4,16,17,18,34) :  7-13 images, ~300-370 draws
#
# Drawing count does NOT separate them — both sit near 300. An earlier threshold
# of 6 images therefore swept pages 16-18 into "photo" and dropped them, and
# those pages carry the market/housing-trends block including the 36-month trend
# matrix. Losing that matrix does not merely reduce coverage, it MANUFACTURES a
# false positive: without it a naive "declining market ⇒ time adjustments must be
# negative" reading flags three adjustments that are provably correct once the
# non-monotonic monthly figures are in hand.
#
# So the bias is toward paying for a photo page rather than dropping a data page.
# The asymmetry is stark: an extra page costs a fraction of a cent against a
# budget that is an order of magnitude underspent, while a dropped data page
# costs fields, and silently.
_PHOTO_MIN_IMAGES = 15
_PHOTO_MAX_DRAWINGS = 600
_BLANK_MAX_DRAWINGS = 100


@dataclass
class PageProfile:
    """One page's structural fingerprint. No text is read off the page."""

    page: int                       # 1-indexed, matching ExtractedField.page
    chars: int
    fonts: int
    images: int
    drawings: int
    width: float
    height: float
    # Long horizontal rules — the signature of a TABLE, and the single best
    # structural discriminator on this form. See likely_grid_pages().
    hlines: int = 0
    kind: str = MIXED
    # Filled by the vision triage pass, not here — page_map has no idea what a
    # "Sales Comparison Approach" is, only that this page has data on it.
    sections: List[str] = field(default_factory=list)

    @property
    def extractable(self) -> bool:
        """Worth spending a vision call on.

        **Only genuinely blank pages are excluded.** Photo-classified pages used
        to be dropped here as pure cost, and that was wrong — provably, on this
        document:

            page 33 — "Value Reconciliation" table restating EVERY comparable's
                      adjusted price, weight and weighted contribution. It is the
                      free, independent answer key for the sales grid, the one
                      region whose misreads are hardest to catch.

            page 33: 29 images, 44.2% image area, 305 drawings
            page 27: 20 images, 44.2% image area, 304 drawings  (a real photo sheet)

        Structurally identical. On a FLATTENED PDF there is no text layer to
        separate them by, so no structural rule can tell a data table from a
        photo grid — any threshold that drops one drops the other. Interior
        photos also carry the only evidence for appliance fields, and photo
        PRESENCE is itself a checklist item.

        So the cost lever is DPI and call shape, never discarding pages. A
        skipped page costs nothing and loses evidence silently, which is the
        worst trade available.
        """
        return self.kind != BLANK


def profile(pdf_path) -> List[PageProfile]:
    """Structural profile of every page. Never raises — an unreadable PDF yields
    an empty list and the caller degrades, per the §16 partial-failure contract."""
    import fitz

    out: List[PageProfile] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("page_map: cannot open %s: %s", pdf_path, exc)
        return out

    try:
        for i, page in enumerate(doc):
            try:
                chars = len(page.get_text().strip())
                fonts = len(page.get_fonts())
                images = len(page.get_images())
                # get_drawings() is the expensive call (tens of thousands of items
                # on a flattened page) but it is the ONLY signal that separates
                # "flattened" from "scanned", and both read 0 chars / 0 fonts.
                draws = page.get_drawings()
                drawings = len(draws)
                rect = page.rect
                hlines = _count_hlines(draws)
            except Exception as exc:
                logger.warning("page_map: page %d unreadable: %s", i + 1, exc)
                continue
            out.append(PageProfile(
                page=i + 1, chars=chars, fonts=fonts, images=images,
                drawings=drawings, width=rect.width, height=rect.height,
                hlines=hlines, kind=_classify_page(images, drawings),
            ))
    finally:
        doc.close()
    return out


def _classify_page(images: int, drawings: int) -> str:
    if images >= _PHOTO_MIN_IMAGES and drawings < _PHOTO_MAX_DRAWINGS:
        return PHOTO_GRID
    if images == 0 and drawings >= _FLATTENED_DRAWS_PER_PAGE:
        return TEXT_DENSE
    if images == 0 and drawings < _BLANK_MAX_DRAWINGS:
        return BLANK
    return MIXED


def classify_document(profiles: List[PageProfile]) -> str:
    """digital | flattened | scanned — decides which extraction path runs.

    A "flattened" verdict is the important one: it means every text-based
    extractor (pdf_digital, grid, checkbox, sweep) will return zero WITHOUT
    ERRORING, which is how confidently-wrong output got shipped before. The
    caller should route to vision, not to OCR.
    """
    if not profiles:
        return SCANNED
    n = len(profiles)
    total_chars = sum(p.chars for p in profiles)
    total_fonts = sum(p.fonts for p in profiles)
    total_draws = sum(p.drawings for p in profiles)

    if total_chars > _DIGITAL_CHARS_PER_PAGE * n:
        return DIGITAL
    if total_fonts == 0 and total_draws > _FLATTENED_DRAWS_PER_PAGE * n:
        return FLATTENED
    return SCANNED


def detect_uad_version(profiles: List[PageProfile], pdf_path=None) -> Optional[str]:
    """'3.6' | '2.6' | None (unknown). Text-based when there IS text; falls back
    to page count when there is not.

    A 1004 is 6-12 pages with 3 comps; the redesigned URAR runs 25-45 with 6.
    Page count alone is weak evidence, so it is only consulted when the text
    probe found nothing to read — which is exactly the flattened case.
    """
    if pdf_path is not None and any(p.chars for p in profiles):
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            try:
                text = " ".join(doc[i].get_text().lower()
                                for i in range(min(6, len(doc))))
            finally:
                doc.close()
            from app.pipeline.intake import _UAD36_MARKERS
            if any(m in text for m in _UAD36_MARKERS):
                return "3.6"
            if "uniform residential appraisal report" in text:
                return "2.6"
        except Exception as exc:
            logger.debug("page_map: uad text probe failed: %s", exc)

    if len(profiles) >= 25:
        return "3.6"
    if profiles:
        return "2.6"
    return None


def _count_hlines(drawings, min_len: float = 40.0, flat: float = 0.6) -> int:
    """Long horizontal rules on a page — i.e. table row separators."""
    n = 0
    for item in drawings:
        for op in item.get("items", ()):
            if op[0] != "l":
                continue
            p1, p2 = op[1], op[2]
            if abs(p1.y - p2.y) < flat and abs(p1.x - p2.x) > min_len:
                n += 1
    return n


def likely_grid_pages(profiles: List[PageProfile], top_n: int = 4,
                      min_hlines: int = 60) -> List[int]:
    """Pages holding the comparable sales grid — structurally, with no model
    call and no latency in front of the first extraction.

    **Ranked by long horizontal rules, not by drawing count.** Drawing count is
    the intuitive metric and it is WRONG here: on a flattened PDF every glyph is
    vector outlines, so the densest pages by that measure are the certification
    pages — 68,000+ drawings of pure prose, and not a table among them. Measured
    on the 2026-08-03 sample:

        page       21   22   23   24  | 38     39     | best non-grid
        drawings  2439 1498 2403 1820 | 5450   5890   | 2467   <- ranks certs first
        h-rules    200  114  200  114 |    0      2   |   54   <- ranks grid first

    Row rules are what makes a table a table, so they separate the grid from
    dense prose cleanly (200/114 vs 0/2) where raw density inverts the answer.
    `min_hlines` guards the case where a report simply has no grid: better to
    return nothing and record a degradation than to hand the grid extractor four
    arbitrary pages and let it invent comparables.

    Returned in page order — the grid spans page PAIRS and the pairing depends
    on their sequence.
    """
    candidates = [p for p in profiles if p.extractable and p.hlines >= min_hlines]
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda p: p.hlines, reverse=True)[:top_n]
    return sorted(p.page for p in ranked)


def extraction_plan(profiles: List[PageProfile]) -> Dict[str, object]:
    """What the vision pass should and should not pay for. Pure arithmetic —
    the caller logs this BEFORE spending anything, so the cost of a run is
    visible in advance rather than discovered on the invoice."""
    extractable = [p.page for p in profiles if p.extractable]
    skipped = [p.page for p in profiles if not p.extractable]
    return {
        "total_pages": len(profiles),
        "extractable_pages": extractable,
        "skipped_pages": skipped,
        "skipped_reason": {p.page: p.kind for p in profiles if not p.extractable},
        "document_class": classify_document(profiles),
        "kind_counts": {
            k: sum(1 for p in profiles if p.kind == k)
            for k in (TEXT_DENSE, PHOTO_GRID, MIXED, BLANK)
        },
    }
