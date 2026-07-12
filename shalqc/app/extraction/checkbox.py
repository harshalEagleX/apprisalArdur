"""
Checkbox extractor (part of extractor.pdf_digital's step, SHALqc.md §3.2 step 5).

Discovery: TOTAL-generated UAD PDFs mark a checked checkbox with a small
(~7x7pt) rectangle plus two crossing diagonal lines (an X) in the PDF drawings
layer — form widgets are empty on these PDFs, so the checkbox state lives
entirely in drawings, not in AcroForm fields.

Strategy: find every checked box via the X-mark/fill pattern, read the text
label immediately to its right (or, for left-labelled rows like Utilities,
immediately to its left), map that label to a canonical field + enum value via
the field schema's allowed_values vocabulary. Confidence fixed at 0.92 — this
is reading the actual drawn state, not inferring it.

Ported from ocr-service/app/ocr/checkbox_extractor.py, re-pointed at the
ExtractedField contract.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "chk-1.0.0"

logger = logging.getLogger(__name__)

_CHECKBOX_SIZE_MIN = 4.0
_CHECKBOX_SIZE_MAX = 12.0
_LABEL_SEARCH_X_RANGE = 120
_LABEL_ROW_TOLERANCE = 8.0
_DIAGONAL_TOLERANCE = 2.0
_CONF = 0.92

_OPTION_WORD_GAP = 18.0
_OPTION_MAX_WORDS = 3

# canonical value vocabulary the schema expects (SHALqc.md §3.2 step 5: "emit
# schema enum vocabulary — never raw True/False"). Utility presence is the one
# deliberate exception: field_schema has no dedicated Public/Private enum for
# utilities_*, so a boolean "True" is emitted there and is expected to be
# normalized against the schema's own allowed_values by normalize/normalizer.py.
_CHECKBOX_VALUE_TO_FIELD: Dict[str, Tuple[str, str]] = {
    "owner": ("occupant_status", "Owner"),
    "tenant": ("occupant_status", "Tenant"),
    "vacant": ("occupant_status", "Vacant"),
    "fee simple": ("property_rights", "Fee Simple"),
    "fee": ("property_rights", "Fee Simple"),
    "leasehold": ("property_rights", "Leasehold"),
    "de minimis": ("property_rights", "De Minimis PUD"),
    "purchase": ("assignment_type", "Purchase Transaction"),
    "refinance": ("assignment_type", "Refinance Transaction"),
    "did": ("did_analyze_contract", "True"),
    "did not": ("did_analyze_contract", "False"),
    "urban": ("location", "Urban"),
    "suburban": ("location", "Suburban"),
    "rural": ("location", "Rural"),
    "over 75%": ("built_up", "Over 75%"),
    "25-75%": ("built_up", "25-75%"),
    "under 25%": ("built_up", "Under 25%"),
    "rapid": ("growth_rate", "Rapid"),
    "stable": ("growth_rate", "Stable"),
    "slow": ("growth_rate", "Slow"),
    "increasing": ("property_values", "Increasing"),
    "declining": ("property_values", "Declining"),
    "shortage": ("demand_supply", "Shortage"),
    "in balance": ("demand_supply", "In Balance"),
    "over supply": ("demand_supply", "Over Supply"),
    "under 3": ("marketing_time", "Under 3 mths"),
    "3-6 mths": ("marketing_time", "3-6 mths"),
    "over 6": ("marketing_time", "Over 6 mths"),
    "legal": ("zoning_compliance", "Legal"),
    "legal nonconforming": ("zoning_compliance", "Legal Non-Conforming"),
    "legal non-conforming": ("zoning_compliance", "Legal Non-Conforming"),
    "no zoning": ("zoning_compliance", "No Zoning"),
    "illegal": ("zoning_compliance", "Illegal"),
    "existing": ("status", "Existing"),
    "proposed": ("status", "Proposed"),
    "under const": ("status", "Under Const."),
    "one": ("units_count", "One"),
    "det.": ("dwelling_type", "Det."),
    "att.": ("dwelling_type", "Att."),
    "s-det./end": ("dwelling_type", "S-Det./End Unit"),
    "concrete slab": ("foundation_type", "Concrete Slab"),
    "crawl space": ("foundation_type", "Crawl Space"),
    "full basement": ("foundation_type", "Full Basement"),
    "partial basement": ("foundation_type", "Partial Basement"),
}

_UTILITY_LEFT = {
    "electricity": "utilities_electricity", "electric": "utilities_electricity",
    "gas": "utilities_gas", "water": "utilities_water",
    "sewer": "utilities_sewer", "sanitary": "utilities_sewer",
}

_MIDDLE_COL_X = 190


def _is_diagonal_line(item) -> bool:
    if item[0] != "l":
        return False
    p1, p2 = item[1], item[2]
    return abs(p2.x - p1.x) > 2 and abs(p2.y - p1.y) > 2


def _checked_from_drawings(drawings: List[Dict]) -> List[Dict]:
    clusters: List[Dict] = []
    for d in drawings:
        r = d.get("rect")
        if r is None:
            continue
        if not (_CHECKBOX_SIZE_MIN <= r.width <= _CHECKBOX_SIZE_MAX and
                _CHECKBOX_SIZE_MIN <= r.height <= _CHECKBOX_SIZE_MAX):
            continue
        g = next((c for c in clusters
                  if abs(c["x"] - r.x0) <= _DIAGONAL_TOLERANCE and abs(c["y"] - r.y0) <= _DIAGONAL_TOLERANCE), None)
        if g is None:
            g = {"x": r.x0, "y": r.y0, "rect": False, "diag": 0, "lines": 0, "fill": False}
            clusters.append(g)
        if d.get("fill") is not None and d.get("type") in ("f", "fs"):
            g["fill"] = True
        for item in d.get("items", []):
            if item[0] == "re":
                g["rect"] = True
            elif item[0] == "l":
                g["lines"] += 1
                if _is_diagonal_line(item):
                    g["diag"] += 1

    checked: List[Dict] = []
    for g in clusters:
        if not g["rect"]:
            continue
        if g["diag"] >= 2 or g["lines"] >= 1 or g["fill"]:
            checked.append({"x": g["x"], "y": g["y"]})
    return checked


def find_checked_checkboxes(page) -> List[Dict]:
    return _checked_from_drawings(page.get_drawings())


def find_label_for_checkbox(checked_pos: Dict, sorted_words: List) -> Optional[str]:
    cx, cy = checked_pos["x"], checked_pos["y"]
    row = sorted(
        ((w[0], w[2], w[4]) for w in sorted_words
         if abs(w[1] - cy) < _LABEL_ROW_TOLERANCE and (cx - 4) < w[0] < cx + _LABEL_SEARCH_X_RANGE),
        key=lambda w: w[0])
    if not row:
        return None
    parts = [row[0][2]]
    prev_x1 = row[0][1]
    for x0, x1, txt in row[1:]:
        if len(parts) >= _OPTION_MAX_WORDS or (x0 - prev_x1) > _OPTION_WORD_GAP:
            break
        parts.append(txt)
        prev_x1 = x1
    return " ".join(parts).strip().rstrip(".,;:")


def find_row_label_left(checked_pos: Dict, sorted_words: List) -> Optional[str]:
    cx, cy = checked_pos["x"], checked_pos["y"]
    left = [w for w in sorted_words
            if abs(w[1] - cy) < _LABEL_ROW_TOLERANCE and w[0] < cx and (cx - w[0]) < 95]
    if not left:
        return None
    left.sort(key=lambda w: -w[0])
    return left[0][4].strip().rstrip(".,;:")


def map_label_to_field(label: Optional[str], checkbox_x: Optional[float] = None,
                        left_label: Optional[str] = None) -> Optional[Tuple[str, str]]:
    if not label and not left_label:
        return None
    label_lower = (label or "").lower().strip()

    if label_lower == "stable" and checkbox_x is not None:
        return (("property_values", "Stable") if checkbox_x >= _MIDDLE_COL_X
                else ("growth_rate", "Stable"))

    result = _CHECKBOX_VALUE_TO_FIELD.get(label_lower)
    if result is not None:
        return result

    best = None
    for key, mapping in _CHECKBOX_VALUE_TO_FIELD.items():
        if label_lower == key or label_lower.startswith(key + " "):
            if best is None or len(key) > len(best[0]):
                best = (key, mapping)
    if best is not None:
        return best[1]

    if left_label:
        util = _UTILITY_LEFT.get(left_label.lower().strip().rstrip(".,;:"))
        if util:
            return (util, "True")

    return None


def extract_page(page, page_number: int) -> Dict[str, ExtractedField]:
    results: Dict[str, ExtractedField] = {}
    checked = find_checked_checkboxes(page)
    if not checked:
        return results

    raw_words = page.get_text("words")
    sorted_words = sorted(raw_words, key=lambda w: (round(w[1] / 3) * 3, w[0]))
    pw, ph = float(page.rect.width), float(page.rect.height)

    for cb in checked:
        label = find_label_for_checkbox(cb, sorted_words)
        left_label = find_row_label_left(cb, sorted_words)
        if not label and not left_label:
            continue
        mapping = map_label_to_field(label, checkbox_x=cb.get("x"), left_label=left_label)
        if not mapping:
            continue
        field_name, value = mapping
        if field_name in results:
            continue  # first hit on this page wins

        bbox = None
        if pw > 0 and ph > 0:
            bbox = {"x": round(cb["x"] / pw, 5), "y": round(cb["y"] / ph, 5),
                    "w": round(10.0 / pw, 5), "h": round(10.0 / ph, 5)}

        results[field_name] = ExtractedField(
            canonical_name=field_name,
            value=value,
            raw_value=f"[Checkbox checked] {label or left_label or ''}".rstrip(),
            source=Source.CHECKBOX,
            confidence=_CONF,
            page=page_number,
            bbox=bbox,
        )
    return results


def extract_checkboxes(pdf_path, max_pages: int = 8) -> ExtractedFieldSet:
    """Extract checkbox values from the first `max_pages` pages of a PDF."""
    import fitz

    fs = ExtractedFieldSet()
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("checkbox: cannot open %s: %s", pdf_path, exc)
        return fs

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        if len(page.get_drawings()) < 10:
            continue  # skip narrative/text-only pages — no checkbox grid here
        for field_name, ef in extract_page(page, page_num + 1).items():
            if fs.get(field_name) is None:
                fs.add(ef)
    doc.close()

    logger.info("checkbox: %d fields found in %s", len(fs.found_fields()), pdf_path)
    return fs
