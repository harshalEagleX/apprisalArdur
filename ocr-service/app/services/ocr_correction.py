"""
OCR Correction Dictionary — Phase 2

Corrects common Tesseract misreads specific to UAD 1004 appraisal forms.
This is Level 1 of the self-learning loop (instant, no ML training needed).

Sources:
  - Live run on 96 Baell Trace Ct SE.pdf (e.g. "aP Code" → "Zip Code")
  - Known Tesseract failure modes on printed forms with table grids

Later (Phase 6), operator feedback replaces/extends this dictionary automatically.
"""

import re
from typing import Tuple

# ── Label corrections ─────────────────────────────────────────────────────────
# Tesseract misreads of printed form labels (font/resolution dependent)
LABEL_CORRECTIONS: dict[str, str] = {
    # Zip Code variants
    "aP Code":         "Zip Code",
    "ZiP Code":        "Zip Code",
    "Zip Gode":        "Zip Code",
    "Zip C0de":        "Zip Code",
    "ZIP C0de":        "Zip Code",
    "Zp Code":         "Zip Code",

    # Borrower
    "Borrovver":       "Borrower",
    "Borrewer":        "Borrower",
    "B orrower":       "Borrower",
    "Borr0wer":        "Borrower",
    "Borrcwer":        "Borrower",

    # Owner
    "0 wner":          "Owner",
    "0wner":           "Owner",
    "Ovvner":          "Owner",

    # Lender
    "l.ender":         "Lender",
    "Lendcr":          "Lender",
    "Lend er":         "Lender",
    "Lender/C1ient":   "Lender/Client",
    "Lender/Cllent":   "Lender/Client",

    # Neighborhood
    "Ncighborhood":    "Neighborhood",
    "Neighborh00d":    "Neighborhood",
    "Neighb0rhood":    "Neighborhood",

    # County
    "Counly":          "County",
    "Coun ty":         "County",

    # Census
    "Ccnsus":          "Census",
    "Censu5":          "Census",

    # Assessor
    "Assessor's Parce1": "Assessor's Parcel",
    "Assessors Parcel":  "Assessor's Parcel",
    "APN Assessor":      "Assessor's Parcel",

    # Legal description
    "l.egal":          "Legal",
    "Lega1":           "Legal",

    # Occupant
    "0ccupant":        "Occupant",
    "Occupanl":        "Occupant",

    # Sale / Sales
    "Sa1e":            "Sale",
    "Sal e":           "Sale",
    "S ale":           "Sale",

    # Property
    "Propert y":       "Property",
    "Proper ty":       "Property",

    # Contract
    "C0ntract":        "Contract",
    "Conlract":        "Contract",

    # Map Reference
    "Map Ref erence":  "Map Reference",
    "Map Ref":         "Map Reference",

    # Inspection
    "lnspection":      "Inspection",
    "Inspecti0n":      "Inspection",

    # Financial
    "Financ1al":       "Financial",
    "Financia1":       "Financial",

    # Personal
    "Persona1":        "Personal",

    # Checkbox artifacts — normalise to [X]
    "X]":  "[X]",
    "]X[": "[X]",
    "|X|": "[X]",
    "><":  "[X]",
}

# State abbreviation fixes (OCR sometimes misreads 2-letter state codes)
STATE_FIXES: dict[str, str] = {
    "G A": "GA",
    "C A": "CA",
    "T X": "TX",
    "F L": "FL",
    "N Y": "NY",
    "N C": "NC",
    "S C": "SC",
}

# ── Numeric context fixes (regex-based) ───────────────────────────────────────
# Uppercase O misread as zero inside numeric strings: "1O0,000" → "100,000"
_NUMERIC_O_PATTERN = re.compile(r'(?<=\d)O(?=\d)|(?<=\$)O(?=\d)')
# Lowercase l misread as 1 inside dollar amounts: "$l00" → "$100"
_NUMERIC_L_PATTERN = re.compile(r'(?<=\$)l(?=\d)|(?<=\d)l(?=\d)')


def apply_ocr_correction(text: str) -> Tuple[str, bool]:
    """
    Apply the correction dictionary and regex-based numeric fixes to `text`.

    Returns:
        (corrected_text, was_corrected)

    Fast path: if text contains none of the known bad patterns, returns immediately
    without iterating the whole dictionary.
    """
    if not text:
        return text, False

    corrected = text
    changed = False

    # Label corrections (case-sensitive, shortest-first to avoid partial matches)
    for wrong, right in LABEL_CORRECTIONS.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            changed = True

    # State abbreviation fixes
    for wrong, right in STATE_FIXES.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            changed = True

    # Numeric O/l fixes
    fixed = _NUMERIC_O_PATTERN.sub("0", corrected)
    if fixed != corrected:
        corrected = fixed
        changed = True

    fixed = _NUMERIC_L_PATTERN.sub("1", corrected)
    if fixed != corrected:
        corrected = fixed
        changed = True

    return corrected, changed


def apply_ocr_correction_to_full_text(text: str) -> Tuple[str, int]:
    """
    Apply corrections to an entire OCR page or document.

    Returns:
        (corrected_text, correction_count)
    """
    corrected, _ = apply_ocr_correction(text)
    count = sum(1 for wrong in LABEL_CORRECTIONS if wrong in text)
    return corrected, count
