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
    Format:
      Row 0:                    PRICE $000    |    AGE (yrs)
      Row 1: One-Unit Housing:  Low  High Pred.  Low  High Pred.
      Row 2: (values)           220   340  275     0    5    1
    """
    results = {}

    # Find the data row (numbers)
    for row in table:
        texts = [str(c or "").strip() for c in row]
        nums = [_clean_number(t) for t in texts]

        # Neighborhood price range: values in $000 notation (max ~5000)
        # Filter out comp sale prices (6-digit full amounts)
        small_nums = [n for n in nums if n and float(n) < 5000]

        if len(small_nums) >= 3:
            # Map positions to field names based on column order
            # Typical layout: Low | High | Pred | Low | High | Pred
            num_positions = [(i, nums[i]) for i in range(len(nums))
                             if nums[i] and float(nums[i]) < 5000]
            if len(num_positions) >= 3:
                field_map = [
                    "price_low", "price_high", "predominant_price",
                    "age_low", "age_high", "predominant_age",
                ]
                for idx, (pos, val) in enumerate(num_positions[:6]):
                    if idx < len(field_map) and val:
                        results[field_map[idx]] = val
            break

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
