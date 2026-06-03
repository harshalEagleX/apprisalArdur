"""
Comparable sales-grid extractor — per-comparable columns.

The URAR Sales Comparison grid is a true table: a label column on the left, a
SUBJECT column, then COMPARABLE SALE 1..3 columns (4..6 continue on a second
grid page). Each comparable column is split into a VALUE (left) and an
ADJUSTMENT (right). The generic spatial/Camelot extraction mangles this (it put
the GLA *adjustment* into comp_N_gla and produced one merged comp_N_* value),
which blocks the per-comparable SCA rules.

This extractor reconstructs the grid geometrically:
  1. find the grid page(s) ("COMPARABLE SALE" + "PROXIMITY"),
  2. detect column anchors by clustering the x of the Address row values,
  3. for each known feature row, read each comparable's value (and adjustment)
     from its column band.

Output: {comp_<i>_<field>: value} for i = 1..N, using canonical field suffixes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Feature label (lowercased, matched as a prefix of the row's label text) ->
# canonical suffix. DESCRIPTIVE fields only — the currency columns (sale price,
# net adjustment, adjusted sale price) are right-aligned with +/- checkboxes and
# are extracted reliably by Camelot, so they are intentionally NOT read here.
_FEATURES: List[Tuple[str, str]] = [
    ("address", "address"),
    ("proximity", "proximity"),
    ("data source", "data_source"),
    ("verification source", "verification_source"),
    ("sales or financing", "sale_financing"),
    ("date of sale", "sale_date"),
    ("leasehold", "leasehold"),
    ("location", "location_rating"),
    ("site", "site_size"),
    ("view", "view"),
    ("design", "design"),
    ("quality of construction", "quality_rating"),
    ("actual age", "actual_age"),
    ("condition", "condition_rating"),
    ("gross living area", "gla"),
    ("functional utility", "functional_utility"),
    ("heating/cooling", "heating_cooling"),
    ("garage/carport", "garage_carport"),
    ("porch/patio", "porch_patio_deck"),
]

_LABEL_X_MAX = 130     # label column ends ~here
_ROW_TOL = 4.0         # words within this y are on the same grid row


def _find_grid_pages(pdf) -> List[int]:
    pages = []
    for i, page in enumerate(pdf.pages):
        t = (page.extract_text() or "").upper()
        if "COMPARABLE SALE" in t and "PROXIMITY" in t and "ADJUSTED SALE" in t:
            pages.append(i)
    return pages


def _column_anchors(words) -> List[float]:
    """Cluster the x of the Address-row value words → [subject, comp1, comp2, ...]."""
    addr = [w for w in words if w["text"].lower().startswith("address") and w["x0"] < _LABEL_X_MAX]
    if not addr:
        return []
    y = addr[0]["top"]
    row = sorted([w for w in words if abs(w["top"] - y) < _ROW_TOL and w["x0"] > _LABEL_X_MAX],
                 key=lambda w: w["x0"])
    # First pass: split on a >60px gap. But long addresses span >60px within a
    # single column, creating false splits, so second-pass MERGE any anchor that
    # is within ~100px of the last kept one (real URAR columns are ~131px apart).
    raw: List[float] = []
    for w in row:
        if not raw or w["x0"] - raw[-1] > 60:
            raw.append(w["x0"])
    anchors: List[float] = []
    for x in raw:
        if not anchors or x - anchors[-1] > 100:
            anchors.append(x)
    return anchors


def _row_words(words, label_prefix: str):
    """Find the grid row whose label column begins with label_prefix."""
    cands = [w for w in words if w["x0"] < _LABEL_X_MAX]
    # build label text per row-y
    from collections import defaultdict
    by_y = defaultdict(list)
    for w in cands:
        by_y[round(w["top"] / _ROW_TOL) * _ROW_TOL].append(w)
    for y, ws in by_y.items():
        label = " ".join(t["text"] for t in sorted(ws, key=lambda w: w["x0"])).lower()
        if label.startswith(label_prefix):
            return y
    return None


def _value_in_band(words, y: float, lo: float, hi: float) -> str:
    toks = sorted([w for w in words if abs(w["top"] - y) < _ROW_TOL and lo <= w["x0"] < hi],
                  key=lambda w: w["x0"])
    return " ".join(t["text"] for t in toks).strip()


def extract_comp_grid(pdf_path) -> Dict[str, str]:
    """Return {comp_<i>_<suffix>: value} parsed from the sales grid page(s)."""
    import pdfplumber
    out: Dict[str, str] = {}
    try:
        pdf = pdfplumber.open(str(Path(pdf_path)))
    except Exception:
        return out
    try:
        comp_base = 0
        for pidx in _find_grid_pages(pdf):
            page = pdf.pages[pidx]
            words = page.extract_words()
            # anchors are already comps-only: the subject column value sits in
            # the x<_LABEL_X_MAX label region and is filtered out by _column_anchors.
            comp_anchors = _column_anchors(words)
            if len(comp_anchors) < 1:
                continue
            # column value band = [anchor-12, anchor+ ~half-column]; rest = adjustment
            bounds = []
            for k, ax in enumerate(comp_anchors):
                nxt = comp_anchors[k + 1] if k + 1 < len(comp_anchors) else ax + 130
                half = ax + (nxt - ax) * 0.55
                bounds.append((ax - 12, half, nxt - 8))   # (val_lo, val_hi, adj_hi)
            for prefix, suffix in _FEATURES:
                if suffix is None:
                    continue
                y = _row_words(words, prefix)
                if y is None:
                    continue
                for k, (vlo, vhi, ahi) in enumerate(bounds):
                    ci = comp_base + k + 1
                    val = _value_in_band(words, y, vlo, vhi)
                    if val:
                        out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                    adj = _value_in_band(words, y, vhi, ahi)
                    if adj and re.search(r"[+\-]?\$?\d", adj):
                        m = re.search(r"[+\-]?\$?[\d,]+", adj)
                        if m:
                            out[f"comp_{ci}_{suffix}_adjustment"] = m.group(0).replace("$", "").replace(",", "")
            comp_base += len(comp_anchors)
    finally:
        pdf.close()
    return out


def _clean(suffix: str, val: str) -> str:
    v = val.strip()
    if suffix in ("sale_price", "net_adjustment", "adjusted_sale_price", "gla"):
        m = re.search(r"[+\-]?\$?[\d,]+", v)
        if m:
            return m.group(0).replace("$", "").replace(",", "").lstrip("+")
    if suffix == "condition_rating":
        m = re.search(r"C[1-6]", v)
        return m.group(0) if m else v
    if suffix == "quality_rating":
        m = re.search(r"Q[1-6]", v)
        return m.group(0) if m else v
    if suffix == "actual_age":
        m = re.search(r"\d+", v)
        return str(int(m.group(0))) if m else v   # strip leading zeros (055 -> 55)
    if suffix == "proximity":
        m = re.search(r"\d+\.\d+\s*miles?.*", v)
        return m.group(0) if m else v
    return v
