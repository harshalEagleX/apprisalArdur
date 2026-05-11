"""Structured comparable grid extraction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.appraisal import Comparable


@dataclass
class ComparableExtractionResult:
    comparables: list[Comparable]
    confidence: float
    method: str


class ComparableGridExtractor:
    def extract(self, text: str | None) -> ComparableExtractionResult:
        raw = text or ""
        prices = self._extract_sale_price_row(raw)
        if prices:
            return ComparableExtractionResult(
                comparables=[Comparable(sale_price=price) for price in prices[:6]],
                confidence=0.82,
                method="sales_grid_sale_price_row",
            )

        detail_prices = [
            self._parse_money(value)
            for value in re.findall(r"\bSale\s+Price\s+\$?\s*([\d,]{5,})\b", raw, re.I)
        ]
        detail_prices = [price for price in detail_prices if price is not None]
        if len(detail_prices) >= 3:
            return ComparableExtractionResult(
                comparables=[Comparable(sale_price=price) for price in detail_prices[:6]],
                confidence=0.62,
                method="detail_page_sale_price_labels",
            )

        return ComparableExtractionResult(comparables=[], confidence=0.0, method="not_found")

    def _extract_sale_price_row(self, text: str) -> list[float]:
        rows = re.findall(r"(?m)^\s*Sale\s+Price\s+(.+)$", text)
        for row in rows:
            amounts = [self._parse_money(v) for v in re.findall(r"\$?\s*([\d,]{5,}(?:\.\d{2})?)", row)]
            amounts = [amount for amount in amounts if amount is not None]
            if len(amounts) >= 4:
                # First amount is usually the subject contract/list price.
                return amounts[1:]
            if len(amounts) >= 3:
                return amounts
        return []

    def _parse_money(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace(",", "").replace("$", "").strip())
        except ValueError:
            return None


comparable_grid_extractor = ComparableGridExtractor()
