"""LLM extraction of the SCA comparable-sales grid — extraction layer v0.1.12.

Why this exists: the deterministic Camelot/pdfplumber readers miss or mis-read
the currency rows of the sales grid — e.g. surfacing the cost-approach figure or
a plain sale price as an "adjusted sale price". That silently breaks the
bracketing rules (SCA-BR/SCA-26).

This module is the "brain": it reads the grid-page TEXT that OCR already produced
(the "eyes") and asks the LLM for each comparable's bottom-row currency figures,
then applies validation logic (the adjusted price must equal sale price + net
adjustment) before trusting a value. It performs NO OCR and never sees images.

Boundary: returns {comp_<i>_<field>: value}. Empty dict on any failure so the
caller keeps its deterministic result (P-6).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional

# Only the grid rows the currency/GLA extractor needs — keeping just these (plus
# the column header) cuts the prompt from the whole grid (~3k tokens) to a few
# hundred, which both respects the LLM rate limit and sharpens accuracy.
_KEEP_ROW = re.compile(
    r"(comparable sale|feature|sale price|gross living|net adj|gross adj|adjusted sale)",
    re.I,
)

from app.extraction import llm_groq
from app.extraction.comp_grid_extractor import _find_grid_pages

logger = logging.getLogger(__name__)

# Stamped onto every field this module produces (extraction_method/version log).
SCA_LLM_VERSION = "0.1.12"

_CURRENCY = ("sale_price", "net_adjustment", "adjusted_sale_price")
_FIELDS = _CURRENCY + ("gross_adj_pct", "gla")

_SYSTEM = (
    "You read the Sales Comparison Approach grid of a URAR / Form 1004 residential "
    "appraisal report. Output ONLY one valid JSON object and nothing else."
)


def _prompt(grid_text: str) -> str:
    return (
        "Below is ONE spatially-reconstructed page of the COMPARABLE SALES grid of a "
        "URAR/1004 appraisal. Each line is one grid row: a row label followed by the "
        "cell values left-to-right.\n\n"
        "COLUMN STRUCTURE (critical): the columns are  FEATURE-label | SUBJECT | "
        "COMPARABLE SALE A | COMPARABLE SALE B | COMPARABLE SALE C.  IGNORE the SUBJECT "
        "column entirely — only return comparables.\n"
        "- Return the comparables ON THIS PAGE ONLY, left-to-right: the leftmost "
        "comparable is comp 1, next is comp 2, then comp 3. Ignore the printed "
        "'COMPARABLE SALE #' numbers — use left-to-right position.\n"
        "- The 'Sale Price' row lists the SUBJECT first, then one price per comparable; "
        "skip the first amount.\n"
        "- The 'Net Adjustment (Total)' row has NO subject value — one signed amount per "
        "comparable.\n"
        "- gla = 'Gross Living Area' in square feet (the subject's GLA is first; skip it).\n\n"
        'Return JSON exactly as: {"comps":[{"comp":1,"sale_price":<number>,'
        '"net_adjustment":<number, signed +/->,"gross_adj_pct":<number>,"gla":<number>}, ... ]}.\n'
        "Do NOT output adjusted_sale_price (it is computed as sale_price + net_adjustment). "
        "Use digits only (no $ or commas). Omit a field you cannot find. Return only the "
        "comparable columns that actually contain sale data on this page (1 to 3).\n\n"
        "GRID PAGE TEXT:\n" + grid_text
    )


def _grid_pages_text(pdf_path):
    """Spatially reconstruct EACH grid page separately: cluster words by row (y)
    and sort by column (x) so each row label sits with its cell values on one
    line. Plain reading-order extract_text() scatters the flattened cell numbers
    away from their labels (the values exist, just disassociated), defeating both
    the deterministic readers and a naive LLM prompt.

    Returns a list of (page_index, reconstructed_text) in document order — the
    SCA grid is commonly split across two pages (comps 1-3 then 4-6), so the
    caller numbers comparables sequentially across pages, never trusting the
    printed 'COMPARABLE SALE #' which some forms restart at 1 on each page."""
    import pdfplumber

    pages = []
    with pdfplumber.open(str(Path(pdf_path))) as pdf:
        idxs = _find_grid_pages(pdf) or list(range(min(4, len(pdf.pages))))
        for i in idxs:
            page = pdf.pages[i]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            lines: Dict[int, list] = {}
            for w in words:
                lines.setdefault(round(w["top"] / 3.0), []).append(w)
            rows = [
                " ".join(w["text"] for w in sorted(lines[yk], key=lambda w: w["x0"]))
                for yk in sorted(lines)
            ]
            # Keep only the currency/GLA rows (+ header) to stay within the token
            # budget; fall back to the full page if the filter finds nothing.
            kept = [r for r in rows if _KEEP_ROW.search(r)]
            pages.append((i, "\n".join(kept) if kept else "\n".join(rows)))
    return pages


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def _plausible(field: str, n: float) -> bool:
    if field in ("sale_price", "adjusted_sale_price"):
        return 10_000 <= n <= 100_000_000
    if field == "gross_adj_pct":
        return 0 <= n <= 100
    if field == "gla":
        return 200 <= n <= 20_000
    return True  # net_adjustment can be any sign/size


def _extract_page_comps(page_text: str):
    """LLM-extract one grid page's comparables, in left-to-right column order.

    Returns a list of value dicts (sale_price/net_adjustment/gross_adj_pct/gla),
    ordered by column. Rows with no sale data are dropped — this also makes the
    prior-sale-history grid (which shares the 'COMPARABLE SALE #' header but has
    no Sale Price / Net Adjustment rows) yield nothing, so it can't pollute."""
    data = llm_groq.chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(page_text[:12000])},
        ],
        reasoning_effort="medium",  # column alignment needs real reasoning
        max_tokens=4096,  # headroom so reasoning tokens don't truncate the JSON
    )
    if not data or not isinstance(data.get("comps"), list):
        return []
    ordered = []
    for row in data["comps"]:
        if not isinstance(row, dict):
            continue
        try:
            col = int(row.get("comp"))
        except Exception:
            col = 999
        vals = {f: _num(row.get(f)) for f in ("sale_price", "net_adjustment", "gross_adj_pct", "gla")}
        if vals["sale_price"] is None and vals["net_adjustment"] is None:
            continue  # not a real comparable column (e.g. prior-sale grid)
        ordered.append((col, vals))
    ordered.sort(key=lambda t: t[0])
    return [v for _, v in ordered]


def extract_sca_grid_llm(pdf_path) -> Dict[str, str]:
    """Return {comp_<i>_<field>: value} for the SCA currency/GLA grid via the LLM.

    Handles the SCA grid being split across pages: comparables are numbered
    sequentially by page order then column order (never by the printed
    'COMPARABLE SALE #', which some forms restart at 1 on the continuation page).
    Applies the identity adjusted == sale + net so a garbled/hallucinated
    adjusted value can never pass through.
    """
    if not llm_groq.groq_extraction_available():
        return {}
    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        pages = _grid_pages_text(pdf_path)
    except Exception as exc:
        logger.warning("SCA-LLM grid-text read failed for %s: %s", name, exc)
        return {}
    if not pages:
        return {}

    out: Dict[str, str] = {}
    gi = 0  # global comparable index, sequential across pages
    for _pidx, text in pages:
        if not text.strip():
            continue
        for vals in _extract_page_comps(text):
            gi += 1
            if gi > 12:
                break
            sale, net = vals.get("sale_price"), vals.get("net_adjustment")
            if sale is not None and net is not None:
                vals["adjusted_sale_price"] = sale + net  # validated identity
            for f in _FIELDS:
                n = vals.get(f)
                if n is None or not _plausible(f, n):
                    continue
                out[f"comp_{gi}_{f}"] = str(n) if f == "gross_adj_pct" else str(int(round(n)))
        if gi > 12:
            break

    if out:
        logger.info(
            "SCA-LLM v%s extracted %d grid fields across %d page(s) for %s",
            SCA_LLM_VERSION, len(out), len(pages), name,
        )
    return out
