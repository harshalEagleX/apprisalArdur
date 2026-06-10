"""Sales-comparison narrative extractor — extraction layer.

The appraiser's free-text "Summary of Sales Comparison Approach" / reconciliation
narrative lives on the sales-comparison page, but the URAR form's text layer
returns it interleaved with the blank-form template labels (and, on 1073 condo
forms, with UAD-coded grid cells). A plain synonym/label match therefore grabs a
one-line header stub instead of the paragraph.

This module reads that page's text BLOCKS (each with its own bbox) and keeps only
the appraiser's prose — blocks that read like sentences — dropping three classes
of non-narrative text: software/footer boilerplate, blank-form template sentences
(which carry unfilled "$ to $" / "did did not" artifacts), and UAD grid cells
(semicolon-coded tenure/sale-date tokens). The result is the substantive narrative
the SCA-14 quality-commentary safeguard evaluates (P-3: extraction only, no rule
logic here). Returns {} when no sales-comparison page or no prose is found (P-6).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# Software footers / form identifiers printed on every page.
_BOILER = re.compile(
    r"a la mode|fannie mae|freddie mac|uad version|page \d+ of \d+|"
    r"appraisal software|form \d{3,}|^form [a-z]", re.I)
# Pre-printed grid headers / row labels (not narrative).
_GRID = re.compile(
    r"proximity to subject|item\s+subject|net adjustment|data source\(s\)|"
    r"sale price/gross|comparable sale #|date of prior sale", re.I)
# Blank-form template sentences betrayed by their unfilled fields.
_BLANKS = re.compile(r"\$\s*\$|\$\s+to\s+\$|did\s+did not|ranging in (price|sale price)", re.I)
# Fixed 1004/1073 template sentences (identical on every blank form, so never
# the appraiser's own commentary even when the checkbox version carries text).
_TEMPLATE = re.compile(
    r"this appraisal is made|based on a complete visual inspection|"
    r"subject to completion per plans|subject to the following (repairs|required)", re.I)
# UAD grid-cell leakage: coded cells with semicolons / sale-date codes / tenure.
_UADCELL = re.compile(r"armlth|fee simple|leasehold|s\d\d/\d\d|;.*;", re.I)
# Common function words — real prose has several; coded grid junk has almost none.
_STOPWORDS = re.compile(r"\b(the|and|was|were|is|are|of|to|for|with|that|this|not|been)\b", re.I)

_MIN_WORDS = 12
_MIN_LOWER = 20
_MIN_STOPWORDS = 4


def _is_prose(txt: str) -> bool:
    """True when a text block reads like the appraiser's own sentences rather than
    a form label, footer, template sentence, or coded grid cell."""
    if len(txt.split()) < _MIN_WORDS:
        return False
    if sum(c.islower() for c in txt) < _MIN_LOWER or not txt[:1].isupper():
        return False
    if _BOILER.search(txt) or _GRID.search(txt) or _BLANKS.search(txt) or _TEMPLATE.search(txt):
        return False
    if txt.count(";") >= 2 or _UADCELL.search(txt):
        return False
    if len(_STOPWORDS.findall(txt)) < _MIN_STOPWORDS:
        return False
    if txt.count("$") >= 2 and not re.search(r"\$\s?\d", txt):
        return False
    return True


def _sales_comparison_page(doc):
    for i in range(doc.page_count):
        if "summary of sales comparison" in (doc[i].get_text() or "").lower():
            return i
    return None


def extract_sca_narrative(pdf_path) -> Dict[str, str]:
    """Return {sales_comparison_summary, _narrative_page} or {} (P-6)."""
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        logger.warning("Narrative extractor needs PyMuPDF: %s", exc)
        return {}

    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        doc = fitz.open(str(Path(pdf_path)))
    except Exception as exc:
        logger.warning("Narrative extractor could not open %s: %s", name, exc)
        return {}
    try:
        idx = _sales_comparison_page(doc)
        if idx is None:
            return {}
        blocks = sorted(doc[idx].get_text("blocks"), key=lambda b: (round(b[1]), b[0]))
    except Exception as exc:
        logger.warning("Narrative read failed for %s: %s", name, exc)
        return {}
    finally:
        doc.close()

    prose = [b[4].replace("\n", " ").strip() for b in blocks]
    prose = [t for t in prose if _is_prose(t)]
    text = re.sub(r"\s{2,}", " ", " ".join(prose)).strip()
    if len(text) < 40:
        logger.info("SCA narrative not found (page %s) for %s", idx + 1 if idx is not None else "?", name)
        return {}
    logger.info("SCA narrative for %s: %d chars (page %d)", name, len(text), idx + 1)
    return {"sales_comparison_summary": text, "_narrative_page": str(idx + 1)}
