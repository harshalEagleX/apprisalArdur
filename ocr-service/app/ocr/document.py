"""
Day 2 — Document Loader (Layer 1, minimal)

Responsibilities:
  - Open a PDF with PyMuPDF
  - Extract text per page (direct for digital, flag for scanned)
  - Return a simple PageText list for the extraction tier

Adaptive OCR (Tesseract fallback, image preprocessing, table detection)
is Day 7 work. Today: correct abstraction, minimal implementation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

_DIGITAL_PAGE_WORD_THRESHOLD = 50   # fewer words → suspect scanned page


@dataclass
class PageText:
    page_number: int        # 1-indexed
    text: str
    word_count: int
    is_scanned: bool        # True → low word count, needs OCR fallback later
    width: float = 0.0
    height: float = 0.0

    @property
    def normalized_text(self) -> str:
        """Basic whitespace normalization — full normalization pipeline is Day 8."""
        import re
        t = self.text
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()


@dataclass
class LoadedDocument:
    path: str
    total_pages: int
    pages: List[PageText] = field(default_factory=list)
    file_hash: Optional[str] = None   # SHA-256 for dedup (Day 8 full impl)
    metadata: Dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.normalized_text for p in self.pages)

    @property
    def page_index(self) -> Dict[int, str]:
        """Map of page_number → normalized text."""
        return {p.page_number: p.normalized_text for p in self.pages}

    @property
    def scanned_page_count(self) -> int:
        return sum(1 for p in self.pages if p.is_scanned)

    def text_for_page(self, page_number: int) -> Optional[str]:
        for p in self.pages:
            if p.page_number == page_number:
                return p.normalized_text
        return None


def load_pdf(path: str | Path) -> LoadedDocument:
    """
    Open a PDF and extract per-page text using PyMuPDF.

    Digital pages → direct text extraction.
    Low-word-count pages → flagged is_scanned=True for later OCR fallback.
    Graceful: individual page failures are logged and skipped; they don't
    fail the whole document.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    doc_fitz = fitz.open(str(path))
    pages: List[PageText] = []

    for page_num in range(len(doc_fitz)):
        try:
            page = doc_fitz[page_num]
            text = page.get_text("text") or ""
            words = [w for w in text.split() if w.strip()]
            word_count = len(words)
            is_scanned = word_count < _DIGITAL_PAGE_WORD_THRESHOLD

            pages.append(PageText(
                page_number=page_num + 1,
                text=text,
                word_count=word_count,
                is_scanned=is_scanned,
                width=page.rect.width,
                height=page.rect.height,
            ))

            if is_scanned:
                logger.debug("Page %d of %s has %d words — marked as scanned",
                             page_num + 1, path.name, word_count)

        except Exception as exc:
            logger.warning("Failed to extract page %d of %s: %s", page_num + 1, path.name, exc)
            pages.append(PageText(
                page_number=page_num + 1,
                text="",
                word_count=0,
                is_scanned=True,
            ))

    doc_fitz.close()

    doc = LoadedDocument(
        path=str(path),
        total_pages=len(pages),
        pages=pages,
    )

    logger.info(
        "Loaded %s — %d pages, %d scanned, %d words total",
        path.name, doc.total_pages, doc.scanned_page_count,
        sum(p.word_count for p in pages),
    )
    return doc
