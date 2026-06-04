"""
Dedicated Sales-Comparison grid extractor — Camelot LATTICE (true cell matrix).

The URAR sales grid is a bordered (lattice) table. Reading it as a real cell
matrix — row label x column — instead of x-band binning eliminates the
pdfplumber "glue" artifacts (a comp's value sticking to the prior comp's
adjustment, which corrupted site/date and dropped numbers) and yields a real
confidence signal (Camelot's parsing accuracy).

Column layout (detected, not hardcoded): the header row carries "COMPARABLE
SALE" in the comp value columns; the subject value column is two left of comp 1;
each comp's +/- adjustment sits two columns right of its value.

Contract: returns {comp_<i>_<field>[/_adjustment], subject_grid_<field>,
_sca_grid_accuracy}. Returns {} when Camelot is unavailable or the page is not a
readable lattice (scanned image) so the caller falls back to the pdfplumber
band extractor (graceful degradation, P-6).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# URAR row label (lowercased prefix) -> canonical field suffix. Order matters:
# the more specific "sale price/gross" must precede "sale price".
_ROW_FIELDS: List = [
    ("address", "address"),
    ("proximity", "proximity"),
    ("sale price/gross", None),                 # $/sqft line — skip
    ("sale price", "sale_price"),
    ("data source", "data_source"),
    ("verification source", "verification_source"),
    ("sales or financing", "sale_financing"),
    ("date of sale", "sale_date"),
    ("location", "location_rating"),
    ("leasehold", "leasehold"),
    ("site", "site_size"),
    ("view", "view"),
    ("design", "design"),
    ("quality of construction", "quality_rating"),
    ("actual age", "actual_age"),
    ("condition", "condition_rating"),
    ("above grade", "room_count"),
    ("gross living area", "gla"),
    ("basement", "basement"),
    ("functional utility", "functional_utility"),
    ("heating", "heating_cooling"),
    ("garage", "garage_carport"),
    ("porch", "porch_patio_deck"),
]

# Descriptive rows that have NO +/- adjustment column.
_NO_ADJ = {"address", "proximity", "data_source", "verification_source", "room_count"}


def _field_for_label(label: str) -> Optional[str]:
    low = re.sub(r"\s+", " ", label or "").strip().lower()
    if not low:
        return None
    for prefix, suffix in _ROW_FIELDS:
        if low.startswith(prefix):
            return suffix
    return None


def _clean(suffix: str, val: str) -> str:
    v = re.sub(r"\s+", " ", val).strip()
    if suffix in ("sale_price", "gla"):
        m = re.search(r"[\d,]{3,}", v)
        return m.group(0).replace(",", "") if m else v
    if suffix == "condition_rating":
        m = re.search(r"C[1-6]", v)
        return m.group(0) if m else v
    if suffix == "quality_rating":
        m = re.search(r"Q[1-6]", v)
        return m.group(0) if m else v
    if suffix == "actual_age":
        m = re.search(r"\d+", v)
        return str(int(m.group(0))) if m else v
    return v


def extract_sca_grid(pdf_path) -> Dict[str, str]:
    """Camelot-lattice SCA grid → field dict (see module docstring). {} on failure."""
    try:
        import camelot
    except Exception:
        return {}
    from app.extraction.comp_grid_extractor import _find_grid_pages
    out: Dict[str, str] = {}
    try:
        import pdfplumber
        with pdfplumber.open(str(Path(pdf_path))) as pdf:
            grid_pages = _find_grid_pages(pdf)   # 0-indexed
    except Exception:
        return {}
    if not grid_pages:
        return {}

    comp_base = 0
    accuracies: List[float] = []
    for p0 in grid_pages:
        try:
            tables = camelot.read_pdf(str(pdf_path), pages=str(p0 + 1),
                                      flavor="lattice", line_scale=40)
        except Exception as exc:
            logger.debug("Camelot SCA lattice failed p%d: %s", p0 + 1, exc)
            continue
        if not len(tables):
            continue
        df = tables[0].df
        accuracies.append(float(tables[0].parsing_report.get("accuracy", 0) or 0))

        # comp value columns = header cells containing "COMPARABLE SALE"
        comp_cols: List[int] = []
        for r in range(min(6, df.shape[0])):
            cols = [c for c in range(df.shape[1]) if "COMPARABLE SALE" in df.iat[r, c].upper()]
            if cols:
                comp_cols = cols
                break
        if not comp_cols:
            continue
        subj_col = comp_cols[0] - 2

        for r in range(df.shape[0]):
            suffix = _field_for_label(df.iat[r, 1] if df.shape[1] > 1 else "")
            if not suffix:
                continue
            if comp_base == 0 and 0 <= subj_col < df.shape[1]:
                sv = df.iat[r, subj_col].strip()
                if sv:
                    out[f"subject_grid_{suffix}"] = _clean(suffix, sv)
            for k, cc in enumerate(comp_cols):
                ci = comp_base + k + 1
                val = df.iat[r, cc].strip() if cc < df.shape[1] else ""
                if val:
                    out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                if suffix in _NO_ADJ:
                    continue
                adj_col = cc + 2
                if adj_col < df.shape[1]:
                    m = re.search(r"[+\-]?\$?[\d,]+", df.iat[r, adj_col])
                    if m:
                        out[f"comp_{ci}_{suffix}_adjustment"] = (
                            m.group(0).replace("$", "").replace(",", "").lstrip("+"))
        comp_base += len(comp_cols)

    if accuracies:
        out["_sca_grid_accuracy"] = str(round(sum(accuracies) / len(accuracies), 1))
    return out
