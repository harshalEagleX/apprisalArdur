"""
Layer 2 — Grid / Table Field Resolver

Uses pdfplumber's table extraction to read grid data that the spatial
text-label matcher can never reach: the UAD neighborhood grid, the
comparable sale adjustment grid, the land-use percentage table.

The UAD 1004 form has these tables where values are at row × column
intersections — a cell has no nearby label, only a row header and a column header.

Fields this fixes (all currently at 0%):
  N-3  price_low, price_high, predominant_price
       age_low, age_high, predominant_age
  N-4  land_use_one_unit, land_use_2_4_unit, land_use_multi_family,
       land_use_commercial, land_use_other, land_use_total

Additional grids:
  SCA  comp_N_sale_price, comp_N_gla, comp_N_net_adjustment,
       comp_N_adjusted_sale_price (for N=1,2,3)

Output: {canonical_field_name: value_string}
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Neighborhood price/age grid detection keywords
_PRICE_GRID_KEYWORDS = ["price", "pred.", "predominant", "low", "high"]
_AGE_GRID_KEYWORDS   = ["age", "yrs", "pred.", "predominant"]
_LAND_USE_KEYWORDS   = ["one-unit", "2-4 unit", "multi-family", "commercial", "other"]


def _clean_number(text: Optional[str]) -> Optional[str]:
    """Strip formatting and return the numeric string."""
    if not text:
        return None
    cleaned = re.sub(r"[$,%\s]", "", str(text).strip())
    if not cleaned or cleaned in ("", "N/A", "n/a", "-"):
        return None
    try:
        float(cleaned)
        return cleaned
    except ValueError:
        return None


def _table_contains_any(table: List[List], keywords: List[str]) -> bool:
    """Check if any cell in the table contains any of the keywords."""
    flat = [str(cell or "").lower() for row in table for cell in row]
    return any(any(kw.lower() in cell for kw in keywords) for cell in flat)


def _extract_price_age_grid(table: List[List]) -> Dict[str, str]:
    """
    Parse the UAD neighborhood price/age grid.

    Real UAD 1004 layout — PRICE and AGE are SEPARATE columns,
    with Low/High/Pred. as ROW labels:

        | One-Unit Housing |  PRICE $(000)  |  AGE (yrs) |
        | Low              |      220       |      0     |
        | High             |    1,750       |     76     |
        | Pred.            |      400       |     40     |

    We anchor on:
      - the header row (find which column is PRICE, which is AGE)
      - the label column (find which row is Low / High / Pred.)
    Then read each cell at the intersection. Numbers <5000 only — that
    excludes 6-digit comp sale prices that may bleed into adjacent tables.
    """
    results: Dict[str, str] = {}
    if not table or len(table) < 2:
        return results

    # 1. Locate header row and column indices for PRICE and AGE.
    price_col = age_col = None
    header_row_idx = None
    for r_idx, row in enumerate(table[:4]):  # header is in the top of the table
        for c_idx, cell in enumerate(row):
            t = str(cell or "").lower()
            if price_col is None and "price" in t and "000" in t.replace(" ", ""):
                price_col = c_idx
                header_row_idx = r_idx
            elif price_col is None and t.strip() == "price":
                price_col = c_idx
                header_row_idx = r_idx
            if age_col is None and ("age" in t and ("yrs" in t or t.strip() == "age")):
                age_col = c_idx
                if header_row_idx is None:
                    header_row_idx = r_idx
        if price_col is not None and age_col is not None:
            break

    # If we can't find both columns, this table is not the price/age grid.
    if price_col is None and age_col is None:
        return results
    if header_row_idx is None:
        header_row_idx = 0

    # 2. For each data row below the header, find its Low/High/Pred. label
    #    and read the value at the PRICE and AGE columns.
    row_label_map = {
        "low": ("price_low", "age_low"),
        "high": ("price_high", "age_high"),
        "pred": ("predominant_price", "predominant_age"),
        "pred.": ("predominant_price", "predominant_age"),
        "predominant": ("predominant_price", "predominant_age"),
    }

    for row in table[header_row_idx + 1:]:
        # Find a Low / High / Pred. label anywhere in this row.
        row_label = None
        for cell in row:
            t = str(cell or "").strip().lower().rstrip(".")
            if t in ("low", "high", "pred", "predominant"):
                row_label = "pred" if t in ("pred", "predominant") else t
                break
        if not row_label:
            continue

        price_field, age_field = row_label_map[row_label]

        if price_col is not None and price_col < len(row):
            v = _clean_number(row[price_col])
            # Neighborhood price is in $000; sanity range 1..5000.
            if v and 1 <= float(v) < 5000 and price_field not in results:
                results[price_field] = v

        if age_col is not None and age_col < len(row):
            v = _clean_number(row[age_col])
            # Age in years; sanity range 0..200.
            if v and 0 <= float(v) <= 200 and age_field not in results:
                results[age_field] = v

    return results


def _extract_land_use(table: List[List]) -> Dict[str, str]:
    """
    Parse the UAD land use percentage table.
    Format:
      One-Unit:       90 %
      2-4 Unit:        5 %
      Multi-Family:    3 %
      Commercial:      2 %
      Other:           0 %
    """
    results = {}
    field_map = {
        "one-unit": "land_use_one_unit",
        "one unit": "land_use_one_unit",
        "2-4 unit": "land_use_2_4_unit",
        "2-4 units": "land_use_2_4_unit",
        "multi-family": "land_use_multi_family",
        "multi family": "land_use_multi_family",
        "commercial": "land_use_commercial",
        "other": "land_use_other",
    }

    for row in table:
        texts = [str(c or "").strip() for c in row]
        if len(texts) < 2:
            continue
        label = texts[0].lower().strip()
        # Land use values must be 0–100 (percentage), reject text values
        value_str = next((
            _clean_number(t) for t in texts[1:]
            if _clean_number(t) and 0 <= float(_clean_number(t)) <= 100
        ), None)
        if not value_str:
            continue
        for key, field_name in field_map.items():
            if key in label:
                results[field_name] = value_str
                break

    # Derive total
    total = sum(
        float(v) for k, v in results.items()
        if k.startswith("land_use_") and k != "land_use_total"
        and v is not None
    )
    if total > 0:
        results["land_use_total"] = str(round(total, 1))

    return results


def _extract_comparable_grid(table: List[List]) -> Dict[str, str]:
    """
    Parse the UAD comparable sale adjustment grid.
    Finds sale prices, GLA, net adjustments, adjusted sale prices
    for comparables 1, 2, 3.
    """
    results = {}

    # Look for the "Sale Price" row
    for row in table:
        texts = [str(c or "").strip() for c in row]
        row_text = " ".join(texts).lower()

        if "sale price" in row_text and "$" in row_text:
            prices = [_clean_number(t) for t in texts[1:] if _clean_number(t)]
            for i, price in enumerate(prices[:3], 1):
                if price:
                    results[f"comp_{i}_sale_price"] = price

        elif "gross living area" in row_text or "gla" in row_text:
            glas = [_clean_number(t) for t in texts[1:] if _clean_number(t)]
            for i, gla in enumerate(glas[:3], 1):
                if gla:
                    results[f"comp_{i}_gla"] = gla

        elif "net adj" in row_text or "net adjustment" in row_text:
            adjs = [_clean_number(t) for t in texts[1:] if _clean_number(t)]
            for i, adj in enumerate(adjs[:3], 1):
                if adj:
                    results[f"comp_{i}_net_adjustment"] = adj

        elif "adjusted sale price" in row_text or "indicated value" in row_text:
            adj_prices = [_clean_number(t) for t in texts[1:] if _clean_number(t)]
            for i, p in enumerate(adj_prices[:3], 1):
                if p:
                    results[f"comp_{i}_adjusted_sale_price"] = p

    return results


def extract_grid_fields(pdf_path: Path, max_pages: int = 12) -> Dict[str, str]:
    """
    Extract grid/table fields using pdfplumber's bordered table detection.
    Runs on all pages up to max_pages and returns all found field values.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available — Layer 2 grid resolver skipped")
        return {}

    results: Dict[str, str] = {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_to_scan = min(max_pages, len(pdf.pages))

            for page_num in range(pages_to_scan):
                page = pdf.pages[page_num]

                # Try multiple table detection strategies
                for strategy in [
                    {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
                    {"vertical_strategy": "text", "horizontal_strategy": "text",
                     "snap_tolerance": 5, "join_tolerance": 5},
                    {"vertical_strategy": "lines", "horizontal_strategy": "text"},
                ]:
                    try:
                        tables = page.extract_tables(strategy)
                    except Exception:
                        tables = []

                    for table in (tables or []):
                        if not table or len(table) < 2:
                            continue

                        # Price/Age grid
                        if _table_contains_any(table, _PRICE_GRID_KEYWORDS):
                            found = _extract_price_age_grid(table)
                            if found:
                                results.update({k: v for k, v in found.items()
                                                if k not in results})

                        # Land use table
                        if _table_contains_any(table, _LAND_USE_KEYWORDS):
                            found = _extract_land_use(table)
                            if found:
                                results.update({k: v for k, v in found.items()
                                                if k not in results})

                        # Comparable sales grid
                        flat = " ".join(str(c or "").lower() for row in table for c in row)
                        if "sale price" in flat and "comparable" in flat:
                            found = _extract_comparable_grid(table)
                            if found:
                                results.update({k: v for k, v in found.items()
                                                if k not in results})

    except Exception as exc:
        logger.warning("pdfplumber grid extraction failed for %s: %s", pdf_path.name, exc)

    if results:
        logger.info(
            "L2 grid resolver: %s — found %d fields: %s",
            pdf_path.name, len(results), list(results.keys())[:8],
        )
    return results
