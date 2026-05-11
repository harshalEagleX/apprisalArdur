"""Hybrid purchase-agreement extraction.

The parser combines document quality checks, label/anchor extraction, and
signature-aware date selection. It intentionally returns missing fields instead
of guessing from unrelated dates such as closing dates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.models.appraisal import PurchaseAgreement
from app.services.document_quality import DocumentQualityResult, score_text_quality


@dataclass
class ContractCandidate:
    field_name: str
    value: str
    confidence: float
    method: str
    evidence: str


@dataclass
class PurchaseAgreementExtraction:
    agreement: PurchaseAgreement
    quality: DocumentQualityResult
    candidates: list[ContractCandidate] = field(default_factory=list)


class HybridContractExtractor:
    def extract(self, text: str | None) -> PurchaseAgreementExtraction:
        raw = text or ""
        quality = score_text_quality(raw, expected_terms=["Buyer", "Seller", "Purchase Price"])
        agreement = PurchaseAgreement()
        candidates: list[ContractCandidate] = []

        if quality.status != "READABLE":
            return PurchaseAgreementExtraction(agreement=agreement, quality=quality, candidates=candidates)

        price = self._extract_price(raw)
        if price:
            agreement.contract_price = self._parse_money(price.value)
            candidates.append(price)

        date = self._extract_contract_date(raw)
        if date:
            agreement.contract_date = self._normalize_date(date.value)
            candidates.append(date)

        seller = self._extract_seller(raw)
        if seller:
            agreement.seller_name = seller.value
            candidates.append(seller)

        concessions = self._extract_concessions(raw, agreement.contract_price)
        if concessions:
            agreement.concessions_amount = self._parse_money(concessions.value)
            candidates.append(concessions)

        agreement.personal_property_items = self._extract_personal_property(raw)
        if agreement.personal_property_items:
            candidates.append(ContractCandidate(
                field_name="personal_property_items",
                value=", ".join(agreement.personal_property_items),
                confidence=0.82,
                method="anchor_block",
                evidence="Personal property clause",
            ))

        return PurchaseAgreementExtraction(agreement=agreement, quality=quality, candidates=candidates)

    def _extract_price(self, text: str) -> ContractCandidate | None:
        for match in re.finditer(r"\bPurchase\s+Price\b", text, re.I):
            window = text[max(0, match.start() - 260): match.end() + 360]
            amounts = [
                amount for amount in (
                    self._parse_money(value)
                    for value in re.findall(r"[\$ ]\s*([\d,]+(?:\.\d{2})?)", window)
                )
                if amount is not None and 10_000 <= amount <= 10_000_000
            ]
            if amounts:
                value = f"{max(amounts):.2f}"
                return ContractCandidate("contract_price", value, 0.94, "purchase_price_anchor_window", window[:300])

        for line in text.splitlines():
            if not re.search(r"\bPurchase\s+Price\b", line, re.I):
                continue
            amounts = [
                amount for amount in (
                    self._parse_money(value)
                    for value in re.findall(r"[\$ ]\s*([\d,]+(?:\.\d{2})?)", line)
                )
                if amount is not None and 10_000 <= amount <= 10_000_000
            ]
            if amounts:
                value = f"{max(amounts):.2f}"
                return ContractCandidate("contract_price", value, 0.94, "purchase_price_line", line[:300])

        patterns = [
            r"\bPurchase\s+Price\b[^\n$]{0,260}\$\s*_*\s*([\d,]+(?:\.\d{2})?)",
            r"\bPurchase\s+Price[:\s][^\n$]{0,260}\$\s*([\d,]+(?:\.\d{2})?)",
            r"\bBuyer\s+offers\s+to\s+buy\b[^\n$]{0,260}\$\s*([\d,]+(?:\.\d{2})?)",
            r"\bTotal\s+Purchase\s+Price\b[^\n$]{0,260}\$\s*([\d,]+(?:\.\d{2})?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.S)
            if match and self._parse_money(match.group(1)) and self._parse_money(match.group(1)) >= 10_000:
                return ContractCandidate("contract_price", match.group(1), 0.92, "price_anchor", match.group(0)[:300])
        return None

    def _extract_contract_date(self, text: str) -> ContractCandidate | None:
        explicit = [
            r"Binding\s+Agreement\s+Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
            r"(?:Fully\s+Executed|Final|Acceptance|Accepted|Effective)\s+Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
            r"Date\s+of\s+Last\s+Signature[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        ]
        for pattern in explicit:
            match = re.search(pattern, text, re.I)
            if match:
                return ContractCandidate("contract_date", match.group(1), 0.90, "explicit_effective_date", match.group(0))

        signature_dates: list[tuple[str, str]] = []
        for match in re.finditer(
            r"X\s*\((Buyer|Seller)[^)]{0,80}Signature[^)]*\):[^\n]*?(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{1,2}/\d{2})",
            text,
            re.I,
        ):
            signature_dates.append((match.group(1).lower(), match.group(2)))

        seller_dates = [date for role, date in signature_dates if role == "seller"]
        buyer_dates = [date for role, date in signature_dates if role == "buyer"]
        if seller_dates:
            chosen = max(seller_dates + buyer_dates, key=self._sortable_date)
            return ContractCandidate("contract_date", chosen, 0.86, "signature_date_window", chosen)

        # If only buyer dates were seen, do not guess the fully executed date.
        return None

    def _extract_seller(self, text: str) -> ContractCandidate | None:
        text = re.split(r"\bTEMPORARY\s+OCCUPANCY\b|\bOCCUPANCY\s+AGREEMENT\b", text, maxsplit=1, flags=re.I)[0]
        patterns = [
            r"PARTIES:[\s\S]{0,220}?([A-Z][A-Za-z ,&]+?)\s*\(\"Seller\"\)",
            r"X\s*\(Seller.?s\s+Signature[^\)]*\):\s*([A-Za-z][A-Za-z\s.'-]+?)\s{2,}\d{1,2}/\d{1,2}/\d{2,4}",
            r"\bSeller[:\s_]+([A-Za-z][A-Za-z\s,&.]+?)(?:\n|Buyer|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.S)
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip(" _.,")
                if 3 <= len(value) <= 120 and not re.search(r"\b(?:shall|buyer|read|signed|disclosure|property)\b", value, re.I):
                    return ContractCandidate("seller_name", value, 0.78, "seller_anchor", match.group(0)[:300])
        return None

    def _extract_concessions(self, text: str, price: float | None) -> ContractCandidate | None:
        money_patterns = [
            r"Seller'?s\s+Monetary\s+Contribution[^$]{0,120}\$\s*([\d,]+(?:\.\d{2})?)",
            r"Seller\s+(?:agrees\s+to\s+)?pay[^\n$]{0,120}\$\s*([\d,]+(?:\.\d{2})?)",
            r"Seller\s+(?:to\s+Pay|Contribution|Credit)[^\n$]{0,80}\$\s*([\d,]+(?:\.\d{2})?)",
        ]
        for pattern in money_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return ContractCandidate("concessions_amount", match.group(1), 0.78, "concession_money_anchor", match.group(0))

        percent_match = re.search(r"Seller\s+agrees\s+to\s+pay\s+([\d.]+)\s*%\s+of\s+purchase\s+price", text, re.I)
        if percent_match and price:
            amount = price * (float(percent_match.group(1)) / 100.0)
            return ContractCandidate("concessions_amount", f"{amount:.2f}", 0.72, "concession_percent_anchor", percent_match.group(0))
        return None

    def _extract_personal_property(self, text: str) -> list[str]:
        blocks: list[str] = []
        patterns = [
            r"Other\s+Personal\s+Property\s+items\s+included\s+in\s+this\s+purchase\s+are:\s*(.+?)\bPersonal\s+Property\s+is\s+included",
            r"also\s+includes:\s*(.+?)\n\s*but\s+does\s+not\s+include",
            r"(?:Personal\s+Property|Inclusions?|Items?\s+Included)[:\s]+([^\n]{10,300})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.S)
            if match:
                blocks.append(match.group(1))

        items: list[str] = []
        for block in blocks:
            cleaned = re.sub(r"[_\n]+", " ", block)
            cleaned = re.sub(r"\s+", " ", cleaned)
            for part in re.split(r"[,;]", cleaned):
                item = re.sub(r"^\d+\s*", "", part.strip(" .:_"))
                item = re.sub(r"\s+\d+$", "", item).strip()
                if 2 < len(item) <= 60 and not self._is_boilerplate(item):
                    items.append(item)
        return list(dict.fromkeys(items))

    def _parse_money(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(str(value).replace(",", "").replace("$", "").strip())
        except ValueError:
            return None

    def _normalize_date(self, value: str | None) -> str | None:
        if not value:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(value, fmt).strftime("%m/%d/%Y")
            except ValueError:
                pass
        return value

    def _sortable_date(self, value: str) -> str:
        normalized = self._normalize_date(value) or value
        try:
            return datetime.strptime(normalized, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return normalized

    def _is_boilerplate(self, value: str) -> bool:
        lower = value.lower()
        return any(token in lower for token in (
            "unless excluded",
            "paragraph",
            "property",
            "personal property is included",
            "purchase price",
            "no contributory value",
            "shall be left",
        ))


hybrid_contract_extractor = HybridContractExtractor()
