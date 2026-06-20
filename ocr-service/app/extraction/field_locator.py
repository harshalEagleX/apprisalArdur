"""
Field locator — stamp each extracted value with WHERE it sits on the page.

Extraction produces VALUES; this pass produces their LOCATION. It reuses the
spatial word map of each PDF page (the same machinery the spatial extractor
already uses for label finding) to find the bounding box of every found value,
normalizes it to [0,1] fractions with a top-left origin, and stamps it on the
ExtractionResult as `bbox`. That single normalized box is what powers the
reviewer's click-to-scroll highlight — the Java DTO/entity/mapper and the PDF
viewer are already wired to consume `source_page` + `bbox_{x,y,w,h}`; only this
producing end was missing.

Separation of concerns (P-3):
  - It does NOT extract values — extractors already did that.
  - It does NOT touch rules — it only enriches ExtractionResult positions.

Precision gating (per the MIRA coordinate spec — be conservative, a page-only
scroll beats a highlight on the wrong line):
  - Page known   → search that page; a short value that occurs more than once
                   there is left page-level only (ambiguous column/row).
  - Page unknown → search the whole document and accept ONLY a unique match,
                   which also fills in `source_page`. Never guess a page.
  - Scanned page → no text layer → no words → no box (page-level only), exactly
                   the degraded behaviour MIRA describes for scanned appraisals.

Never raises (P-6): any failure leaves results unchanged and returns 0.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from app import config
from app.core.result import ExtractionResult, ExtractionResultSet
from app.ocr.spatial_extractor import SpatialWordMap, _normalize_for_match

logger = logging.getLogger(__name__)

PointBox = Tuple[float, float, float, float]   # (x0, y0, x1, y1) in PDF points
PageLookup = Callable[[int], Tuple[Optional[SpatialWordMap], float, float]]


def _normalized_box(box: PointBox, page_w: float, page_h: float, pad: float) -> Optional[Dict[str, float]]:
    """Convert a PDF-point box to a padded, clamped [0,1] fraction box
    (top-left origin) — the convention the PDF viewer expects."""
    if page_w <= 0 or page_h <= 0:
        return None
    x0, y0, x1, y1 = box
    x = x0 / page_w - pad
    y = y0 / page_h - pad
    w = (x1 - x0) / page_w + 2 * pad
    h = (y1 - y0) / page_h + 2 * pad
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0 - x)
    h = min(max(h, 0.0), 1.0 - y)
    if w <= 0.0 or h <= 0.0:
        return None
    return {"x": round(x, 5), "y": round(y, 5), "w": round(w, 5), "h": round(h, 5)}


def _candidate_strings(r: ExtractionResult) -> List[str]:
    """The strings worth trying to locate, best first: the normalized value, then
    the verbatim source passage when it differs and is short enough to be a field
    (not a whole paragraph)."""
    out: List[str] = []
    value = str(r.value).strip()
    if value:
        out.append(value)
    raw = (r.raw_source_text or "").strip()
    if raw and raw != value and len(raw) <= config.FIELD_LOCATOR_MAX_LEN:
        out.append(raw)
    return out


def _locate_one(r: ExtractionResult, page_count: int, page: PageLookup) -> Optional[Tuple[int, Dict[str, float]]]:
    """Find (page, normalized_box) for one result, or None to leave it page-level."""
    pad = config.FIELD_LOCATOR_PAD
    page_known = bool(r.source_page) and 1 <= r.source_page <= page_count

    for candidate in _candidate_strings(r):
        if len(candidate) > config.FIELD_LOCATOR_MAX_LEN:
            continue
        norm = _normalize_for_match(candidate)
        if not norm:
            continue
        short = len(norm) < config.FIELD_LOCATOR_MIN_LEN

        if page_known:
            wm, pw, ph = page(r.source_page)
            if wm is None:
                continue
            boxes = wm.locate_value(candidate)
            if not boxes:
                continue
            if short and len(boxes) > 1:
                continue  # ambiguous on the page — page-level only
            nb = _normalized_box(boxes[0], pw, ph, pad)
            if nb:
                return r.source_page, nb
            continue

        # Page unknown — only a document-unique match is trustworthy.
        if short:
            continue
        hit: Optional[Tuple[int, PointBox, float, float]] = None
        total = 0
        for pno in range(1, page_count + 1):
            wm, pw, ph = page(pno)
            if wm is None:
                continue
            boxes = wm.locate_value(candidate)
            if not boxes:
                continue
            total += len(boxes)
            if total > 1:
                break
            hit = (pno, boxes[0], pw, ph)
        if total == 1 and hit is not None:
            pno, box, pw, ph = hit
            nb = _normalized_box(box, pw, ph, pad)
            if nb:
                return pno, nb
    return None


def locate_fields(pdf_path, result_set: ExtractionResultSet) -> int:
    """Stamp `bbox` (and fill `source_page` when it was unknown) on every found
    value in `result_set` that can be located on the PDF. Returns the number of
    boxes stamped. Mutates results in place; never raises."""
    if not config.FIELD_LOCATOR_ENABLED:
        return 0
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("Field locator: could not open %s: %s", pdf_path, exc)
        return 0

    # Build each page's word map at most once.
    cache: Dict[int, Tuple[Optional[SpatialWordMap], float, float]] = {}

    def page(pno: int) -> Tuple[Optional[SpatialWordMap], float, float]:
        if pno not in cache:
            if 1 <= pno <= doc.page_count:
                pg = doc[pno - 1]
                try:
                    wm: Optional[SpatialWordMap] = SpatialWordMap.from_fitz_page(pg, pno)
                except Exception as exc:
                    logger.debug("field_locator: page %s word-map failed: %s", pno, exc)
                    wm = None
                cache[pno] = (wm, float(pg.rect.width), float(pg.rect.height))
            else:
                cache[pno] = (None, 0.0, 0.0)
        return cache[pno]

    stamped = 0
    found = 0
    try:
        for r in result_set.all_results():
            if not r.found or not r.value:
                continue
            found += 1
            if r.bbox:
                # An extractor already placed this field precisely (e.g. the comp
                # grid knows each comparable's exact cell) — never clobber it.
                continue
            located = _locate_one(r, doc.page_count, page)
            if located is None:
                continue
            pno, box = located
            r.bbox = box
            if not r.source_page:
                r.source_page = pno
            stamped += 1
    finally:
        doc.close()

    logger.info("Field locator: stamped %d/%d field boxes for %s",
                stamped, found, Path(str(pdf_path)).name)
    return stamped
