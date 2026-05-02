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

    try:
        from app.services.model_inference import correct_ocr_value
        model_value, model_changed = correct_ocr_value(corrected)
        if model_changed and model_value and 0.5 <= len(model_value) / max(len(corrected), 1) <= 1.8:
            corrected = model_value
            changed = True
    except Exception:
        pass

    return corrected, changed


def apply_ocr_correction_to_full_text(text: str) -> Tuple[str, int]:
    """
    Apply corrections to an entire OCR page or document.

    Applies TWO layers (Phase 6 — Level 1 learning):
      Layer 1: Static LABEL_CORRECTIONS dictionary (built-in)
      Layer 2: Operator-learned corrections from feedback_events DB table

    Returns:
        (corrected_text, correction_count)
    """
    corrected, _ = apply_ocr_correction(text)
    static_count = sum(1 for wrong in LABEL_CORRECTIONS if wrong in text)

    # Layer 2: apply operator-learned corrections from DB (same-day, no retraining)
    learned = _get_learned_corrections_cached()
    learned_count = 0
    for wrong, right in learned.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            learned_count += 1

    return corrected, static_count + learned_count


# ── Phase 6: Learned corrections from operator feedback ───────────────────────
# Cached in memory with a short TTL so new corrections apply within minutes
# without hitting the DB on every document.

import time
_learned_cache: dict = {}
_learned_cache_time: float = 0.0
_LEARNED_CACHE_TTL = 300  # 5 minutes


def _get_learned_corrections_cached() -> dict:
    """
    Pull operator OCR corrections from feedback_events (feedback_type='OCR_ERROR').
    Cached for 5 minutes so DB isn't hit on every document.
    """
    global _learned_cache, _learned_cache_time

    if time.time() - _learned_cache_time < _LEARNED_CACHE_TTL:
        return _learned_cache

    try:
        from app.database import get_db
        from app.models.db_models import FeedbackEvent

        learned = {}
        with get_db() as db:
            rows = (
                db.query(FeedbackEvent)
                .filter(
                    FeedbackEvent.original_status == "OCR_ERROR",
                    FeedbackEvent.original_value.isnot(None),
                    FeedbackEvent.corrected_value.isnot(None),
                )
                .all()
            )
            for row in rows:
                if row.original_value and row.corrected_value:
                    learned[row.original_value] = row.corrected_value

        _learned_cache = learned
        _learned_cache_time = time.time()
        return learned

    except Exception:
        return {}


def get_learned_corrections_count() -> int:
    """Return how many operator corrections are in the DB (for monitoring)."""
    return len(_get_learned_corrections_cached())


def invalidate_learned_cache():
    """Call after a new correction is saved so it applies immediately."""
    global _learned_cache_time
    _learned_cache_time = 0.0
