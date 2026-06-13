"""
Day 2 — Structured Extraction Result Format

Every extraction attempt for every field must return an ExtractionResult.
Every document produces an ExtractionResultSet.

This is the output contract between extraction tiers and all downstream
components (validation, routing, reviewer display, DB persistence, ML training).

Rules:
  - confidence is always 0.0–1.0 (never left as default 0.0 when found)
  - source_page is always set (1-indexed)
  - extraction_method always identifies exactly how the value was found
  - raw_source_text is the verbatim OCR passage the value came from
  - found=False still produces a complete result (not None, not missing)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List, Optional, Tuple


class ExtractionMethod(str, Enum):
    EXACT_LABEL_MATCH   = "exact_label_match"    # label matched exactly (case-insensitive)
    SYNONYM_MATCH       = "synonym_match"         # label matched a known synonym
    DATA_PATTERN_ONLY   = "data_pattern_only"     # found by value shape (zip, currency, date)
    POSITIONAL_ANCHOR   = "positional_anchor"     # found relative to section header position
    FUZZY_LABEL_MATCH   = "fuzzy_label_match"     # approximate label match (Week 2)
    EMBEDDING_MATCH     = "embedding_match"       # semantic vector similarity (Week 3 Tier 2)
    LLM_INFERENCE       = "llm_inference"         # LLM returned this value (Week 3 Tier 1)
    TIER_MERGED         = "tier_merged"           # merged output from multiple tiers
    NOT_FOUND           = "not_found"             # no extraction succeeded


class RoutingDecision(str, Enum):
    AUTO_ACCEPT     = "auto_accept"     # confidence ≥ auto_accept threshold
    OPTIONAL_REVIEW = "optional_review" # review threshold ≤ confidence < auto_accept
    MANDATORY_REVIEW = "mandatory_review" # confidence < review threshold
    NOT_FOUND       = "not_found"       # field was not found at all


@dataclass
class ExtractionResult:
    """
    The atomic output of one extraction attempt for one field.

    Every field in every document produces exactly one ExtractionResult,
    even when not found. Downstream systems never need to handle None.
    """

    # Identity
    canonical_name: str
    document_type: str                  # "appraisal_report" | "engagement_letter" | "sales_contract"

    # Value — None means the field was not found
    value: Optional[str] = None         # normalized/corrected value
    raw_source_text: Optional[str] = None  # verbatim OCR passage the value was extracted from

    # Provenance — all four MUST be set, never left as defaults when found
    extraction_method: str = ExtractionMethod.NOT_FOUND
    confidence: float = 0.0             # 0.0–1.0, computed — never the default when found
    source_page: int = 0                # 1-indexed PDF page number (0 = unknown)
    char_start: Optional[int] = None    # character offset within page text

    # Positional anchor for reviewer click-to-scroll. Normalized to the page's
    # own width/height as fractions in [0,1] with a TOP-LEFT origin — the exact
    # convention the PDF viewer expects (it multiplies each by 100% of the page
    # container, so the highlight is zoom-independent). None means "value not
    # located on the page" → the reviewer scrolls to the page without a box.
    # Keys: {"x", "y", "w", "h"}. Stamped by app.extraction.field_locator after
    # extraction; extractors themselves never set it (separation of concerns).
    bbox: Optional[Dict[str, float]] = None

    # Normalization audit trail
    normalization_applied: List[str] = field(default_factory=list)

    # Quality flags
    sanity_check_failed: bool = False
    sanity_check_reason: Optional[str] = None
    hallucination_flag: bool = False    # value returned by LLM but not verifiable in source text

    # Cross-document validation (set after consistency check pass)
    cross_validated: bool = False
    cross_validated_source: Optional[str] = None  # e.g. "engagement_letter"

    # Routing (computed after confidence thresholds are applied)
    routing: Optional[str] = None       # RoutingDecision value

    @property
    def found(self) -> bool:
        return self.value is not None

    @property
    def effective_confidence(self) -> float:
        """Confidence after sanity-check penalty (-0.25) and hallucination penalty (-0.40)."""
        c = self.confidence
        if self.sanity_check_failed:
            c = max(0.0, c - 0.25)
        if self.hallucination_flag:
            c = max(0.0, c - 0.40)
        return round(c, 3)

    def to_db_dict(self) -> Dict:
        """Row dict matching the extraction_results table schema (Day 3)."""
        return {
            "canonical_name":       self.canonical_name,
            "document_type":        self.document_type,
            "field_value":          self.value,
            "raw_source_text":      self.raw_source_text,
            "extraction_method":    self.extraction_method,
            "confidence_score":     self.effective_confidence,
            "source_page":          self.source_page,
            "char_start":           self.char_start,
            "normalization_steps":  self.normalization_applied,
            "sanity_check_failed":  self.sanity_check_failed,
            "sanity_check_reason":  self.sanity_check_reason,
            "hallucination_flag":   self.hallucination_flag,
            "cross_validated":      self.cross_validated,
            "cross_validated_source": self.cross_validated_source,
            "routing":              self.routing,
        }

    def __repr__(self) -> str:
        status = f"'{self.value}' @{self.effective_confidence:.2f}" if self.found else "NOT_FOUND"
        return f"ExtractionResult({self.canonical_name}={status} via {self.extraction_method} p{self.source_page})"


@dataclass
class ExtractionResultSet:
    """
    Complete set of extraction results for one document.

    One per document processed — holds every field attempted, found or not.
    The contract says: if a field is in the schema, it has an entry here.
    """

    document_path: str
    document_type: str          # "appraisal_report" | "engagement_letter" | "sales_contract"
    amc_id: Optional[str] = None
    total_pages: int = 0
    extraction_time_ms: int = 0
    ocr_method: str = "pymupdf"  # "pymupdf" | "tesseract" | "hybrid"

    _results: Dict[str, ExtractionResult] = field(default_factory=dict, repr=False)
    _started: float = field(default_factory=time.time, repr=False)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, result: ExtractionResult) -> None:
        self._results[result.canonical_name] = result

    def finalize(self) -> None:
        """Stamp extraction_time_ms."""
        self.extraction_time_ms = int((time.time() - self._started) * 1000)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, canonical: str) -> Optional[ExtractionResult]:
        return self._results.get(canonical)

    def value(self, canonical: str) -> Optional[str]:
        r = self._results.get(canonical)
        return r.value if r else None

    def all_results(self) -> List[ExtractionResult]:
        return list(self._results.values())

    def found_results(self) -> List[ExtractionResult]:
        return [r for r in self._results.values() if r.found]

    def not_found_results(self) -> List[ExtractionResult]:
        return [r for r in self._results.values() if not r.found]

    def by_section(self, section: str, schema) -> Dict[str, ExtractionResult]:
        """Return results for fields belonging to a given section."""
        section_fields = {f.canonical_name for f in schema.fields_for_section(section)}
        return {k: v for k, v in self._results.items() if k in section_fields}

    def low_confidence(self, threshold: float = 0.65) -> List[ExtractionResult]:
        return [r for r in self._results.values() if r.found and r.effective_confidence < threshold]

    def required_missing(self, schema) -> List[str]:
        """Fields marked required* that are not found."""
        missing = []
        for f in schema.all_fields():
            if f.required in ("required", "required_cross_document"):
                r = self._results.get(f.canonical_name)
                if not r or not r.found:
                    missing.append(f.canonical_name)
        return missing

    def summary(self) -> Dict:
        found = [r for r in self._results.values() if r.found]
        return {
            "document_type": self.document_type,
            "total_pages": self.total_pages,
            "fields_attempted": len(self._results),
            "fields_found": len(found),
            "fields_not_found": len(self._results) - len(found),
            "avg_confidence": round(
                sum(r.effective_confidence for r in found) / len(found), 3
            ) if found else 0.0,
            "extraction_time_ms": self.extraction_time_ms,
            "ocr_method": self.ocr_method,
        }

    def __iter__(self) -> Iterator[Tuple[str, ExtractionResult]]:
        return iter(self._results.items())

    def __len__(self) -> int:
        return len(self._results)
