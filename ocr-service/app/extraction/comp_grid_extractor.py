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

# Descriptive-only features: these four URAR rows carry NO +/- adjustment sub-column,
# so their value uses the FULL cell width. Capping them at 55% (the value/adjustment
# split used for adjustable rows) truncated long text — e.g. data/verification source.
# NB: Sales/Financing, Date of Sale, Leasehold etc. DO have an adjustment column and
# must keep the value/adjustment split, or they bleed into the adjustment / next comp.
_NO_ADJ = {"address", "proximity", "data_source", "verification_source"}


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


def _row_words(words, label_prefix: str, anchors=None):
    """Find the grid row whose label column begins with label_prefix.

    A label can occur more than once on the page (e.g. "Data Source(s)" appears
    in the comp grid AND the prior-sales-history block). When it does, pick the
    occurrence with the most words sitting in the comparable columns — that is
    the actual sales-grid row, not a same-named row elsewhere.
    """
    import re
    from collections import defaultdict
    by_y = defaultdict(list)
    for w in words:
        if w["x0"] < _LABEL_X_MAX:
            by_y[round(w["top"] / _ROW_TOL) * _ROW_TOL].append(w)
    # Word-boundary match on the label column so "Condition" matches the grid row
    # label but NOT the certification prose ("conditions, and appraiser's ...").
    pat = re.compile(re.escape(label_prefix) + r"\b")
    matches = [y for y, ws in by_y.items()
               if pat.match(" ".join(t["text"] for t in sorted(ws, key=lambda w: w["x0"])).lower())]
    if not matches:
        return None
    if len(matches) == 1 or not anchors:
        return matches[0]

    def comp_word_count(y):
        return sum(1 for w in words
                   if abs(w["top"] - y) < _ROW_TOL
                   and any(abs(w["x0"] - a) < 60 for a in anchors))

    return max(matches, key=comp_word_count)


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
            # Each comp cell spans [anchor_k, anchor_{k+1}). Adjustable features split
            # the cell into value (left ~55%) + adjustment (right); descriptive-only
            # features (_NO_ADJ) span the full cell so long text is not truncated.
            cols = []
            for k, ax in enumerate(comp_anchors):
                nxt = comp_anchors[k + 1] if k + 1 < len(comp_anchors) else ax + 131
                cols.append((ax, nxt))
            for prefix, suffix in _FEATURES:
                if suffix is None:
                    continue
                y = _row_words(words, prefix, comp_anchors)
                if y is None:
                    continue
                no_adj = suffix in _NO_ADJ
                for k, (ax, nxt) in enumerate(cols):
                    ci = comp_base + k + 1
                    if no_adj:
                        val = _value_in_band(words, y, ax - 8, nxt - 6)
                        if val:
                            out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                        continue
                    half = ax + (nxt - ax) * 0.55
                    val = _value_in_band(words, y, ax - 12, half)
                    if val:
                        out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                    adj = _value_in_band(words, y, half, nxt - 8)
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
    if suffix in ("sale_date", "sale_financing"):
        # strip adjustment-column digit bleed before the UAD code ("0s06/25" -> "s06/25")
        return re.sub(r"^\d+(?=[scA])", "", v).strip()
    if suffix in ("view", "location_rating"):
        # UAD codes start with a letter (N/B/A; …); a leading digit is bleed ("0N;Res;")
        return re.sub(r"^\d+(?=[A-Za-z])", "", v).strip()
    return v
