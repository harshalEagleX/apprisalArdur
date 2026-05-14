"""
FieldMetaResult — carries extracted value + full metadata for Phase 2.

Every field extracted in Phase 2 produces a FieldMetaResult that records:
  - The raw value OCR produced
  - The corrected value after OCR correction
  - Which page the field was found on
  - Whether a correction was applied
  - The extraction method used (spatial_anchor / regex / fallback)
  - The confidence score
  - Whether a sanity check failed and why

This data flows into the extracted_fields DB table and drives the learning loop.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ExtractionStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OCR_FAILED = "OCR_FAILED"
    PARSER_FAILED = "PARSER_FAILED"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    AMBIGUOUS = "AMBIGUOUS"
    PARTIAL_MATCH = "PARTIAL_MATCH"


MISSING_VALUE_SENTINELS = {"__NOT_FOUND__", "__NOT_PROVIDED__", "__NO_EXTRACTED_VALUE__", "__NO_EXPECTED_VALUE__"}


@dataclass
class FieldMetaResult:
    """Metadata for a single extracted field."""

    field_name: str

    # Raw value from OCR (before any correction)
    raw_value: Optional[str] = None

    # Final value after OCR correction (None if not found)
    corrected_value: Optional[str] = None

    # Confidence score 0.0–1.0
    confidence: float = 0.0

    # Which PDF page the value was found on (1-indexed)
    source_page: Optional[int] = None

    # Normalized field location on the source page. These are 0.0-1.0 values
    # and may be approximate when derived from text-only extraction.
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None

    # True if apply_ocr_correction() changed the raw value
    correction_applied: bool = False

    # How the field was extracted
    # "spatial_anchor"  — found near a known section header
    # "regex_primary"   — matched first (most specific) regex pattern
    # "regex_fallback"  — matched a weaker fallback pattern
    # "not_found"       — no pattern matched
    extraction_method: str = "not_found"

    # Sanity check flags (set by cross-field validation)
    sanity_check_failed: bool = False
    sanity_check_reason: Optional[str] = None

    # Cross-document validation (P2.8): True when this field's value has been
    # compared against an external document (engagement letter, public record)
    # and the values matched.  Used as a training signal for the learning loop —
    # a field that matched cross-document evidence is more reliable than one that
    # was only found in the appraisal text.
    cross_validated: bool = False
    cross_validated_source: Optional[str] = None   # e.g. "engagement_letter"

    extraction_status: ExtractionStatus | str | None = None
    source_document: Optional[str] = None
    parser: Optional[str] = None
    normalization_steps: list[str] = field(default_factory=list)
    failure_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.extraction_status is None:
            if self.value is None:
                self.confidence = 0.0
                self.extraction_status = ExtractionStatus.NOT_FOUND
            elif self.effective_confidence < 0.50:
                self.extraction_status = ExtractionStatus.LOW_CONFIDENCE
            else:
                self.extraction_status = ExtractionStatus.FOUND
        elif isinstance(self.extraction_status, str):
            normalized = self.extraction_status.upper()
            if normalized == "NOT_FOUND":
                self.extraction_status = ExtractionStatus.NOT_FOUND
            elif normalized == "LOW_CONFIDENCE":
                self.extraction_status = ExtractionStatus.LOW_CONFIDENCE
            else:
                self.extraction_status = ExtractionStatus(normalized)

        if self.parser is None:
            self.parser = self.extraction_method

        if self.value is None:
            self.confidence = 0.0

        if self.value is None and not self.failure_reason:
            self.failure_reason = "Field was not found by the configured extraction strategies."

    @property
    def value(self) -> Optional[str]:
        """The best available value (corrected if available, else raw)."""
        value = self.corrected_value if self.corrected_value is not None else self.raw_value
        if isinstance(value, str) and value.strip().upper() in MISSING_VALUE_SENTINELS:
            return None
        return value

    @property
    def effective_confidence(self) -> float:
        """Confidence after sanity-check penalty."""
        if self.value is None:
            return 0.0
        if self.sanity_check_failed:
            return max(0.0, self.confidence - 0.25)
        return self.confidence

    def to_db_dict(self) -> dict:
        """Return dict matching extracted_fields table columns."""
        return {
            "field_name": self.field_name,
            "field_value": self.value,
            "extraction_status": self.extraction_status.value if isinstance(self.extraction_status, ExtractionStatus) else self.extraction_status,
            "confidence_score": round(self.effective_confidence, 3),
            "source_document": self.source_document,
            "source_page": self.source_page,
            "bbox_x": self.bbox_x,
            "bbox_y": self.bbox_y,
            "bbox_w": self.bbox_w,
            "bbox_h": self.bbox_h,
            "parser": self.parser,
            "extraction_method": self.extraction_method,
            "raw_ocr_text": self.raw_value,
            "normalization_steps": json.dumps(self.normalization_steps or []),
            "failure_reason": self.failure_reason,
            "correction_applied": self.correction_applied,
            # P2.8: cross-document validation signal for the ML training loop.
            # A field confirmed against an external source is a high-quality
            # training example — both the extracted value and the confidence
            # calibration can be used as positive labels.
            "cross_validated": self.cross_validated,
            "cross_validated_source": self.cross_validated_source,
        }
