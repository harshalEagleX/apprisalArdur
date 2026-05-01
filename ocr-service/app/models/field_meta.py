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

from dataclasses import dataclass, field
from typing import Optional


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

    @property
    def value(self) -> Optional[str]:
        """The best available value (corrected if available, else raw)."""
        return self.corrected_value if self.corrected_value is not None else self.raw_value

    @property
    def effective_confidence(self) -> float:
        """Confidence after sanity-check penalty."""
        if self.sanity_check_failed:
            return max(0.0, self.confidence - 0.25)
        return self.confidence

    def to_db_dict(self) -> dict:
        """Return dict matching extracted_fields table columns."""
        return {
            "field_name": self.field_name,
            "field_value": self.value,
            "confidence_score": round(self.effective_confidence, 3),
            "source_page": self.source_page,
            "bbox_x": self.bbox_x,
            "bbox_y": self.bbox_y,
            "bbox_w": self.bbox_w,
            "bbox_h": self.bbox_h,
            "extraction_method": self.extraction_method,
            "raw_ocr_text": self.raw_value,
            "correction_applied": self.correction_applied,
        }
