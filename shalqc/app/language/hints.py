"""
language.hints — the ~8 generic computed-hint functions (§4.1).

"computed_hints are the surviving useful part of machine observations — generic
arithmetic the code can always do without per-rule logic." There is NO per-rule
hint code, ever: these functions work over any set of bound labels, so a
count/sum/min/max/%/date-diff/equality check compiles for free for every AMC.

Each hint is `{hint, value, labels}` — the judge is told (prompt rule 4) to trust
these and only contradict one by quoting packet values.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.normalize import dates as _dates
from app.normalize.normalizer import match_band as _match_band

_NUMERIC_TYPES = frozenset({"integer", "number", "currency", "percent", "float"})

# PART 1.3: values that LOOK present but carry no positive/triggering content. A
# "field must not be blank" check is satisfied by any of these ONLY if the check
# wants mere presence; a "field triggers X" check must treat them as absent
# ($0 HOA dues is NOT "HOA dues present"). Surfaced to the judge as a hint.
_NULLISH = frozenset({
    "", "0", "0.0", "0.00", "$0", "$0.00", "n/a", "na", "none", "--", "-", "0%", "tbd"})


def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    s = re.sub(r"\s+", " ", str(v)).strip().lower()
    if s in _NULLISH:
        return True
    num = re.sub(r"[,$%\s]", "", s)          # a currency/number that reduces to zero
    try:
        return float(num) == 0.0
    except ValueError:
        return False


def _xdoc_kind(label: str) -> str:
    """PART 1.2: the comparison kind for a cross-document label (its
    engagement./contract. prefix stripped), so match_band normalizes correctly."""
    n = label.split(".", 1)[-1].lower()
    if "address" in n or "street" in n or n in ("city", "state", "zip", "zip_code"):
        return "address"
    if "phone" in n:
        return "phone"
    if "email" in n:
        return "email"
    if "company" in n or "lender" in n or "client" in n or "amc" in n:
        return "company"
    if "borrower" in n or "seller" in n or "owner" in n or n in ("appraiser_name",):
        return "person"
    if "transaction_type" in n or "loan_program" in n or "assignment" in n or "purpose" in n:
        return "enum"
    if "form" in n or "product" in n:
        return "form"
    return "generic"


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _nums(values: Dict[str, Any], labels: List[str]) -> List[float]:
    out = []
    for lbl in labels:
        n = _num(values.get(lbl))
        if n is not None:
            out.append(n)
    return out


# ── the generic hint functions ───────────────────────────────────────────────

def count_present(values: Dict[str, Any], labels: List[str]) -> int:
    return sum(1 for lbl in labels if values.get(lbl) not in (None, ""))


def comp_count_present(values: Dict[str, Any]) -> int:
    """Number of comparables actually present — the anchor for count-style checks
    at any N (§7 S-10). A comp is 'present' if it has a sale price."""
    n = 0
    for i in range(1, 13):
        if values.get(f"comp_{i}_sale_price") not in (None, ""):
            n += 1
    return n


def sum_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return round(sum(ns), 4) if ns else None


def min_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return min(ns) if ns else None


def max_of(values: Dict[str, Any], labels: List[str]) -> Optional[float]:
    ns = _nums(values, labels)
    return max(ns) if ns else None


def pct_of(values: Dict[str, Any], numer: str, denom: str) -> Optional[float]:
    a, b = _num(values.get(numer)), _num(values.get(denom))
    if a is None or not b:
        return None
    return round(a / b * 100.0, 3)


def date_diff_days(values: Dict[str, Any], a: str, b: str) -> Optional[int]:
    da, db = _dates.parse_date(str(values.get(a) or "")), _dates.parse_date(str(values.get(b) or ""))
    if not da or not db:
        return None
    return abs((da - db).days)


def _numeric_family(label: str) -> Optional[str]:
    """The comp_N-collapsed schema attribute this label is, iff the schema says
    it is actually numeric-typed — None otherwise (excludes it from sum/min/max
    entirely). Two labels are commensurable (safe to sum/min/max together) only
    when they reduce to the SAME family: comp_1_sale_price..comp_7_sale_price
    are the same attribute repeated across comps (the intended §7 S-10 use);
    contract_price + year_built, or a quality-rating code + a dollar
    adjustment, are not — they only look numeric because a regex found digits
    somewhere in the string (2026-07-13 dry-run cause #5: sums that silently
    added quality-rating codes to dollar adjustments, and street numbers to
    census tracts, then had the validator penalize a correct judge answer for
    disagreeing with the resulting nonsense)."""
    from app.extraction.schema import schema_loader
    from app.language.label_dictionary import canonical_label

    family = canonical_label(label)
    fd = schema_loader.get_field(family)
    if fd is None or fd.data_type not in _NUMERIC_TYPES:
        return None
    return family


def equal_after_norm(values: Dict[str, Any], a: str, b: str) -> Optional[bool]:
    va, vb = values.get(a), values.get(b)
    if va is None or vb is None:
        return None
    na = re.sub(r"[^a-z0-9]+", "", str(va).lower())
    nb = re.sub(r"[^a-z0-9]+", "", str(vb).lower())
    if not na or not nb:
        return None
    return na == nb or na in nb or nb in na


# ── driver: compute the always-safe hint set for a packet ────────────────────

def compute_hints(values: Dict[str, Any], bound_labels: List[str],
                  expects: str = "", comp_count: Optional[int] = None) -> List[Dict[str, Any]]:
    """Every hint we can safely derive for this item. `comp_count_present` is
    ALWAYS included so count-style checks work at any N. Numeric aggregates are
    added when ≥2 bound labels carry numbers; a date-diff when exactly two bound
    labels are dates; an equality when `expects` hints at a comparison.

    `comp_count` overrides the comp tally when the caller knows it from the full
    report (the packet's bound labels may not include comp_*_sale_price)."""
    present = [lbl for lbl in bound_labels if values.get(lbl) not in (None, "")]
    cc = comp_count if comp_count is not None else comp_count_present(values)
    hints: List[Dict[str, Any]] = [
        {"hint": "comp_count_present", "value": cc, "labels": []},
        {"hint": "count(bound labels present)", "value": len(present), "labels": present},
    ]

    # sum/min/max: only across labels that are (a) schema-numeric-typed, not
    # just regex-parseable, and (b) all the SAME attribute (e.g. every present
    # comp's sale price) — see _numeric_family. One aggregate block per family
    # that actually has 2+ members; unrelated numeric fields never mix.
    families: Dict[str, List[str]] = {}
    for lbl in bound_labels:
        if _num(values.get(lbl)) is None:
            continue
        fam = _numeric_family(lbl)
        if fam is not None:
            families.setdefault(fam, []).append(lbl)
    for fam, numeric_labels in families.items():
        if len(numeric_labels) < 2:
            continue
        suffix = f" ({fam})" if len(families) > 1 else ""
        hints.append({"hint": f"sum{suffix}", "value": sum_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": f"min{suffix}", "value": min_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": f"max{suffix}", "value": max_of(values, numeric_labels), "labels": numeric_labels})

    date_labels = [lbl for lbl in bound_labels
                   if _dates.parse_date(str(values.get(lbl) or ""))]
    if len(date_labels) == 2:
        dd = date_diff_days(values, date_labels[0], date_labels[1])
        if dd is not None:
            hints.append({"hint": "date_diff_days", "value": dd, "labels": date_labels})

    # PART 1.3: present-looking values that are actually nullish ($0/N/A/blank).
    # The judge is told (doctrine) to treat these as NOT present for a presence
    # check — the fix for EQ-11 ("hoa_dues $0" was read as "HOA present").
    nullish = [lbl for lbl in present if _is_nullish(values.get(lbl))]
    if nullish:
        hints.append({"hint": "nullish_values (present but $0/N/A/blank)",
                      "value": nullish, "labels": nullish})

    # PART 1.2: a NORMALIZED cross-document comparison, so a trailing comma, a
    # corporate suffix, ZIP+4, or "Refinance Transaction" vs "Refinance" can no
    # longer read as a mismatch. Fires ONLY for a genuine cross-document PAIR — an
    # engagement./contract.-prefixed label AND its same-named appraisal counterpart.
    # (It must never compare two unrelated same-document fields, e.g. heating vs
    # air_conditioning — that produced a false "mismatch" reject on EQ-72.)
    for lbl in present:
        if not lbl.startswith(("engagement.", "contract.")):
            continue
        base = lbl.split(".", 1)[1]
        if base not in values or values.get(base) is None:
            continue
        kind = _xdoc_kind(base)
        band = _match_band(values.get(base), values.get(lbl), kind)
        hints.append({"hint": f"normalized_match ({kind}): {band}",
                      "value": band, "labels": [base, lbl]})

    return hints
