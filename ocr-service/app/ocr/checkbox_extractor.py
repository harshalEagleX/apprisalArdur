"""
Checkbox Extractor — PDF Drawings Layer Analysis

Discovery (from real document inspection):
  TOTAL appraisal software (a la mode) marks checked checkboxes with:
  1. A small rectangle (~7x7 pixels) for the checkbox border
  2. Two crossing diagonal lines (an X mark) inside the rectangle

  Checked: rect + line(top-left→bottom-right) + line(top-right→bottom-left)
  Unchecked: rect only

  PyMuPDF form widgets are empty on these PDFs — the checkbox state is
  entirely in the drawings layer, not in widget fields.

This extractor:
  1. Finds all checked checkbox positions via the X-mark pattern
  2. Finds the text label to the RIGHT of each checked checkbox
  3. Maps the label to a known field by comparing to the field schema

Tested on: MSL (GA), Equity Solutions (FL/TX/WV), Orders/ (multiple states).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import fitz

from app.core.result import ExtractionMethod, ExtractionResult
from app.core.schema import FieldDefinition, schema_loader

logger = logging.getLogger(__name__)

_CHECKBOX_SIZE_MIN = 4.0    # minimum px for a valid checkbox
_CHECKBOX_SIZE_MAX = 12.0   # maximum px for a valid checkbox
_LABEL_SEARCH_X_RANGE = 120 # search this far to the right for the label
_LABEL_ROW_TOLERANCE = 8.0  # Y tolerance for same-row label matching
_DIAGONAL_TOLERANCE = 2.0   # how close two diagonal lines must be to form an X

# Confidence for checkbox extraction (high — this is reading the actual drawing state)
_CHECKBOX_CONFIDENCE = 0.92


def _is_diagonal_line(item) -> bool:
    """True if the path item is a diagonal line (not horizontal/vertical)."""
    if item[0] != 'l':
        return False
    p1, p2 = item[1], item[2]
    dx = abs(p2.x - p1.x)
    dy = abs(p2.y - p1.y)
    return dx > 2 and dy > 2   # has both horizontal and vertical components


def find_checked_checkboxes(page: fitz.Page) -> List[Dict]:
    """
    Find all checked checkboxes on a page.
    Returns list of {x, y, w, h} for each checked checkbox.

    A checked checkbox = a small rect + two diagonal crossing lines inside it.
    """
    drawings = page.get_drawings()

    # Group drawings by position (rounded to 1dp)
    pos_groups: Dict[Tuple, List] = defaultdict(list)
    for d in drawings:
        r = d.get('rect')
        if r is None:
            continue
        w, h = r.width, r.height
        if not (_CHECKBOX_SIZE_MIN <= w <= _CHECKBOX_SIZE_MAX and
                _CHECKBOX_SIZE_MIN <= h <= _CHECKBOX_SIZE_MAX):
            continue
        key = (round(r.x0, 1), round(r.y0, 1))
        pos_groups[key].append(d)

    checked: List[Dict] = []
    for (x0, y0), draws in pos_groups.items():
        # Count: rectangles and diagonal lines
        has_rect = False
        diagonal_count = 0
        for d in draws:
            items = d.get('items', [])
            for item in items:
                if item[0] == 're':
                    has_rect = True
                elif _is_diagonal_line(item):
                    diagonal_count += 1

        if has_rect and diagonal_count >= 2:
            # This checkbox has an X mark → CHECKED
            checked.append({'x': x0, 'y': y0})
            logger.debug("Checked checkbox at (%.1f, %.1f)", x0, y0)

    return checked


_OPTION_WORD_GAP = 18.0   # stop collecting the label at a gap wider than this (next column)
_OPTION_MAX_WORDS = 3     # multi-word options: "In Balance", "Under 3 mths"


def find_label_for_checkbox(
    checked_pos: Dict,
    sorted_words: List,
) -> Optional[str]:
    """
    Find the option label to the RIGHT of a checked checkbox, on the same row.

    URAR options are often multi-word ("In Balance", "Over Supply", "Under 3
    mths"), so collect up to _OPTION_MAX_WORDS consecutive words, stopping at a
    wide x-gap (the next box/column). Returning only the first word lost these.
    """
    cx, cy = checked_pos['x'], checked_pos['y']
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
    """Nearest word to the LEFT of the box on the same row — the row label for
    left-labelled rows (e.g. Utilities: "Electricity ☐ ☐")."""
    cx, cy = checked_pos['x'], checked_pos['y']
    left = [w for w in sorted_words
            if abs(w[1] - cy) < _LABEL_ROW_TOLERANCE and w[0] < cx and (cx - w[0]) < 95]
    if not left:
        return None
    left.sort(key=lambda w: -w[0])
    return left[0][4].strip().rstrip(".,;:")


# Left-labelled rows: the row label sits to the LEFT of its checked box.
# Utilities (ST-7) — a checked Public/Other box on the row => utility present.
_UTILITY_LEFT = {
    "electricity": "utilities_electricity", "electric": "utilities_electricity",
    "gas": "utilities_gas", "water": "utilities_water",
    "sewer": "utilities_sewer", "sanitary": "utilities_sewer",
}


def map_label_to_field(label: str, doc_type: str,
                       checkbox_x: Optional[float] = None,
                       left_label: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    Map a checked label text to (canonical_field_name, canonical_value).
    Uses the field schema's allowed_values to find the matching field.
    Returns (field_name, value) or None if no match.

    checkbox_x disambiguates options whose words appear in more than one field.
    On the URAR neighborhood block the LEFT column (Location/Built-Up/Growth)
    sits at x<~190 and the MIDDLE column (Property Values/Demand/Marketing) at
    x>=~190 — e.g. "Stable" belongs to growth_rate on the left but to
    property_values in the middle. left_label carries the row label to the LEFT
    of the box, used for left-labelled rows (utilities).
    """
    if not label and not left_label:
        return None

    label_lower = (label or "").lower().strip()

    # Position-disambiguated options (word shared across two fields by column).
    _MIDDLE_COL_X = 190
    if label_lower == "stable" and checkbox_x is not None:
        return (("property_values", "Stable") if checkbox_x >= _MIDDLE_COL_X
                else ("growth_rate", "Stable"))

    # Mapping of known checkbox values to field names
    # Built from QC Checklist rules + real document observation
    CHECKBOX_VALUE_TO_FIELD = {
        # Occupant Status (S-7)
        "owner": ("occupant_status", "Owner"),
        "tenant": ("occupant_status", "Tenant"),
        "vacant": ("occupant_status", "Vacant"),
        # Property Rights (S-11)
        "fee simple": ("property_rights", "Fee Simple"),
        "fee": ("property_rights", "Fee Simple"),
        "leasehold": ("property_rights", "Leasehold"),
        "de minimis": ("property_rights", "De Minimis PUD"),
        # Assignment Type (C-1)
        "purchase": ("assignment_type", "Purchase Transaction"),
        "refinance": ("assignment_type", "Refinance Transaction"),
        # Did Analyze Contract (C-1)
        "did": ("did_analyze_contract", "True"),
        "did not": ("did_analyze_contract", "False"),
        # Seller Owner of Record (C-3)
        "yes": None,   # ambiguous — need context (see below)
        "no": None,    # ambiguous — need context
        # Location (N-1)
        "urban": ("location", "Urban"),
        "suburban": ("location", "Suburban"),
        "rural": ("location", "Rural"),
        # Built Up (N-1)
        "over 75%": ("built_up", "Over 75%"),
        "25-75%": ("built_up", "25-75%"),
        "under 25%": ("built_up", "Under 25%"),
        # Growth (N-1)
        "rapid": ("growth_rate", "Rapid"),
        "stable": ("growth_rate", "Stable"),
        "slow": ("growth_rate", "Slow"),
        # Property Values (N-2)
        "increasing": ("property_values", "Increasing"),
        "declining": ("property_values", "Declining"),
        # Demand/Supply (N-2)
        "shortage": ("demand_supply", "Shortage"),
        "in balance": ("demand_supply", "In Balance"),
        "over supply": ("demand_supply", "Over Supply"),
        # Marketing Time (N-2)
        "under 3": ("marketing_time", "Under 3 mths"),
        "3-6 mths": ("marketing_time", "3-6 mths"),
        "over 6": ("marketing_time", "Over 6 mths"),
        # Zoning Compliance (ST-5)
        "legal": ("zoning_compliance", "Legal"),
        "legal nonconforming": ("zoning_compliance", "Legal Non-Conforming"),
        "legal non-conforming": ("zoning_compliance", "Legal Non-Conforming"),
        "no zoning": ("zoning_compliance", "No Zoning"),
        "illegal": ("zoning_compliance", "Illegal"),
        # Highest and Best Use (ST-6)
        # HBU "yes" is checked = True (existing use = HBU)
        # Utilities (ST-7)
        "electricity": ("utilities_electricity", "True"),
        "electric": ("utilities_electricity", "True"),
        "gas": ("utilities_gas", "True"),
        "water": ("utilities_water", "True"),
        "sanitary sewer": ("utilities_sewer", "True"),
        "sewer": ("utilities_sewer", "True"),
        # FEMA (ST-8)
        "fema": None,  # context-dependent
        # Status (improvements)
        "existing": ("status", "Existing"),
        "proposed": ("status", "Proposed"),
        "under const": ("status", "Under Const."),
        # Units
        "one": ("units_count", "One"),
        "det.": ("dwelling_type", "Det."),
        "att.": ("dwelling_type", "Att."),
        "s-det./end": ("dwelling_type", "S-Det./End Unit"),
        # Foundation
        "concrete slab": ("foundation_type", "Concrete Slab"),
        "crawl space": ("foundation_type", "Crawl Space"),
        "full basement": ("foundation_type", "Full Basement"),
        "partial basement": ("foundation_type", "Partial Basement"),
    }

    result = CHECKBOX_VALUE_TO_FIELD.get(label_lower)
    if result is not None:
        return result

    # Token-prefix match: a key whose words START the (possibly multi-word) label
    # — "in balance"/"over supply"/"under 3 mths". Replaces the old substring
    # fallback, which mis-matched short labels (e.g. "in" -> "de mINimis").
    best = None
    for key, mapping in CHECKBOX_VALUE_TO_FIELD.items():
        if mapping and (label_lower == key or label_lower.startswith(key + " ")):
            if best is None or len(key) > len(best[0]):
                best = (key, mapping)
    if best is not None:
        return best[1]

    # Left-labelled utility row: a checked Public/Other box => utility present.
    if left_label:
        util = _UTILITY_LEFT.get(left_label.lower().strip().rstrip(".,;:"))
        if util:
            return (util, "True")

    return None


class CheckboxExtractor:
    """
    Extract enum/boolean field values from PDF drawing-layer checkboxes.
    This is the correct approach for UAD forms generated by TOTAL software.

    Works on digital PDFs only — scanned docs need vision-based checkbox detection.
    """

    def extract_page(
        self,
        page: fitz.Page,
        page_number: int,
        document_type: str,
    ) -> Dict[str, ExtractionResult]:
        """
        Extract all checked checkbox values from a single page.
        Returns {canonical_field_name: ExtractionResult}.
        """
        results: Dict[str, ExtractionResult] = {}

        checked = find_checked_checkboxes(page)
        if not checked:
            return results

        # Get sorted words for label lookup
        raw_words = page.get_text('words')
        sorted_words = sorted(raw_words, key=lambda w: (round(w[1] / 3) * 3, w[0]))

        for cb in checked:
            label = find_label_for_checkbox(cb, sorted_words)
            left_label = find_row_label_left(cb, sorted_words)
            if not label and not left_label:
                continue

            mapping = map_label_to_field(label, document_type,
                                         checkbox_x=cb.get('x'), left_label=left_label)
            if not mapping:
                continue

            field_name, value = mapping

            # If the same field was already found on this page, keep the first
            if field_name in results and results[field_name].found:
                continue

            source_text = f"[Checkbox checked] {label or left_label or ''}".rstrip()
            results[field_name] = ExtractionResult(
                canonical_name=field_name,
                document_type=document_type,
                value=value,
                raw_source_text=source_text,
                extraction_method="checkbox_drawing_detection",
                confidence=_CHECKBOX_CONFIDENCE,
                source_page=page_number,
                normalization_applied=["checkbox_to_enum"],
            )
            logger.debug(
                "Checkbox: %s=%r from label=%r (p%d)",
                field_name, value, label, page_number,
            )

        return results

    def extract_document(
        self,
        pdf_path,
        document_type: str,
        max_pages: int = 8,
    ) -> Dict[str, ExtractionResult]:
        """
        Extract checkbox values from the first max_pages pages of a PDF.
        Main form content is on pages 1-8 for most appraisal formats.
        """
        all_results: Dict[str, ExtractionResult] = {}

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as exc:
            logger.warning("Cannot open PDF for checkbox extraction: %s", exc)
            return {}

        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            # Only process pages with drawings (skip narrative/text-only pages)
            if len(page.get_drawings()) < 10:
                continue

            page_results = self.extract_page(page, page_num + 1, document_type)
            for fname, result in page_results.items():
                if fname not in all_results or not all_results[fname].found:
                    all_results[fname] = result

        doc.close()

        found = [f for f, r in all_results.items() if r.found]
        logger.info(
            "Checkbox extraction: %s | found %d fields: %s",
            pdf_path, len(found), found[:10],
        )
        return all_results


# Module-level singleton
checkbox_extractor = CheckboxExtractor()
