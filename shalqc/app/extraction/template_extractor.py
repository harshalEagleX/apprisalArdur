"""
extraction.template_extractor (tpl-1.1.0) — SHALqc-CORE §2 template-anchored pass.

Because the UAD 2.6 layout is fixed, for every template-mapped field the reader
goes straight to its label anchor on the known page and reads the value in the
region to the RIGHT of the label — no hunting. Each read carries the widget-tight
bbox (location_quality exact) and confidence 0.90.

Merged as a witness (below XML 0.97), so XML still wins every field it owns; the
template read's real payoff is (a) filling PDF-primary/MISSING fields and (b)
a tight bbox. Plausibility runs downstream, so a mis-read near a label is
suppressed rather than trusted (P4) — this pass can only help, never FAIL a rule.

STATUS (honest): this reader is NOT wired into merge.run_extraction yet. Runtime
anchor+read is unreliable until each field's precise value `region` is measured
from a GOLDEN BLANK FORM (CORE §2) — with only label anchors, a generic label
("effective date") matches prose and the row-read grabs the wrong text. The
mechanism is complete; it activates (add the field regions to
template_positions.yaml + call extract_template in merge) once the golden form
is supplied. Until then the back-locator uses these anchors for LOCATION only
(where a value is), which is robust; EXTRACTION stays with pdf_digital.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.extraction.template_positions import _load, detect_vendor

__version__ = "tpl-1.1.0"

logger = logging.getLogger(__name__)

_CONF = 0.90
_ROW_OVERLAP = 0.4      # fraction of label height a value word must overlap
_MAX_GAP = 60.0         # x-gap (pt) that ends a value cell


def _fields_for_vendor(vendor: str) -> Dict[str, dict]:
    vendors = _load().get("vendors") or {}
    base = dict((vendors.get("_default") or {}).get("fields") or {})
    over = (vendors.get(vendor) or {}).get("fields") or {} if vendor != "unknown" else {}
    base.update(over)
    return base


def _read_value_right(page, anchor_rect) -> Optional[tuple]:
    """Read the value words to the right of the anchor on the same row; return
    (text, normalized_bbox) or None."""
    pw, ph = float(page.rect.width), float(page.rect.height)
    ay0, ay1, ax1 = anchor_rect.y0, anchor_rect.y1, anchor_rect.x1
    ah = max(ay1 - ay0, 1.0)
    words = [w for w in page.get_text("words") if w[4].strip()]
    # words on the same row, to the right of the label
    row = []
    for x0, y0, x1, y1, txt, *_ in words:
        overlap = min(ay1, y1) - max(ay0, y0)
        if overlap / ah >= _ROW_OVERLAP and x0 >= ax1 - 1:
            row.append((x0, y0, x1, y1, txt))
    row.sort(key=lambda w: w[0])
    # collect until a big horizontal gap (next cell)
    picked = []
    prev_x1 = ax1
    for x0, y0, x1, y1, txt in row:
        if x0 - prev_x1 > _MAX_GAP and picked:
            break
        picked.append((x0, y0, x1, y1, txt))
        prev_x1 = x1
    if not picked:
        return None
    text = " ".join(w[4] for w in picked).strip()
    if not text:
        return None
    x0 = min(w[0] for w in picked); y0 = min(w[1] for w in picked)
    x1 = max(w[2] for w in picked); y1 = max(w[3] for w in picked)
    bbox = {"x": round(x0 / pw, 5), "y": round(y0 / ph, 5),
            "w": round((x1 - x0) / pw, 5), "h": round((y1 - y0) / ph, 5)}
    return text, bbox


def extract_template(pdf_path, vendor: Optional[str] = None) -> ExtractedFieldSet:
    """Template-anchored read of every mapped field. Empty set on any failure
    (P6 — never sinks the run)."""
    fs = ExtractedFieldSet()
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("template: cannot open %s: %s", pdf_path, exc)
        return fs
    try:
        v = vendor or detect_vendor(pdf_path)
        mapped = _fields_for_vendor(v)
        count = 0
        for field, entry in mapped.items():
            if field.endswith("2"):          # alias/dup anchors (e.g. neighborhood_name2)
                continue
            page_no = int(entry.get("page", 1))
            anchor = entry.get("anchor", "")
            if not anchor or not (1 <= page_no <= len(doc)):
                continue
            page = doc[page_no - 1]
            rects = page.search_for(anchor)
            if not rects:
                continue
            read = _read_value_right(page, rects[0])
            if read is None:
                continue
            text, bbox = read
            fs.add(ExtractedField(
                canonical_name=field, value=text, raw_value=text,
                source=Source.PDF_DIGITAL, confidence=_CONF,
                page=page_no, bbox=bbox, location_quality="exact"))
            count += 1
        if count:
            logger.info("template: read %d field(s) (vendor=%s)", count, v)
    finally:
        doc.close()
    return fs
