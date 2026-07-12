"""
extractor.grid (grd-1.0.0) — comparable-sales grid + 1004MC.

SHALqc.md §3.2 step 4: pdfplumber column bands and Camelot lattice extraction
run SEQUENTIALLY over the grid pages — never in parallel (parallel Camelot +
pdfplumber deep-parse on the same document is a known recursion crash, see
SHALqc.md §3.2 "Concurrency rule"). The two reads are then arbitrated:
  - both find the same (normalized) value  → confidence 0.90
  - only one finds a value                 → confidence 0.88
  - the two disagree                       → pdfplumber's band read wins at
    confidence 0.85 (its geometric column anchors are the more precise of the
    two on the compact grid); Camelot's value is retained as a conflict
    witness, never discarded (P3), so a genuine grid misread surfaces to a
    reviewer instead of being silently picked.

pdfplumber pass ported from ocr-service/app/extraction/comp_grid_extractor.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "grd-1.0.0"

logger = logging.getLogger(__name__)

_CONF_AGREE = 0.90
_CONF_SINGLE = 0.88
_CONF_DISAGREE_WINNER = 0.85

# Feature label (lowercased prefix) -> canonical suffix. Descriptive columns
# only — currency columns (sale price, net/adjusted price) are read reliably
# by both readers via right-aligned cells, so they are handled directly.
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
    ("basement", "basement"),
    ("functional utility", "functional_utility"),
    ("heating/cooling", "heating_cooling"),
    ("garage/carport", "garage_carport"),
    ("porch/patio", "porch_patio_deck"),
]

_LABEL_X_MAX = 130
_ROW_TOL = 4.0
_NO_ADJ = {"address", "proximity", "data_source", "verification_source"}


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
        return str(int(m.group(0))) if m else v
    if suffix == "proximity":
        m = re.search(r"\d+\.\d+\s*miles?.*", v)
        return m.group(0) if m else v
    if suffix in ("sale_date", "sale_financing"):
        return re.sub(r"^\d+(?=[scA])", "", v).strip()
    if suffix in ("view", "location_rating"):
        return re.sub(r"^\d+(?=[A-Za-z])", "", v).strip()
    return v


def _norm_box(bbox, page_w: float, page_h: float, pad: float = 0.003) -> Optional[Dict]:
    if not bbox or page_w <= 0 or page_h <= 0:
        return None
    x0, top, x1, bottom = bbox
    x = max(0.0, x0 / page_w - pad)
    y = max(0.0, top / page_h - pad)
    w = min(1.0 - x, (x1 - x0) / page_w + 2 * pad)
    h = min(1.0 - y, (bottom - top) / page_h + 2 * pad)
    if w <= 0.0 or h <= 0.0:
        return None
    return {"x": round(x, 5), "y": round(y, 5), "w": round(w, 5), "h": round(h, 5)}


def _find_grid_pages_plumber(pdf) -> List[int]:
    pages = []
    for i, page in enumerate(pdf.pages):
        t = (page.extract_text() or "").upper()
        if "COMPARABLE SALE" in t and "PROXIMITY" in t and "ADJUSTED SALE" in t:
            pages.append(i)
    return pages


def _column_anchors(words) -> List[float]:
    addr = [w for w in words if w["text"].lower().startswith("address") and w["x0"] < _LABEL_X_MAX]
    if not addr:
        return []
    y = addr[0]["top"]
    row = sorted([w for w in words if abs(w["top"] - y) < _ROW_TOL and w["x0"] > _LABEL_X_MAX],
                 key=lambda w: w["x0"])
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
    from collections import defaultdict
    by_y = defaultdict(list)
    for w in words:
        if w["x0"] < _LABEL_X_MAX:
            by_y[round(w["top"] / _ROW_TOL) * _ROW_TOL].append(w)
    pat = re.compile(re.escape(label_prefix) + r"\b")
    matches = [y for y, ws in by_y.items()
               if pat.match(" ".join(t["text"] for t in sorted(ws, key=lambda w: w["x0"])).lower())]
    if not matches:
        return None
    if len(matches) == 1 or not anchors:
        return matches[0]

    def comp_word_count(y):
        return sum(1 for w in words
                   if abs(w["top"] - y) < _ROW_TOL and any(abs(w["x0"] - a) < 60 for a in anchors))

    return max(matches, key=comp_word_count)


def _value_in_band(words, y: float, lo: float, hi: float):
    toks = sorted([w for w in words if abs(w["top"] - y) < _ROW_TOL and lo <= w["x0"] < hi],
                  key=lambda w: w["x0"])
    text = " ".join(t["text"] for t in toks).strip()
    if not toks:
        return text, None
    bbox = (min(t["x0"] for t in toks), min(t["top"] for t in toks),
            max(t["x1"] for t in toks), max(t["bottom"] for t in toks))
    return text, bbox


def _extract_grid_pdfplumber(pdf_path) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """Column-band read of the sales-comparison grid. Returns
    ({comp_<i>_<suffix>: value}, {field: {"page","bbox"}})."""
    import pdfplumber

    out: Dict[str, str] = {}
    positions: Dict[str, Dict] = {}
    try:
        pdf = pdfplumber.open(str(Path(pdf_path)))
    except Exception as exc:
        logger.warning("grid(pdfplumber): could not open %s: %s", pdf_path, exc)
        return out, positions
    try:
        comp_base = 0
        for pidx in _find_grid_pages_plumber(pdf):
            page = pdf.pages[pidx]
            page_no = pidx + 1
            pw, ph = float(page.width), float(page.height)
            words = page.extract_words()
            comp_anchors = _column_anchors(words)
            if len(comp_anchors) < 1:
                continue
            cols = []
            for k, ax in enumerate(comp_anchors):
                nxt = comp_anchors[k + 1] if k + 1 < len(comp_anchors) else ax + 131
                cols.append((ax, nxt))
            for prefix, suffix in _FEATURES:
                if suffix == "sale_date":
                    continue  # handled positionally below (glued adj+date tokens)
                y = _row_words(words, prefix, comp_anchors)
                if y is None:
                    continue
                no_adj = suffix in _NO_ADJ
                for k, (ax, nxt) in enumerate(cols):
                    ci = comp_base + k + 1
                    if no_adj:
                        val, vbox = _value_in_band(words, y, ax - 8, nxt - 6)
                        if val:
                            out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                            positions[f"comp_{ci}_{suffix}"] = {"page": page_no, "bbox": _norm_box(vbox, pw, ph)}
                        continue
                    half = ax + (nxt - ax) * 0.55
                    val, vbox = _value_in_band(words, y, ax - 12, half)
                    if val:
                        out[f"comp_{ci}_{suffix}"] = _clean(suffix, val)
                        positions[f"comp_{ci}_{suffix}"] = {"page": page_no, "bbox": _norm_box(vbox, pw, ph)}
                    adj, _ = _value_in_band(words, y, half, nxt - 8)
                    if adj and re.search(r"[-+][$]?\d", adj):
                        m = re.search(r"[-+][$]?[\d,]+", adj)
                        if m:
                            out[f"comp_{ci}_{suffix}_adjustment"] = m.group(0).replace("$", "").replace(",", "")

            ydate = _row_words(words, "date of sale", comp_anchors)
            if ydate is not None:
                row_txt = " ".join(
                    t["text"] for t in sorted(
                        (w for w in words if abs(w["top"] - ydate) < _ROW_TOL and w["x0"] >= comp_anchors[0] - 12),
                        key=lambda w: w["x0"]))
                unit = r"(?:[sc]\d{2}/\d{2}|Active|Unk)"
                dates = re.findall(unit + r"(?:;" + unit + r")?", row_txt)
                ydate_box = _norm_box((comp_anchors[0] - 12, ydate, comp_anchors[-1] + 131, ydate + 10), pw, ph)
                for k in range(len(comp_anchors)):
                    if k < len(dates):
                        out[f"comp_{comp_base + k + 1}_sale_date"] = dates[k]
                        positions[f"comp_{comp_base + k + 1}_sale_date"] = {"page": page_no, "bbox": ydate_box}

            if comp_base == 0:
                subj_hi = comp_anchors[0] - 12
                for prefix, suffix in (("gross living area", "gla"), ("condition", "condition_rating"),
                                       ("quality of construction", "quality_rating"),
                                       ("location", "location_rating"), ("view", "view")):
                    ys = _row_words(words, prefix, comp_anchors)
                    if ys is None:
                        continue
                    sval, sbox = _value_in_band(words, ys, _LABEL_X_MAX, subj_hi)
                    if sval:
                        out[f"subject_grid_{suffix}"] = _clean(suffix, sval)
                        positions[f"subject_grid_{suffix}"] = {"page": page_no, "bbox": _norm_box(sbox, pw, ph)}
            comp_base += len(comp_anchors)
    finally:
        pdf.close()
    return out, positions


def _find_grid_pages_camelot(pdf_path) -> List[int]:
    """Locate grid pages via pdfplumber text (Camelot has no text-search API)."""
    import pdfplumber
    pages = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                t = (page.extract_text() or "").upper()
                if "COMPARABLE SALE" in t and "PROXIMITY" in t:
                    pages.append(i + 1)  # camelot is 1-indexed
    except Exception as exc:
        logger.warning("grid(camelot): page scan failed for %s: %s", pdf_path, exc)
    return pages


def _extract_grid_camelot(pdf_path) -> Dict[str, str]:
    """Lattice-table read of the grid, as the second (arbitration) witness.

    Row-label based: the grid's first column is the feature label ("Address",
    "Condition", ...); remaining columns are comp columns left-to-right. Far
    coarser than the pdfplumber band read (no adjustment sub-column split) but
    a structurally independent read — exactly what arbitration needs.
    """
    out: Dict[str, str] = {}
    pages = _find_grid_pages_camelot(pdf_path)
    if not pages:
        return out
    try:
        import camelot
    except Exception as exc:
        logger.info("grid(camelot): camelot-py not available (%s) — pdfplumber-only", exc)
        return out

    comp_base = 0
    for page_no in pages:
        try:
            tables = camelot.read_pdf(str(pdf_path), pages=str(page_no), flavor="lattice")
        except Exception as exc:
            logger.warning("grid(camelot): read_pdf failed on page %d of %s: %s", page_no, pdf_path, exc)
            continue
        for table in tables:
            df = table.df
            if df.shape[1] < 2:
                continue
            n_comps = df.shape[1] - 1
            matched_any = False
            for _, row in df.iterrows():
                label = str(row.iloc[0]).strip().lower()
                suffix = next((s for prefix, s in _FEATURES if label.startswith(prefix)), None)
                if suffix is None:
                    continue
                for k in range(1, min(n_comps + 1, df.shape[1])):
                    val = str(row.iloc[k]).strip()
                    if not val:
                        continue
                    matched_any = True
                    out[f"comp_{comp_base + k}_{suffix}"] = _clean(suffix, val)
            if matched_any:
                comp_base += n_comps
    return out


def extract_grid(pdf_path, schema=None) -> ExtractedFieldSet:
    """Grid extraction with pdfplumber + Camelot run sequentially, arbitrated.

    `schema` is accepted for interface symmetry with the other extractors but
    unused — the grid reader is geometry-driven, not label-driven.
    """
    fs = ExtractedFieldSet()

    # Sequential — never parallel with each other or with an OCR pass over the
    # same document (SHALqc.md §3.2 concurrency rule).
    plumber_vals, plumber_pos = _extract_grid_pdfplumber(pdf_path)
    camelot_vals = _extract_grid_camelot(pdf_path)

    all_fields = set(plumber_vals) | set(camelot_vals)
    for field_name in all_fields:
        pv = plumber_vals.get(field_name)
        cv = camelot_vals.get(field_name)
        pos = plumber_pos.get(field_name, {})

        if pv and cv:
            if pv.strip().lower() == cv.strip().lower():
                fs.add(ExtractedField(
                    canonical_name=field_name, value=pv, raw_value=pv,
                    source=Source.GRID, confidence=_CONF_AGREE,
                    page=pos.get("page", 0), bbox=pos.get("bbox"),
                ))
            else:
                ef = ExtractedField(
                    canonical_name=field_name, value=pv, raw_value=pv,
                    source=Source.GRID, confidence=_CONF_DISAGREE_WINNER,
                    page=pos.get("page", 0), bbox=pos.get("bbox"),
                )
                ef.add_conflict(source="grid_camelot", value=cv, confidence=_CONF_DISAGREE_WINNER)
                fs.add(ef)
        else:
            value = pv or cv
            source_tag = Source.GRID
            fs.add(ExtractedField(
                canonical_name=field_name, value=value, raw_value=value,
                source=source_tag, confidence=_CONF_SINGLE,
                page=pos.get("page", 0), bbox=pos.get("bbox"),
            ))

    logger.info("grid_extractor: %d fields found in %s", len(fs.found_fields()), Path(pdf_path).name)
    return fs
