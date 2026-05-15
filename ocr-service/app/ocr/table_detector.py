"""
Day 10 — Table Detection and Linearization

Three detection strategies applied in order, each building on the previous:
  Strategy A — Line-based detection: bordered tables with explicit grid lines
  Strategy B — Whitespace-based detection: space-aligned columns without borders
  Strategy C — Header-based inference: comparable sale grids with labeled columns

Output: StructuredTable — every cell labeled with row_id and column_id.
Failures produce a failed StructuredTable, not incorrect data.
Downstream extraction sees the failure flag and falls back to text extraction.

The UAD 1004 comparable sale grid is the primary target for Strategy C.
The neighborhood section land-use table is Strategy B's primary target.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TableCell:
    row_id: str          # row header or sequential index "R1", "R2", ...
    col_id: str          # column header or sequential index "C1", "C2", ...
    value: str
    raw_text: str        # verbatim before any normalization


@dataclass
class StructuredTable:
    """
    A detected table with every cell labeled by row and column.
    detection_strategy: "line" | "whitespace" | "header" | "failed"
    When failed=True, raw_region contains the original text for fallback.
    """
    table_id: str
    page_number: int
    detection_strategy: str
    cells: List[TableCell] = field(default_factory=list)
    failed: bool = False
    failure_reason: Optional[str] = None
    raw_region: Optional[str] = None
    column_headers: List[str] = field(default_factory=list)
    row_headers: List[str] = field(default_factory=list)

    def get(self, row_id: str, col_id: str) -> Optional[str]:
        for cell in self.cells:
            if cell.row_id == row_id and cell.col_id == col_id:
                return cell.value
        return None

    def column(self, col_id: str) -> List[TableCell]:
        return [c for c in self.cells if c.col_id == col_id]

    def row(self, row_id: str) -> List[TableCell]:
        return [c for c in self.cells if c.row_id == row_id]

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "strategy": self.detection_strategy,
            "failed": self.failed,
            "columns": self.column_headers,
            "rows": self.row_headers,
            "cells": [{"r": c.row_id, "c": c.col_id, "v": c.value} for c in self.cells],
        }


# ---------------------------------------------------------------------------
# Known UAD table headers (observed in real test documents)
# ---------------------------------------------------------------------------

# Comparable sale grid column identifiers
COMP_COLUMN_HEADERS = [
    "SUBJECT", "COMPARABLE SALE # 1", "COMPARABLE SALE # 2",
    "COMPARABLE SALE # 3", "COMPARABLE SALE # 4",
    "COMPARABLE SALE #1", "COMPARABLE SALE #2", "COMPARABLE SALE #3",
    "COMP 1", "COMP 2", "COMP 3",
]

# UAD comparable sale row identifiers (features)
COMP_ROW_IDENTIFIERS = [
    "Address", "Proximity to Subject", "Sale Price", "Data Source(s)",
    "Verification Source(s)", "Sales or Financing Concessions", "Date of Sale/Time",
    "Location", "Leasehold/Fee Simple", "Site", "View", "Design (Style)",
    "Quality of Construction", "Actual Age", "Condition",
    "Above Grade", "Gross Living Area", "Basement & Finished Rooms Below Grade",
    "Functional Utility", "Heating/Cooling", "Energy Efficient Items",
    "Garage/Carport", "Porch/Patio/Deck", "Net Adjustment (Total)",
    "Adjusted Sale Price",
]

# Neighborhood section table rows
NEIGHBORHOOD_ROW_IDENTIFIERS = [
    "One-Unit", "2-4 Unit", "Multi-Family", "Commercial", "Other",
    "Price Low", "Price High", "Predominant",
    "Age Low", "Age High",
]


# ---------------------------------------------------------------------------
# Strategy A — Line-based table detection (bordered tables)
# ---------------------------------------------------------------------------

def _detect_line_based(page, page_number: int, table_id_prefix: str) -> List[StructuredTable]:
    """
    Use PyMuPDF drawing commands to detect table borders (horizontal + vertical lines).
    Returns structured tables for bordered grids. Only works on digital PDF pages.
    """
    tables: List[StructuredTable] = []
    try:
        # Get drawing commands (rectangles and lines indicate table borders)
        drawings = page.get_drawings()
        if not drawings:
            return tables

        # Look for rectangular regions (table borders)
        rects = []
        for d in drawings:
            if d.get("type") in ("re", "curve") or "rect" in d:
                r = d.get("rect")
                if r and r.width > 50 and r.height > 10:
                    rects.append(r)

        if len(rects) < 4:
            return tables

        # Find the bounding box of all detected rectangles
        # (simplified: treat as one table region)
        all_x0 = min(r.x0 for r in rects)
        all_y0 = min(r.y0 for r in rects)
        all_x1 = max(r.x1 for r in rects)
        all_y1 = max(r.y1 for r in rects)

        # Extract text within the table region
        table_rect = page.rect & fitz.Rect(all_x0, all_y0, all_x1, all_y1)
        if not table_rect.is_empty:
            region_text = page.get_text("text", clip=table_rect) or ""
            if region_text.strip():
                table = StructuredTable(
                    table_id=f"{table_id_prefix}_line",
                    page_number=page_number,
                    detection_strategy="line",
                    raw_region=region_text,
                )
                # Parse the region text as a simple grid
                _parse_text_grid(table, region_text)
                tables.append(table)

    except Exception as exc:
        logger.debug("Line-based table detection failed on page %d: %s", page_number, exc)

    return tables


# ---------------------------------------------------------------------------
# Strategy B — Whitespace-based column detection
# ---------------------------------------------------------------------------

def _detect_whitespace_based(page_text: str, page_number: int, table_id_prefix: str) -> List[StructuredTable]:
    """
    Detect tables by finding consistent whitespace gaps across multiple lines.
    Targets neighborhood percentage tables and fee schedules.
    """
    tables: List[StructuredTable] = []
    lines = page_text.split("\n")
    if len(lines) < 3:
        return tables

    # Find runs of lines where multiple columns are separated by 2+ spaces
    # A table run has at least 3 consecutive lines with the same gap positions
    _RE_COL_SEP = re.compile(r"  +")

    def _gap_positions(line: str) -> List[int]:
        return [m.start() for m in _RE_COL_SEP.finditer(line)]

    # Sliding window: look for 3+ consecutive lines with similar gap positions
    table_start = None
    prev_gaps = None
    candidate_lines = []

    for idx, line in enumerate(lines):
        if not line.strip():
            if candidate_lines and len(candidate_lines) >= 3:
                # End of a table candidate
                table = _build_whitespace_table(candidate_lines, page_number, table_id_prefix)
                if table:
                    tables.append(table)
            candidate_lines = []
            prev_gaps = None
            continue

        gaps = _gap_positions(line)
        if not gaps:
            if candidate_lines and len(candidate_lines) >= 3:
                table = _build_whitespace_table(candidate_lines, page_number, table_id_prefix)
                if table:
                    tables.append(table)
            candidate_lines = []
            prev_gaps = None
            continue

        if prev_gaps is None:
            prev_gaps = gaps
            candidate_lines = [line]
        elif _gaps_similar(gaps, prev_gaps):
            candidate_lines.append(line)
        else:
            if len(candidate_lines) >= 3:
                table = _build_whitespace_table(candidate_lines, page_number, table_id_prefix)
                if table:
                    tables.append(table)
            candidate_lines = [line]
            prev_gaps = gaps

    if candidate_lines and len(candidate_lines) >= 3:
        table = _build_whitespace_table(candidate_lines, page_number, table_id_prefix)
        if table:
            tables.append(table)

    return tables


def _gaps_similar(g1: List[int], g2: List[int], tolerance: int = 5) -> bool:
    if len(g1) != len(g2):
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(g1, g2))


def _build_whitespace_table(lines: List[str], page_number: int, prefix: str) -> Optional[StructuredTable]:
    """Build a StructuredTable from whitespace-aligned lines."""
    if not lines:
        return None

    table = StructuredTable(
        table_id=f"{prefix}_ws_{page_number}",
        page_number=page_number,
        detection_strategy="whitespace",
        raw_region="\n".join(lines),
    )

    # Split each line by 2+ whitespace
    col_sep = re.compile(r"  +")
    for row_idx, line in enumerate(lines):
        parts = [p.strip() for p in col_sep.split(line) if p.strip()]
        if not parts:
            continue
        row_id = f"R{row_idx + 1}"
        for col_idx, part in enumerate(parts):
            col_id = f"C{col_idx + 1}"
            table.cells.append(TableCell(row_id=row_id, col_id=col_id, value=part, raw_text=part))

    if table.cells:
        return table
    return None


# ---------------------------------------------------------------------------
# Strategy C — Header-based inference (UAD comparable sale grids)
# ---------------------------------------------------------------------------

# Patterns for finding comp grid sections in the text
_COMP_SECTION_MARKERS = [
    r"SALES COMPARISON APPROACH",
    r"COMPARABLE SALE #\s*1",
    r"FEATURE\s+SUBJECT",
]

_COMP_COL_PATTERN = re.compile(
    r"(?:COMPARABLE\s+SALE\s+#?\s*(\d+)|SUBJECT)",
    re.IGNORECASE,
)


def _detect_header_based(page_text: str, page_number: int, table_id_prefix: str) -> List[StructuredTable]:
    """
    Detect UAD comparable sale grids by finding column headers.
    The subject column + 3 comparable columns are the standard structure.
    """
    tables: List[StructuredTable] = []
    text_upper = page_text.upper()

    # Check if this page has a comparable sale grid
    has_comp_grid = any(
        re.search(marker, text_upper) for marker in _COMP_SECTION_MARKERS
    )
    if not has_comp_grid:
        return tables

    # Try to extract the comparable grid
    table = _parse_comp_grid(page_text, page_number, table_id_prefix)
    if table:
        tables.append(table)

    return tables


def _parse_comp_grid(page_text: str, page_number: int, prefix: str) -> Optional[StructuredTable]:
    """
    Parse the UAD comparable sale grid from page text.
    The UAD 1004 form (as seen in MSL/Equity Solutions appraisals) outputs data
    values BEFORE the form labels in the PDF text stream. This parser extracts
    the data section by looking for known label sequences.
    """
    table = StructuredTable(
        table_id=f"{prefix}_comp_grid",
        page_number=page_number,
        detection_strategy="header",
        column_headers=["Subject", "Comp1", "Comp2", "Comp3"],
        row_headers=list(COMP_ROW_IDENTIFIERS),
        raw_region=page_text[:2000],
    )

    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # Find the section that starts the comparable data
    # In UAD 1004, the first line with an address is often the subject
    address_lines = []
    for i, line in enumerate(lines):
        # Lines that look like addresses (contain common street abbreviations)
        if re.search(r"\b(St|Ave|Blvd|Dr|Rd|Ln|Ct|Way|Pl|Cir)\b", line, re.IGNORECASE):
            address_lines.append((i, line))

    if len(address_lines) >= 2:
        # First address = subject, next 2-3 = comparables
        subject_line = lines[address_lines[0][0]]
        table.cells.append(TableCell(
            row_id="Address", col_id="Subject", value=subject_line, raw_text=subject_line
        ))
        for comp_idx, (line_idx, addr_line) in enumerate(address_lines[1:4], 1):
            table.cells.append(TableCell(
                row_id="Address", col_id=f"Comp{comp_idx}", value=addr_line, raw_text=addr_line
            ))

    # Extract sale prices (lines that look like large dollar amounts)
    price_pattern = re.compile(r"\b(\d{2,3},\d{3})\b")
    price_lines = [(i, line) for i, line in enumerate(lines) if price_pattern.search(line)]
    if price_lines:
        # First price is typically the subject (if purchase), rest are comparables
        for idx, (_, line) in enumerate(price_lines[:4]):
            prices = price_pattern.findall(line)
            if prices:
                col = "Subject" if idx == 0 else f"Comp{idx}"
                table.cells.append(TableCell(
                    row_id="Sale Price", col_id=col, value=prices[0], raw_text=line
                ))

    if len(table.cells) < 2:
        table.failed = True
        table.failure_reason = "insufficient_data_extracted"

    return table


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

class TableDetector:
    """
    Runs all three detection strategies on each page and returns structured tables.
    Failures are graceful — failed tables carry the raw text for downstream fallback.
    """

    def detect_page(
        self,
        page_text: str,
        page_number: int,
        fitz_page=None,
    ) -> List[StructuredTable]:
        """
        Run all three strategies on a single page.
        Returns list of detected tables (may be empty).
        """
        tables: List[StructuredTable] = []
        prefix = f"p{page_number}"

        # Strategy A: line-based (requires fitz page object)
        if fitz_page is not None:
            try:
                import fitz
                line_tables = _detect_line_based(fitz_page, page_number, prefix)
                tables.extend(line_tables)
            except Exception as exc:
                logger.debug("Strategy A skipped on page %d: %s", page_number, exc)

        # Strategy B: whitespace-based (text only)
        try:
            ws_tables = _detect_whitespace_based(page_text, page_number, prefix)
            # Only add if not already captured by line-based
            if not tables:
                tables.extend(ws_tables)
        except Exception as exc:
            logger.debug("Strategy B failed on page %d: %s", page_number, exc)

        # Strategy C: header-based (comparable sale grid)
        try:
            header_tables = _detect_header_based(page_text, page_number, prefix)
            # Comparable grid gets priority — replace generic whitespace detection
            if header_tables:
                tables = [t for t in tables if t.detection_strategy != "whitespace"]
                tables.extend(header_tables)
        except Exception as exc:
            logger.debug("Strategy C failed on page %d: %s", page_number, exc)

        if tables:
            logger.debug(
                "Page %d: detected %d table(s) using strategies: %s",
                page_number,
                len(tables),
                [t.detection_strategy for t in tables],
            )

        return tables

    def detect_document(self, page_texts: Dict[int, str]) -> Dict[int, List[StructuredTable]]:
        """Run detection on all pages. Returns {page_number: [tables]}."""
        result: Dict[int, List[StructuredTable]] = {}
        for page_num, text in page_texts.items():
            tables = self.detect_page(text, page_num)
            if tables:
                result[page_num] = tables
        return result


def _parse_text_grid(table: StructuredTable, text: str) -> None:
    """Parse a simple text region as a row/column grid (fallback)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    col_sep = re.compile(r"\s{3,}")
    for row_idx, line in enumerate(lines):
        parts = [p.strip() for p in col_sep.split(line) if p.strip()]
        for col_idx, part in enumerate(parts):
            table.cells.append(TableCell(
                row_id=f"R{row_idx + 1}",
                col_id=f"C{col_idx + 1}",
                value=part,
                raw_text=part,
            ))


# Module-level singleton
table_detector = TableDetector()
