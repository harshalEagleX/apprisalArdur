"""Document quality signals used before trusting extraction output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DocumentQualityResult:
    status: str
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return self.status != "READABLE"


def score_text_quality(text: str | None, *, expected_terms: list[str] | None = None) -> DocumentQualityResult:
    """Classify whether extracted text is reliable enough for structured parsing."""
    raw = text or ""
    stripped = raw.strip()
    words = re.findall(r"[A-Za-z0-9$,.]{2,}", stripped)
    reasons: list[str] = []

    if len(stripped) < 500:
        reasons.append("too_few_extracted_characters")
    if len(words) < 100:
        reasons.append("too_few_extracted_words")
    if re.search(r"DocuSign\s+Envelope\s+ID", stripped, re.I) and not re.search(r"purchase\s+price|buyer|seller|property", stripped, re.I):
        reasons.append("signature_envelope_without_contract_body")

    expected = expected_terms or []
    missing_terms = [term for term in expected if not re.search(re.escape(term), stripped, re.I)]
    if expected and len(missing_terms) >= max(1, len(expected) - 1):
        reasons.append("expected_contract_terms_missing")

    if reasons:
        confidence = 0.15 if "signature_envelope_without_contract_body" in reasons else 0.35
        return DocumentQualityResult(status="OCR_LOW_CONFIDENCE", confidence=confidence, reasons=reasons)

    return DocumentQualityResult(status="READABLE", confidence=0.95, reasons=[])
