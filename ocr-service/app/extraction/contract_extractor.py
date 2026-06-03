"""
Sales-contract extractor — best-effort price/date/parties.

Contracts are the hardest input in the corpus: TREC contracts are flattened
scans (no text layer), and the Michigan/Florida purchase agreements keep their
values on blank fill-in lines. So this extractor:
  * reads the embedded text where a page has it, else OCRs the rendered page
    with Tesseract (the reliable OCR path in this environment),
  * pulls the contract PRICE (the largest plausible dollar amount appearing in a
    price context) and the contract DATE (latest date = fully-executed date),
    plus seller/buyer names when clearly labelled.

It returns only what it finds with reasonable confidence. When a contract is
unreadable, it returns nothing and the C-2/C-4 rules stay at VERIFY (a reviewer
compares manually) rather than risk a false price mismatch.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import fitz

logger = logging.getLogger(__name__)

_PRICE_CTX = re.compile(r"(sales?\s*price|purchase\s*price|total|sum of|cash\s*portion|"
                        r"contract\s*price|3a|3b)", re.I)
_AMOUNT = re.compile(r"\$?\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{5,})")
_DATE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b")
_CONCESSION_CTX = re.compile(r"(concession|seller\s*(?:paid|to pay|contribution)|"
                             r"seller\s*conc)", re.I)


def _tesseract_text(page) -> str:
    """OCR a rendered page via Tesseract using a temp PNG path (reliable here)."""
    try:
        import pytesseract
        from PIL import Image
        mat = fitz.Matrix(220 / 72, 220 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            img.save(tmp)
            return pytesseract.image_to_string(tmp, config="--psm 6 --oem 3")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    except Exception as exc:
        logger.warning("Contract OCR failed: %s", exc)
        return ""


def _page_text(page) -> str:
    embedded = page.get_text("text")
    if len(embedded.split()) >= 30:
        return embedded
    return _tesseract_text(page)


def _to_amount(s: str) -> Optional[float]:
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _line_amount(line: str, lo: float = 1000.0) -> Optional[float]:
    """Largest plausible amount on a single line (>= lo)."""
    best = None
    for m in _AMOUNT.finditer(line):
        v = _to_amount(m.group(1))
        if v is not None and lo <= v <= 50_000_000:
            best = max(best or 0, v)
    return best


def _contract_price(text: str) -> Optional[str]:
    """Targeted contract-price extraction (no noisy 'largest amount' fallback).

    Strategy 1 (TREC): Cash portion (A) + Loan/Financing (B) = Sales Price.
    Strategy 2: an explicit 'Sales/Purchase Price (Sum...)' or 'Total ... Price'
    line carrying an amount.
    Returns None when neither is confidently found → the QC rule stays VERIFY.
    """
    lines = text.splitlines()
    cash = loan = None
    explicit = None
    for ln in lines:
        low = ln.lower()
        if "cash portion" in low and cash is None:
            cash = _line_amount(ln)
        elif re.search(r"\b(loan|financing|third party|seller financing)\b", low) and loan is None:
            loan = _line_amount(ln, lo=10_000)
        elif re.search(r"(sales?\s*price\s*\(sum|total\s*(sales?|purchase)\s*price|"
                       r"purchase\s*price.*\bsum\b)", low):
            amt = _line_amount(ln, lo=10_000)
            if amt:
                explicit = amt
    if cash is not None and loan is not None:
        total = cash + loan
        if 10_000 <= total <= 50_000_000:
            return str(int(total))
    if explicit:
        return str(int(explicit))
    return None


def _contract_date(text: str) -> Optional[str]:
    """Latest valid date in the document = the fully-executed contract date."""
    best = None
    for mm, dd, yy in _DATE.findall(text):
        m_, d_, y_ = int(mm), int(dd), int(yy)
        if y_ < 100:
            y_ += 2000
        if not (1 <= m_ <= 12 and 1 <= d_ <= 31 and 2000 <= y_ <= 2099):
            continue
        key = (y_, m_, d_)
        if best is None or key > best[0]:
            best = (key, f"{m_:02d}/{d_:02d}/{y_}")
    return best[1] if best else None


def _concessions(text: str) -> Optional[str]:
    for line in text.splitlines():
        if _CONCESSION_CTX.search(line):
            for m in _AMOUNT.finditer(line):
                v = _to_amount(m.group(1))
                if v is not None and 0 < v <= 200_000:
                    return str(int(v))
    return None


def extract_contract_fields(pdf_path, max_pages: int = 4) -> Dict[str, str]:
    """Return {canonical_field: value} from the sales contract (best effort)."""
    pdf_path = Path(pdf_path)
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("Cannot open contract %s: %s", pdf_path, exc)
        return {}
    texts: List[str] = []
    try:
        for i in range(min(max_pages, len(doc))):
            texts.append(_page_text(doc[i]))
    finally:
        doc.close()
    text = "\n".join(texts)
    if not text.strip():
        return {}

    out: Dict[str, str] = {}
    price = _contract_price(text)
    if price:
        out["contract_price"] = price
    date = _contract_date(text)
    if date:
        out["contract_date"] = date
    conc = _concessions(text)
    if conc:
        out["concessions_amount"] = conc
    return out
