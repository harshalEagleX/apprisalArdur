"""
extraction/plausibility.py — step 8: type/range/format sanity per field.

SHALqc.md §3.2 step 8 / §3.3: "Value fails plausibility (garbage OCR) →
Suppressed → field = MISSING. Rule outcome: VERIFY, never FAIL." Column-based
and OCR-based extractors read a field by its position with no proof the value
*belongs* there — a 2-letter state code can land in `county`, a mailing zip in
a name field, an adjustment digit-bleed in a comp cell. This module is the
gate: it runs once, after merge, over the winning value per field, and
SUPPRESSES (never silently drops — the raw value survives in `raw_value`,
SHALqc.md P2) any value that is categorically impossible for its field.

Ported from ocr-service/app/extraction/field_validators.py, re-pointed at the
ExtractedField contract.

Scope, stated honestly: this catches type-confusion (values that CANNOT be
right for the field) at high precision. It does not catch a plausible-but-
wrong swap (e.g. appraised_value holding the contract_price) — that needs a
positive label anchor or a cross-field rule, not a range check.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, Optional

from app.extraction.result import ExtractedField

__version__ = "pla-1.0.0"

logger = logging.getLogger(__name__)

_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})
_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
_DIGITS_RE = re.compile(r"^[\d.,]+$")
_UAD_QUALITY = frozenset({"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"})
_UAD_CONDITION = frozenset({"C1", "C2", "C3", "C4", "C5", "C6"})

_MAX_SITE_ACRES = 250.0
_MAX_STRUCTURE_AGE = 150
_NET_ADJ_TOLERANCE = 5.0
_MAX_COMPS = 9


def _num(value: str) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _field_num(fields: Dict[str, ExtractedField], name: str) -> Optional[float]:
    r = fields.get(name)
    return _num(r.value) if (r and r.value is not None) else None


# ── Validators ─────────────────────────────────────────────────────────────
# validator(value, fields) -> True if PLAUSIBLE. Must only return False when
# the value is categorically impossible — a false positive here destroys
# correct data (SHALqc.md P4: doubt degrades to VERIFY, never invents a FAIL).

def _valid_county(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().upper().rstrip(".")
    if v in _US_STATES:
        return False
    if _DIGITS_RE.match(v):
        return False
    return True


def _valid_state(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().upper().rstrip(".")
    if _DIGITS_RE.match(v):
        return False
    if len(v) == 2:
        return v in _US_STATES
    return v.replace(" ", "").isalpha()


def _valid_real_estate_taxes(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    if n is None:
        return False
    return n >= 100


def _valid_total_rooms(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 1 <= n <= 30 and n == int(n)


def _valid_bedrooms(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 0 <= n <= 20 and n == int(n)


def _valid_appraised_value(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 10_000 <= n <= 100_000_000


def _valid_supervisory_name(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip()
    if not v:
        return False
    if _ZIP_RE.match(v) or _DIGITS_RE.match(v):
        return False
    return any(c.isalpha() for c in v)


def _valid_appraiser_email(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _valid_contract_price(value: str, fields: Dict[str, ExtractedField]) -> bool:
    # A label-proximity read of a BLANK contract cell on a refinance bleeds in
    # adjacent glyphs ("$", "Is"). A real contract price is a dollar amount in
    # the thousands — a value with no multi-digit number cannot be one.
    n = _num(value)
    return n is not None and n >= 1000


def _valid_contract_date(value: str, fields: Dict[str, ExtractedField]) -> bool:
    from app.normalize import dates
    return dates.parse_date(value) is not None


def _valid_concessions_amount(value: str, fields: Dict[str, ExtractedField]) -> bool:
    # Concessions are a dollar amount ($0 is valid — an explicit "no
    # concessions"). Non-numeric prose ("gift or downpayment") is a misread.
    return _num(value) is not None


def _valid_gla(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    if n is None:
        return False
    hoa = fields.get("hoa_monthly_assessment")
    if hoa and hoa.value:
        hoa_n = _num(hoa.value)
        if hoa_n is not None and abs(n - hoa_n) < 1:
            return False
    return 100 <= n <= 25000


def _valid_site_area(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().lower()
    m = re.match(r"[\d,]+(?:\.\d+)?", v)
    n = _num(m.group(0)) if m else None
    if n is None:
        return False
    if "ac" in v:
        unit = "ac"
    elif "sf" in v or "sq" in v:
        unit = "sf"
    else:
        sib = fields.get("site_area_unit")
        unit = (sib.value or "").lower() if sib else ""
    if unit.startswith("ac"):
        return 0.01 <= n <= _MAX_SITE_ACRES
    return 200 <= n <= 5_000_000


def _valid_comp_quality(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return value.strip().upper() in _UAD_QUALITY


def _valid_comp_condition(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return value.strip().upper() in _UAD_CONDITION


def _valid_comp_age(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 0 <= n <= _MAX_STRUCTURE_AGE and n == int(n)


def _comp_net_adjustment_validator(prefix: str) -> Callable[[str, Dict[str, ExtractedField]], bool]:
    """Assert the grid's own arithmetic identity for one comp:
    signed_net_adjustment == adjusted_sale_price - sale_price."""
    def _validate(value: str, fields: Dict[str, ExtractedField]) -> bool:
        sale = _field_num(fields, f"{prefix}_sale_price")
        adj = _field_num(fields, f"{prefix}_adjusted_sale_price")
        mag = _num(value)
        if sale is None or adj is None or mag is None:
            return True
        has_minus = value.strip().startswith("-")
        pos = fields.get(f"{prefix}_net_adj_positive")
        pos_v = (pos.value or "").strip().upper() if pos else ""
        if not has_minus and pos_v == "" and mag != 0:
            return True
        signed = -abs(mag) if (has_minus or pos_v == "N") else abs(mag)
        return abs((adj - sale) - signed) <= _NET_ADJ_TOLERANCE
    return _validate


_FIELD_VALIDATORS: Dict[str, Callable[[str, Dict[str, ExtractedField]], bool]] = {
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
    "contract_price":             _valid_contract_price,
    "contract_date":              _valid_contract_date,
    "concessions_amount":         _valid_concessions_amount,
}

for _pfx in ["subject_grid"] + [f"comp_{_i}" for _i in range(1, _MAX_COMPS + 1)]:
    _FIELD_VALIDATORS[f"{_pfx}_quality_rating"] = _valid_comp_quality
    _FIELD_VALIDATORS[f"{_pfx}_condition_rating"] = _valid_comp_condition
    _FIELD_VALIDATORS[f"{_pfx}_age"] = _valid_comp_age
for _i in range(1, _MAX_COMPS + 1):
    _FIELD_VALIDATORS[f"comp_{_i}_net_adjustment"] = _comp_net_adjustment_validator(f"comp_{_i}")
del _pfx, _i


def _suppress(result: ExtractedField, reason: str) -> None:
    """Reject an implausible value: raw value stays visible (P2), `found`
    flips to False so downstream rules see MISSING and degrade to VERIFY/NA,
    never a confident wrong verdict."""
    if not result.raw_value:
        result.raw_value = result.value
    result.suppressed = True
    result.suppression_reason = f"rejected as implausible {result.canonical_name}: {reason} (was '{result.value}')"


def validate_fields(merged: Dict[str, ExtractedField]) -> int:
    """Run every field validator over the merged fields in place.

    Returns the number of values suppressed (for report.degradations[] / P11).
    """
    suppressed = 0
    for fname, validator in _FIELD_VALIDATORS.items():
        ef = merged.get(fname)
        if ef is None or not ef.found:
            continue
        try:
            ok = validator(str(ef.value), merged)
        except Exception as exc:  # a buggy validator never breaks extraction (P6)
            logger.debug("Validator for %s raised %s — leaving value untouched", fname, exc)
            continue
        if not ok:
            logger.info("Plausibility rejected %s='%s'", fname, ef.value)
            _suppress(ef, "failed plausibility check")
            suppressed += 1
    return suppressed
