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


# Referential stub patterns — when a field cell contains only a cross-reference
# to the addenda rather than the actual content. Matching means the field must
# be resolved from the Supplemental Addendum before NLP rules run on it.
_SEE_ADDENDA_RE = re.compile(
    r"^\s*(?:see\s+(?:attached|addend[au]m?|supplement)|"
    r"refer\s+to\s+(?:addend[au]m?|supplement|attached)|"
    r"per\s+(?:addend[au]m?|supplement)|"
    r"addend[au]m?\s+attached)\s*\.?\s*$",
    re.I,
)


def resolve_addendum_reference(
    stub_text: str,
    doc,
    heading_hint: str,
    *,
    max_chars: int = 2000,
) -> tuple[str | None, str]:
    """When a field value is a referential stub, scan the document for the
    Supplemental Addendum section that matches `heading_hint` and return the
    prose content (up to `max_chars`) plus a provenance note.

    Returns (resolved_text, resolution_outcome) where resolved_text is None
    when the referenced section cannot be located (UNRESOLVED_REFERENCE).

    Intentionally limited to one hop: if the addendum itself says "see exhibit,"
    that outer reference is returned as UNRESOLVED_REFERENCE rather than
    followed further.
    """
    heading_hint_lower = heading_hint.lower().strip()
    best_page: int | None = None
    best_score = 0

    for i in range(doc.page_count):
        page_text = (doc[i].get_text() or "").lower()
        # Skip the primary form pages (likely where the stub appeared).
        if "see attached" in page_text and len(page_text) < 300:
            continue
        # Simple token-overlap similarity between page heading tokens and hint.
        page_words = set(re.findall(r"[a-z]{3,}", page_text[:400]))
        hint_words = set(re.findall(r"[a-z]{3,}", heading_hint_lower))
        score = len(page_words & hint_words)
        if score > best_score:
            best_score = score
            best_page = i

    if best_page is None or best_score < 2:
        return None, "could not locate matching addendum section"

    # Extract prose from the matched page, filtering boilerplate.
    blocks = sorted(doc[best_page].get_text("blocks"), key=lambda b: (round(b[1]), b[0]))
    prose = [b[4].replace("\n", " ").strip() for b in blocks if _is_prose(b[4])]
    content = re.sub(r"\s{2,}", " ", " ".join(prose)).strip()[:max_chars]
    if not content:
        return None, "addendum section found but contained no extractable prose"

    return content, f"resolved from addendum page {best_page + 1}"


# Pages carrying the USPAP scope-of-work / intended-use / intended-user /
# certification language, plus the improvements section's smoke/CO detector
# statement — this content only reaches the QC rules that read it (ST-SCOPE,
# ST-INTENDED, I-SMCO, FHA-3, FHA-4) via `addendum_text`, which the deterministic
# form readers never populate for a PDF-only report (only the MISMO XML path
# sets it, from AppraisalAddendumText). Scanning for these markers directly is a
# Tier-1 deterministic read — no LLM needed for text this well-anchored.
_CERT_PAGE_MARKERS = re.compile(
    r"scope\s+of\s+(?:the\s+|this\s+)?(?:work|appraisal|assignment|analysis)|"
    r"intended\s+use|intended\s+user|"
    r"smoke\s*det(?:ector)?|carbon\s*monoxide|co\s*det(?:ector)?|"
    r"hud[/-]fha|minimum\s+property\s+(?:standards|requirements)|"
    r"exposure\s+time",
    re.I,
)


def extract_certification_addendum(pdf_path) -> Dict[str, str]:
    """Return {addendum_text} concatenating prose from every page that carries
    scope-of-work / intended-use-or-user / smoke-CO-detector / HUD-FHA
    certification language. {} when no such page is found (P-6)."""
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        logger.warning("Certification-addendum extractor needs PyMuPDF: %s", exc)
        return {}

    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        doc = fitz.open(str(Path(pdf_path)))
    except Exception as exc:
        logger.warning("Certification-addendum extractor could not open %s: %s", name, exc)
        return {}
    try:
        parts = []
        for i in range(doc.page_count):
            page_text = doc[i].get_text() or ""
            if not _CERT_PAGE_MARKERS.search(page_text):
                continue
            blocks = sorted(doc[i].get_text("blocks"), key=lambda b: (round(b[1]), b[0]))
            prose = [b[4].replace("\n", " ").strip() for b in blocks if _is_prose(b[4])]
            if prose:
                parts.append(re.sub(r"\s{2,}", " ", " ".join(prose)).strip())
    except Exception as exc:
        logger.warning("Certification-addendum read failed for %s: %s", name, exc)
        return {}
    finally:
        doc.close()

    text = "\n\n".join(p for p in parts if p).strip()
    if not text:
        return {}
    logger.info("Certification addendum text for %s: %d chars across %d page(s)",
                name, len(text), len(parts))
    return {"addendum_text": text}


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
    prose_filtered = [t for t in prose if _is_prose(t)]
    text = re.sub(r"\s{2,}", " ", " ".join(prose_filtered)).strip()

    # If the page text (before prose filtering) is a referential stub, resolve it.
    raw_cell = re.sub(r"\s{2,}", " ", " ".join(t.replace("\n", " ").strip() for t in prose)).strip()
    if len(text) < 40 and _SEE_ADDENDA_RE.match(raw_cell):
        resolved, outcome = resolve_addendum_reference(
            raw_cell, doc, heading_hint="sales comparison summary", max_chars=2000
        )
        if resolved:
            logger.info("SCA narrative resolved from addenda for %s: %d chars (%s)",
                        name, len(resolved), outcome)
            return {"sales_comparison_summary": resolved, "_narrative_page": f"addendum ({outcome})"}
        logger.info("SCA narrative stub unresolved for %s: %s", name, outcome)
        return {"sales_comparison_summary": "__UNRESOLVED_REFERENCE__",
                "_narrative_page": f"addendum ({outcome})"}

    if len(text) < 40:
        logger.info("SCA narrative not found (page %s) for %s", idx + 1 if idx is not None else "?", name)
        return {}
    logger.info("SCA narrative for %s: %d chars (page %d)", name, len(text), idx + 1)
    return {"sales_comparison_summary": text, "_narrative_page": str(idx + 1)}
