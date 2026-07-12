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

    numeric_labels = [lbl for lbl in bound_labels if _num(values.get(lbl)) is not None]
    if len(numeric_labels) >= 2:
        hints.append({"hint": "sum", "value": sum_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": "min", "value": min_of(values, numeric_labels), "labels": numeric_labels})
        hints.append({"hint": "max", "value": max_of(values, numeric_labels), "labels": numeric_labels})

    date_labels = [lbl for lbl in bound_labels
                   if _dates.parse_date(str(values.get(lbl) or ""))]
    if len(date_labels) == 2:
        dd = date_diff_days(values, date_labels[0], date_labels[1])
        if dd is not None:
            hints.append({"hint": "date_diff_days", "value": dd, "labels": date_labels})

    # equality: only when the check text/expects reads like a match, and exactly
    # two non-comp labels are bound (cross-document / cross-section agreement).
    non_comp = [lbl for lbl in present if not lbl.startswith("comp_")]
    if len(non_comp) == 2 and re.search(r"match|agree|same|consisten|equal", expects or "", re.I):
        eq = equal_after_norm(values, non_comp[0], non_comp[1])
        if eq is not None:
            hints.append({"hint": "equal_after_norm", "value": eq, "labels": non_comp})

    return hints
