"""
locate.back_locator (loc-1.0.0) — SHALqc-CORE §3 "solving XML has no coordinates".

A value taken from XML has no page/bbox, so a reviewer clicking the finding
can't be scrolled to it. After merge, every field whose winning witness lacks a
bbox is located ON THE PDF and stamped with a `location_quality`:

  L1 exact  — the field already carries a bbox (a PDF/grid/checkbox witness)   → reuse
  L2 exact  — the normalized value is found as a contiguous token run on a page → tight box
  L4 page   — value not matched but the field HAS a page → scroll-to-page only
  L5 none   — value not matched and no page                                    → XML badge

(L3 region — highlight the label anchor + value region — needs the template map
`template_positions.yaml` from CORE §2, which is not built yet; until then an
unmatched value degrades L2→L4/L5 rather than L2→L3. This is a faithful subset:
no fabricated boxes, just honest downgrades.)

Matching is punctuation/whitespace-insensitive (so "$250,000.00" matches
"250000" and "77338" matches the zip on the page). The address-suffix case
("Mdw"↔"Meadow") needs the full normalizer and is a documented enhancement.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet

__version__ = "loc-1.0.0"

logger = logging.getLogger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_ROW_TOL = 4.0


def _norm(text: str) -> str:
    return _NON_ALNUM.sub("", (text or "").lower())


def _page_words(page) -> List[dict]:
    return [{"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "text": w[4]}
            for w in page.get_text("words") if w[4].strip()]


def _numeric(text: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _box(span, pw, ph) -> Dict[str, float]:
    x0 = min(w["x0"] for w in span); y0 = min(w["y0"] for w in span)
    x1 = max(w["x1"] for w in span); y1 = max(w["y1"] for w in span)
    return {"x": round(x0 / pw, 5), "y": round(y0 / ph, 5),
            "w": round((x1 - x0) / pw, 5), "h": round((y1 - y0) / ph, 5)}


def _locate_on_page(words: List[dict], target_norm: str, pw: float, ph: float,
                    target_num: Optional[float] = None) -> Optional[Dict[str, float]]:
    """Find `target_norm` as a contiguous run of words on one row (tolerant of
    $/comma/case). When the value is numeric, also match a single token by
    numeric equality so "$250,000.00" locates "250000". Returns a normalized
    {x,y,w,h} box (top-left origin) or None."""
    if pw <= 0 or ph <= 0:
        return None
    rows: Dict[int, List[dict]] = {}
    for w in words:
        rows.setdefault(round(w["y0"] / _ROW_TOL), []).append(w)
    for row in rows.values():
        row.sort(key=lambda w: w["x0"])
        # numeric single-token match first (robust to formatting)
        if target_num is not None:
            for w in row:
                wn = _numeric(w["text"])
                if wn is not None and (wn == target_num or (target_num and abs(wn - target_num) / abs(target_num) < 1e-6)):
                    return _box([w], pw, ph)
        if not target_norm:
            continue
        n = len(row)
        for i in range(n):
            acc = ""
            for j in range(i, n):
                acc += _norm(row[j]["text"])
                if len(acc) > len(target_norm):
                    break
                if acc == target_norm:
                    return _box(row[i:j + 1], pw, ph)
    return None


def _anchor_region(doc, page_no: int, anchor_text: str, max_pages: int) -> Optional[Dict[str, float]]:
    """Find a label anchor on its mapped page; return a soft region box just to
    the RIGHT of the label (where the URAR value sits). CORE §3 L3."""
    pages_to_try = [page_no] if 1 <= page_no <= len(doc) else range(1, min(max_pages, len(doc)) + 1)
    for pno in pages_to_try:
        page = doc[pno - 1]
        rects = page.search_for(anchor_text)
        if not rects:
            continue
        r = rects[0]
        pw, ph = float(page.rect.width), float(page.rect.height)
        # value region: from the label's right edge, ~40% page width, label height
        x0 = r.x1 + 2
        y0 = r.y0
        x1 = min(r.x1 + 0.40 * pw, pw)
        y1 = r.y1
        return {"x": round(x0 / pw, 5), "y": round(y0 / ph, 5),
                "w": round(max(x1 - x0, 10) / pw, 5), "h": round((y1 - y0) / ph, 5)}
    return None


def locate_fields(field_set: ExtractedFieldSet, pdf_path, max_pages: int = 12) -> Dict[str, int]:
    """Stamp page/bbox/location_quality on every located-poorly field in place.
    Returns a small histogram {exact, region, page, none} for the run log / the
    CORE §3 golden test ("≥90% of fields at exact")."""
    import fitz

    hist = {"exact": 0, "region": 0, "page": 0, "none": 0}

    # L1: fields that already carry a bbox are exact by construction.
    to_locate: List[ExtractedField] = []
    for _name, ef in field_set:
        if not ef.found:
            continue
        if ef.bbox is not None:
            ef.location_quality = "exact"
            hist["exact"] += 1
        else:
            to_locate.append(ef)

    if not to_locate:
        return hist

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("back_locator: cannot open %s: %s — leaving fields unlocated", pdf_path, exc)
        for ef in to_locate:
            ef.location_quality = "none" if ef.page == 0 else "page"
            hist["none" if ef.page == 0 else "page"] += 1
        return hist

    try:
        from app.extraction.template_positions import field_anchor
    except Exception:
        field_anchor = lambda *a, **k: None  # noqa: E731

    try:
        # cache each page's word list once
        pages = [(p, _page_words(p)) for p in [doc[i] for i in range(min(max_pages, len(doc)))]]
        for ef in to_locate:
            target = _norm(str(ef.value))
            target_num = _numeric(str(ef.value))
            found_box = None
            found_page = 0
            # L2: value found on a page (text or numeric). Short non-numeric
            # tokens (<3 chars) are too ambiguous to place — skip to avoid a
            # wrong box (P4 spirit).
            if target_num is not None or len(target) >= 3:
                for page, words in pages:
                    box = _locate_on_page(words, target, float(page.rect.width),
                                          float(page.rect.height), target_num=target_num)
                    if box is not None:
                        found_box, found_page = box, page.number + 1
                        break
            if found_box is not None:            # L1/L2 exact
                ef.bbox = found_box
                ef.page = found_page
                ef.location_quality = "exact"
                hist["exact"] += 1
                continue

            # L3: value not matched, but the field is in the template map →
            # find its label anchor on the mapped page → region box (soft box).
            anchor = field_anchor(ef.canonical_name)
            if anchor and anchor.get("anchor"):
                a_page = int(anchor.get("page", 1))
                region = _anchor_region(doc, a_page, anchor["anchor"], max_pages)
                if region is not None:
                    ef.bbox = region
                    ef.page = a_page
                    ef.location_quality = "region"
                    hist["region"] += 1
                    continue
                if 1 <= a_page <= len(doc):       # L4: mapped page, anchor missing
                    ef.page = a_page
                    ef.location_quality = "page"
                    hist["page"] += 1
                    continue

            if ef.page and ef.page > 0:           # L4 page-only (had a page already)
                ef.location_quality = "page"
                hist["page"] += 1
            else:                                 # L5 none (XML badge)
                ef.location_quality = "none"
                hist["none"] += 1
    finally:
        doc.close()

    logger.info("back_locator: %s", hist)
    return hist
