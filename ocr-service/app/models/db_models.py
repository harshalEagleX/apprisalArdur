"""
Days 3–7 + Week 4 — Python-owned database models

These tables belong to the Python OCR service.
Created/dropped via `python manage_db.py` (no Alembic, per CLAUDE.md policy).
Never touched by the Java Spring Boot service.

Tables:
  adaptive_extraction_results    — every field extraction attempt, permanent record
  adaptive_corrections           — every human reviewer correction
  adaptive_amc_profiles          — one row per AMC, grows with each document
  adaptive_amc_template_versions — one row per known AMC template version
  adaptive_field_schema_log      — schema version history
  adaptive_test_set              — Day 4 test set documents
  adaptive_test_ground_truth     — Day 4 manually verified correct field values
  adaptive_baseline_runs         — Day 4 baseline measurement snapshots
  adaptive_page_ocr_results      — Day 7 per-page OCR metadata and preprocessing log
  adaptive_document_classifications — Day 9 per-document classification results
"""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# adaptive_extraction_results
# ---------------------------------------------------------------------------

class ExtractionResultRow(Base):
    """
    Permanent record of every field extraction attempt on every document.
    Rows are never deleted — superseded extractions are tracked by run_id.
    This is the primary input to the ML training loop (P-5, P-10).
    """
    __tablename__ = "adaptive_extraction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Document identity
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    document_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)

    # Field extraction result
    field_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Normalization audit
    normalization_steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list

    # Quality flags
    sanity_check_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    sanity_check_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Cross-document validation result
    cross_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    cross_validated_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Routing decision
    routing: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Lineage
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Reviewer state
    reviewer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    has_correction: Mapped[bool] = mapped_column(Boolean, default=False)

    corrections: Mapped[list["CorrectionRow"]] = relationship(
        "CorrectionRow", back_populates="extraction_result"
    )


# ---------------------------------------------------------------------------
# adaptive_corrections
# ---------------------------------------------------------------------------

class CorrectionRow(Base):
    """
    Every correction a human reviewer makes on an extracted field.
    Every correction is a labeled training example (P-10, Rule 10).

    reason_category values:
      wrong_label_matched   — regex caught a label instead of a value
      ocr_error             — OCR garbled the source text
      value_wrong_location  — value found on wrong page/section
      completely_absent     — field is genuinely missing from document
      ambiguous_context     — multiple plausible values, wrong one chosen
      other                 — see explanation field
    """
    __tablename__ = "adaptive_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Links to the extraction that was corrected
    extraction_result_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("adaptive_extraction_results.id", ondelete="SET NULL"), nullable=True
    )
    extraction_result: Mapped[Optional[ExtractionResultRow]] = relationship(
        "ExtractionResultRow", back_populates="corrections"
    )

    # Document context
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # The correction itself
    original_extracted_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured reason — feeds the ML training loop
    reason_category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="other"
    )
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Which QC rule triggered this review (if known)
    rule_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Reviewer identity and timing
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    # Fast-path learning: has this correction already been applied to synonyms/thresholds?
    fast_path_applied: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# adaptive_amc_profiles
# ---------------------------------------------------------------------------

class AmcProfileRow(Base):
    """
    One row per AMC. Grows with each document processed.
    maturity_level: new (< 10 docs) | developing (10–49) | mature (50+)
    """
    __tablename__ = "adaptive_amc_profiles"
    __table_args__ = (UniqueConstraint("amc_id", name="uq_amc_profiles_amc_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amc_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amc_name: Mapped[str] = mapped_column(String(255), nullable=False)

    document_count: Mapped[int] = mapped_column(Integer, default=0)
    maturity_level: Mapped[str] = mapped_column(String(16), default="new")

    # Structural fingerprint for document classification (Day 9)
    fingerprint_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AMC-specific label → canonical field mappings (synonym overrides)
    terminology_mapping_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Per-field confidence threshold overrides for this AMC
    confidence_threshold_overrides_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    template_versions: Mapped[list["AmcTemplateVersionRow"]] = relationship(
        "AmcTemplateVersionRow", back_populates="profile"
    )

    def get_terminology_mapping(self) -> dict:
        return json.loads(self.terminology_mapping_json or "{}")

    def get_confidence_overrides(self) -> dict:
        return json.loads(self.confidence_threshold_overrides_json or "{}")

    def get_fingerprint(self) -> dict:
        return json.loads(self.fingerprint_json or "{}")


# ---------------------------------------------------------------------------
# adaptive_amc_template_versions
# ---------------------------------------------------------------------------

class AmcTemplateVersionRow(Base):
    """
    One row per known template version for an AMC.
    When a new document's fingerprint doesn't match existing versions → new row.
    """
    __tablename__ = "adaptive_amc_template_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("adaptive_amc_profiles.id", ondelete="CASCADE"), nullable=False
    )
    profile: Mapped[AmcProfileRow] = relationship(
        "AmcProfileRow", back_populates="template_versions"
    )

    amc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    structural_fingerprint_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# adaptive_field_schema_log
# ---------------------------------------------------------------------------

class FieldSchemaLogRow(Base):
    """
    Snapshot of the field schema at a point in time.
    Allows tracing which schema version was active when a given extraction was run.
    """
    __tablename__ = "adaptive_field_schema_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[str] = mapped_column(String(32), nullable=False)
    sections_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synonyms_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# adaptive_test_set  (Day 4)
# ---------------------------------------------------------------------------

class TestSetDocumentRow(Base):
    """
    Day 4: One row per document in the verified test set.
    Each document is linked to ground-truth field values.
    """
    __tablename__ = "adaptive_test_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    batch_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    amc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    document_path: Mapped[str] = mapped_column(Text, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    ground_truth_entries: Mapped[list["TestGroundTruthRow"]] = relationship(
        "TestGroundTruthRow", back_populates="test_document"
    )


# ---------------------------------------------------------------------------
# adaptive_test_ground_truth  (Day 4)
# ---------------------------------------------------------------------------

class TestGroundTruthRow(Base):
    """
    Day 4: Manually verified correct field values for each test set document.
    verified_by values: manual (human verified) | inferred (high-confidence from text)
    This is the authoritative truth used to measure extraction accuracy.
    """
    __tablename__ = "adaptive_test_ground_truth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("adaptive_test_set.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_document: Mapped[TestSetDocumentRow] = relationship(
        "TestSetDocumentRow", back_populates="ground_truth_entries"
    )

    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    correct_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False)

    # How confident we are in this ground truth entry
    # manual = human read the document, inferred = extracted from reliable text pattern
    verified_by: Mapped[str] = mapped_column(String(32), default="manual")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# adaptive_baseline_runs  (Day 4)
# ---------------------------------------------------------------------------

class BaselineRunRow(Base):
    """
    Day 4: One row per baseline measurement run.
    Weekly measurements go here so we can track improvement over time.
    """
    __tablename__ = "adaptive_baseline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_label: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    # Aggregate metrics
    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    total_fields_tested: Mapped[int] = mapped_column(Integer, default=0)
    fields_correct: Mapped[int] = mapped_column(Integer, default=0)
    fields_not_found: Mapped[int] = mapped_column(Integer, default=0)
    fields_wrong: Mapped[int] = mapped_column(Integer, default=0)

    # Field-level and AMC-level breakdown stored as JSON for queryability
    field_accuracy_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amc_accuracy_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_accuracy_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Overall rates
    field_accuracy_rate: Mapped[float] = mapped_column(Float, default=0.0)
    document_accuracy_rate: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# adaptive_page_ocr_results  (Day 7)
# ---------------------------------------------------------------------------

class PageOcrResultRow(Base):
    """
    Day 7: Per-page OCR metadata and preprocessing audit trail.

    For every page of every document processed:
    - Records whether direct PyMuPDF extraction or Tesseract was used
    - Records image quality assessment for scanned pages
    - Records which preprocessing steps were applied and in what order
    - Stores text quality score (used by confidence system to reduce field confidence
      on pages with poor OCR output)
    - Stores normalization transformation history (Day 8)
    """
    __tablename__ = "adaptive_page_ocr_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Which OCR path was used for this page
    ocr_path: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "pymupdf_direct" | "tesseract"

    # Word count BEFORE any preprocessing (used to decide which path to take)
    word_count_raw: Mapped[int] = mapped_column(Integer, default=0)
    # Word count AFTER OCR processing (quality signal)
    word_count_ocr: Mapped[int] = mapped_column(Integer, default=0)

    # Image quality assessment (only populated for scanned pages)
    dpi_estimated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_quality_flag: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )  # "low" | "normal" | "high"
    image_variance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Which preprocessing steps were applied (JSON list, ordered)
    preprocessing_steps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Text quality score 0.0-1.0 (estimated OCR accuracy)
    # Computed from: word_count_ocr/word_count_expected, character error indicators
    text_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Day 8: normalization transformation history (JSON list of {transform, before, after})
    normalization_log_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SHA-256 file hash — the dedup key for Rule 8 cache lookup
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Raw text character length before and after normalization
    raw_text_length: Mapped[int] = mapped_column(Integer, default=0)
    normalized_text_length: Mapped[int] = mapped_column(Integer, default=0)

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# adaptive_document_classifications  (Day 9)
# ---------------------------------------------------------------------------

class DocumentClassificationRow(Base):
    """
    Day 9: Document type classification result for every processed document.

    Broad classification (engagement_letter | appraisal_report | sales_contract | ...)
    plus template-level AMC matching. Classification happens before any extraction.
    Stored here so the extraction tier can load the right strategy.
    """
    __tablename__ = "adaptive_document_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Broad category result
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    type_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Keyword match counts per document type (JSON dict)
    keyword_scores_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AMC template matching
    amc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amc_template_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    amc_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Structural fingerprint of this document (for future AMC matching)
    fingerprint_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# adaptive_field_routing_config  (Day 23)
# ---------------------------------------------------------------------------

class FieldRoutingConfigRow(Base):
    """
    Day 23: Per-field, per-AMC confidence thresholds stored in DB as configuration.
    Plan Day 23: 'All threshold values must be stored in the database, not hardcoded.'
    Architecture Guide §14: 'Thresholds should be configurable per field and per AMC.'
    """
    __tablename__ = "adaptive_field_routing_config"
    __table_args__ = (
        UniqueConstraint("field_name", "amc_id", name="uq_routing_field_amc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    amc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    auto_accept: Mapped[float] = mapped_column(Float, nullable=False, default=0.90)
    review: Mapped[float] = mapped_column(Float, nullable=False, default=0.65)
    reject: Mapped[float] = mapped_column(Float, nullable=False, default=0.30)

    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")


# ---------------------------------------------------------------------------
# adaptive_validation_results  (Day 21)
# ---------------------------------------------------------------------------

class ValidationResultRow(Base):
    """
    Day 21: Semantic validation results per document, per rule.
    Architecture Guide §7: context-aware validation that checks field relationships.
    Each row is one rule result; the collection forms the QC report.
    """
    __tablename__ = "adaptive_validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(32), nullable=False)
    fields_involved: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # pass|fail|warning|info
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    field_values_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
