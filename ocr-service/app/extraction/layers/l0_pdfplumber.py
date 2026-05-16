"""
Layer 0 — pdfplumber Word + Table Extractor

pdfplumber gives us:
  - Words with exact x0/top/x1/bottom coordinates
  - Tables detected by ruling lines (bordered tables)
  - Character-level positions (more precise than PyMuPDF for some PDFs)

Runs independently and concurrently with other layers.
Output feeds into: L2 (Yes/No resolver) and L3 (grid resolver).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PLWord:
    """A word with precise bounding box from pdfplumber."""
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    page_number: int

    @property
    def y_center(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class PLTable:
    """A table extracted by pdfplumber (ruled borders)."""
    page_number: int
    bbox: tuple          # (x0, top, x1, bottom)
    cells: List[List[Optional[str]]]   # rows × cols of text
    headers: List[str] = field(default_factory=list)

    def get(self, row: int, col: int) -> Optional[str]:
        try:
            return self.cells[row][col]
        except IndexError:
            return None

    def row_texts(self, row: int) -> List[str]:
        try:
            return [c or "" for c in self.cells[row]]
        except IndexError:
            return []


@dataclass
class PDFPlumberResult:
    """Complete pdfplumber output for one PDF."""
    path: str
    words_by_page: Dict[int, List[PLWord]] = field(default_factory=dict)
    tables_by_page: Dict[int, List[PLTable]] = field(default_factory=dict)
    total_pages: int = 0

    def words_on_page(self, page_number: int) -> List[PLWord]:
        return self.words_by_page.get(page_number, [])

    def tables_on_page(self, page_number: int) -> List[PLTable]:
        return self.tables_by_page.get(page_number, [])

    def all_words(self) -> List[PLWord]:
        result = []
        for pn in sorted(self.words_by_page):
            result.extend(self.words_by_page[pn])
        return result


def extract_with_pdfplumber(pdf_path: Path, max_pages: int = 15) -> PDFPlumberResult:
    """
    Run pdfplumber extraction on a PDF.
    Returns words with exact coordinates and any bordered tables.
    Runs quickly (< 2s for 30-page digital PDF).
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed — Layer 0 skipped")
        return PDFPlumberResult(path=str(pdf_path))

    result = PDFPlumberResult(path=str(pdf_path))

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            result.total_pages = len(pdf.pages)
            pages_to_process = min(max_pages, len(pdf.pages))

            for page_num in range(pages_to_process):
                page = pdf.pages[page_num]
                pn = page_num + 1

                # Words with coordinates
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=True,
                )
                result.words_by_page[pn] = [
                    PLWord(
                        text=w["text"],
                        x0=float(w["x0"]),
                        top=float(w["top"]),
                        x1=float(w["x1"]),
                        bottom=float(w["bottom"]),
                        page_number=pn,
                    )
                    for w in words
                    if w.get("text", "").strip()
                ]

                # Bordered tables (ruled lines)
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 4,
                    "join_tolerance": 4,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                })
                if tables:
                    result.tables_by_page[pn] = [
                        PLTable(
                            page_number=pn,
                            bbox=(0, 0, page.width, page.height),
                            cells=[[cell for cell in row] for row in tbl],
                        )
                        for tbl in tables
                        if tbl
                    ]

    except Exception as exc:
        logger.warning("pdfplumber extraction failed for %s: %s", pdf_path.name, exc)

    word_count = sum(len(ws) for ws in result.words_by_page.values())
    table_count = sum(len(ts) for ts in result.tables_by_page.values())
    logger.info(
        "L0 pdfplumber: %s — %d words, %d tables across %d pages",
        pdf_path.name, word_count, table_count, result.total_pages,
    )
    return result
