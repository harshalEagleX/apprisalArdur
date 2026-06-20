"""Per-field plausibility validators — extraction layer (post-merge gate).

The positional/column extractors (l5_uad_template, spatial_extractor) read a field
by its location on the form with no proof that the value *belongs* to that field.
When a column boundary is off or an adjacent cell bleeds in, an implausible value
wins the merge with high confidence — a 2-letter state code lands in `county`, a
mailing-address zip lands in `supervisory_appraiser_name`, an APN prefix lands in
`real_estate_taxes`. Demoting confidence is not enough: `DocView.value()` returns
any `found` value regardless of confidence, so the rule still reads the wrong data.

This module is the missing "positional extraction *with* plausibility validation"
half called for in CLAUDE.md §17. It runs once, after the orchestrator merge, over
the winning result per field. When a winner is implausible for its field, the value
is SUPPRESSED — moved into `raw_source_text` (P-5: raw input preserved for debugging
and training) and `value` set to None so the field reads as NOT_FOUND. The rule then
receives a data-missing signal and degrades to VERIFY/EXTRACTION_FAILED (P-6) instead
of asserting a confident wrong PASS/FAIL.

Scope (be honest about what this can and cannot do, P-1 Level-2):
  • CATCHES the type-confusion class — values that are categorically impossible for
    the field (state code in county, zip in a name, APN fragment in taxes). High
    precision: a validator only fires when the value *cannot* be right, never on a
    merely-unusual-but-possible value.
  • Does NOT catch plausible-but-wrong swaps (appraised_value=contract_price,
    total_rooms read as the bedroom count). Both candidates pass a range check.
    Those need a positive label anchor / cross-field check — see _CROSS_FIELD_TODO.

Validators are declarative and live here as config (P-4): adding a new guard is a
one-line entry, never a change to the merge code.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, Optional

from app.core.result import ExtractionResult

logger = logging.getLogger(__name__)

# Two-letter USPS state codes — a county value that equals one of these is the
# state field having leaked one column to the left.
_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})

_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
_DIGITS_RE = re.compile(r"^[\d.,]+$")


def _num(value: str) -> Optional[float]:
    """Parse a currency/number-ish string to float, or None if it isn't numeric."""
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


# ── Validators ─────────────────────────────────────────────────────────────
# Contract: validator(value, fields) -> True if PLAUSIBLE for the field.
# `fields` is the full merged {name: ExtractionResult} so a validator may read a
# sibling field (e.g. site_area needs site_area_unit). A validator must only
# return False when the value is categorically impossible — never on a value that
# is merely uncommon. False positives here destroy correct data.

def _valid_county(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    v = value.strip().upper().rstrip(".")
    if v in _US_STATES:          # "TN" → the state field leaked in
        return False
    if _DIGITS_RE.match(v):      # a county is never purely numeric
        return False
    return True


def _valid_state(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    v = value.strip().upper().rstrip(".")
    # Accept a 2-letter USPS code or a longer alphabetic full name; reject digits.
    if _DIGITS_RE.match(v):
        return False
    if len(v) == 2:
        return v in _US_STATES
    return v.replace(" ", "").isalpha()


def _valid_real_estate_taxes(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    n = _num(value)
    if n is None:
        return False
    # An APN fragment ("065" → 65) or a stray digit reads as a tiny number. Annual
    # RE taxes on a financeable property are effectively never below ~$100.
    return n >= 100


def _valid_total_rooms(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    n = _num(value)
    return n is not None and 1 <= n <= 30 and n == int(n)


def _valid_bedrooms(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    n = _num(value)
    return n is not None and 0 <= n <= 20 and n == int(n)


def _valid_appraised_value(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    # Range only — this CANNOT distinguish appraised_value from contract_price when
    # both are plausible dollar amounts. The real fix is the signature-page label
    # anchor in spatial_extractor; this just rejects garbage.
    n = _num(value)
    return n is not None and 10_000 <= n <= 100_000_000


def _valid_supervisory_name(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    v = value.strip()
    if not v:
        return False
    if _ZIP_RE.match(v) or _DIGITS_RE.match(v):   # "24319" — a mailing-address zip
        return False
    return any(c.isalpha() for c in v)


def _valid_appraiser_email(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _valid_gla(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    # Cross-field safety net for the 1073 condo bug where the HOA monthly
    # assessment ("$635") is misread as GLA. If GLA exactly equals the extracted
    # HOA monthly assessment, it is almost certainly the fee, not living area.
    # (The positional fix in l5_uad_template is primary; this is defence in depth.)
    n = _num(value)
    if n is None:
        return False
    hoa = fields.get("hoa_monthly_assessment")
    if hoa and hoa.value:
        hoa_n = _num(hoa.value)
        if hoa_n is not None and abs(n - hoa_n) < 1:
            return False
    return 100 <= n <= 25000


def _valid_site_area(value: str, fields: Dict[str, ExtractionResult]) -> bool:
    n = _num(value)
    if n is None:
        return False
    unit = (fields.get("site_area_unit").value or "").lower() if fields.get("site_area_unit") else ""
    if unit.startswith("ac"):                     # acres
        return 0.01 <= n <= _MAX_SITE_ACRES
    return 200 <= n <= 5_000_000                   # square feet


# Tunables (P-4) — a business analyst can widen these without touching logic.
_MAX_SITE_ACRES = 250.0


_FIELD_VALIDATORS: Dict[str, Callable[[str, Dict[str, ExtractionResult]], bool]] = {
    "county":                     _valid_county,
    "state":                      _valid_state,
    "gla":                        _valid_gla,
    "real_estate_taxes":          _valid_real_estate_taxes,
    "total_rooms":                _valid_total_rooms,
    "bedrooms":                   _valid_bedrooms,
    "appraised_value":            _valid_appraised_value,
    "supervisory_appraiser_name": _valid_supervisory_name,
    "appraiser_email":            _valid_appraiser_email,
    "site_area":                  _valid_site_area,
}

# Plausible-but-wrong swaps a range check can't see — documented so they are not
# mistaken for "covered". Each needs a positive anchor or a cross-field rule.
_CROSS_FIELD_TODO = (
    "appraised_value vs contract_price (needs signature-page label anchor)",
    "total_rooms vs bedrooms (needs total_rooms >= bedrooms cross-check)",
)


def _suppress(result: ExtractionResult, reason: str) -> None:
    """Reject an implausible value: preserve the raw text (P-5), null the value so
    the field reads NOT_FOUND (P-6), and record why for the reviewer (P-10)."""
    if not result.raw_source_text:
        result.raw_source_text = result.value
    result.sanity_check_failed = True
    result.sanity_check_reason = f"rejected as implausible {result.canonical_name}: {reason} (was '{result.value}')"
    result.value = None


def validate_results(merged: Dict[str, ExtractionResult]) -> int:
    """Run every field validator over the merged results in place.

    Returns the number of values suppressed (for the orchestrator log / P-11).
    """
    suppressed = 0
    for fname, validator in _FIELD_VALIDATORS.items():
        result = merged.get(fname)
        if result is None or not result.found:
            continue
        try:
            ok = validator(str(result.value), merged)
        except Exception as exc:                  # a buggy validator never breaks extraction (P-6)
            logger.debug("Validator for %s raised %s — leaving value untouched", fname, exc)
            continue
        if not ok:
            logger.info("Field validator rejected %s='%s'", fname, result.value)
            _suppress(result, "failed plausibility check")
            suppressed += 1
    return suppressed
