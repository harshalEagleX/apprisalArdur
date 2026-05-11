"""
SQLAlchemy ORM models — all database tables.

Tables:
  documents          — every uploaded PDF (deduplication via file_hash)
  page_ocr_results   — per-page OCR text + metadata (the cache)
  extracted_fields   — structured fields extracted from each document
  rule_results       — QC rule outcomes per document
  feedback_events    — operator corrections (drives ML training)
  training_examples  — labelled examples auto-generated from feedback
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ── Documents ─────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_hash        = Column(String(64), nullable=False, unique=True, index=True)
    original_filename = Column(String(255))
    page_count       = Column(Integer)
    upload_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    pages        = relationship("PageOCRResult",   back_populates="document", cascade="all, delete-orphan")
    fields       = relationship("ExtractedFieldRecord", back_populates="document", cascade="all, delete-orphan")
    rule_results = relationship("RuleResultRecord",     back_populates="document", cascade="all, delete-orphan")
    feedback     = relationship("FeedbackEvent",        back_populates="document", cascade="all, delete-orphan")


# ── Durable processing lifecycle ──────────────────────────────────────────────

class ProcessingJob(Base):
    """
    One durable Python-side processing attempt.

    Java remains the business system of record; this table is Python's technical
    journal for OCR, extraction, LLM, rule execution, retries, and failures.
    """
    __tablename__ = "processing_jobs"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key        = Column(String(255), unique=True, index=True)
    correlation_id         = Column(String(128), index=True)
    batch_id               = Column(String(64), index=True)
    batch_file_id          = Column(String(64), index=True)
    qc_result_id           = Column(String(64), index=True)
    source_document_hash   = Column(String(64), index=True)
    original_filename      = Column(String(255))
    model_provider         = Column(String(50))
    model_name             = Column(String(100))
    vision_model           = Column(String(100))
    traceparent            = Column(String(128))
    tracestate             = Column(Text)
    rule_set_version       = Column(String(50), default="1.0")
    current_stage          = Column(String(80), index=True)
    status                 = Column(String(30), default="queued", index=True)
    retry_count            = Column(Integer, default=0)
    document_id            = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    result_json            = Column(Text)
    failure_reason         = Column(Text)
    started_at             = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at           = Column(DateTime)
    failed_at              = Column(DateTime)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document")
    stages   = relationship("ProcessingStage", back_populates="job", cascade="all, delete-orphan")
    llm_calls = relationship("LLMCallLog", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_processing_jobs_corr_status", "correlation_id", "status"),
        Index("ix_processing_jobs_hash_status", "source_document_hash", "status"),
    )


class ProcessingStage(Base):
    """Durable timing row for a major pipeline stage within a job."""
    __tablename__ = "processing_stages"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    job_id         = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id"), nullable=False, index=True)
    stage_name     = Column(String(80), nullable=False, index=True)
    status         = Column(String(30), default="started", index=True)
    started_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at   = Column(DateTime)
    duration_ms    = Column(Integer)
    error_message  = Column(Text)
    metadata_json  = Column(Text)

    job = relationship("ProcessingJob", back_populates="stages")

    __table_args__ = (
        Index("ix_processing_stages_job_stage", "job_id", "stage_name"),
    )


class LLMCallLog(Base):
    """Privacy-conscious metadata for each Ollama call."""
    __tablename__ = "llm_call_logs"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    job_id              = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id"), index=True)
    correlation_id       = Column(String(128), index=True)
    stage_name           = Column(String(80))
    task_name            = Column(String(100))
    prompt_hash          = Column(String(64), nullable=False, index=True)
    model_name           = Column(String(100))
    started_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at         = Column(DateTime)
    duration_ms          = Column(Integer)
    status               = Column(String(30), index=True)
    timed_out            = Column(Boolean, default=False)
    fallback_path        = Column(String(80))
    confidence_label     = Column(String(30))
    response_hash        = Column(String(64))
    error_message        = Column(Text)

    job = relationship("ProcessingJob", back_populates="llm_calls")

    __table_args__ = (
        Index("ix_llm_call_logs_job_stage", "job_id", "stage_name"),
    )


# ── OCR Cache: one row per page per unique PDF ────────────────────────────────

class PageOCRResult(Base):
    __tablename__ = "page_ocr_results"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    document_id       = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    file_hash         = Column(String(64), nullable=False, index=True)
    page_number       = Column(Integer, nullable=False)
    extraction_method = Column(String(20))           # embedded / tesseract / cloud
    word_count        = Column(Integer)
    confidence_score  = Column(Float)
    raw_text          = Column(Text)
    hocr_text         = Column(Text)
    word_json         = Column(Text)
    has_tables        = Column(Boolean, default=False)
    processed_at      = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="pages")

    __table_args__ = (
        UniqueConstraint("file_hash", "page_number", name="uq_page_ocr_hash_page"),
        Index("ix_page_ocr_file_hash", "file_hash"),
    )


# ── Extracted fields ──────────────────────────────────────────────────────────

class ExtractedFieldRecord(Base):
    __tablename__ = "extracted_fields"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    document_id       = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    processing_job_id = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id"))
    field_name        = Column(String(100), nullable=False)
    field_value       = Column(Text)
    extraction_status = Column(String(30), default="NOT_FOUND", nullable=False)
    confidence_score  = Column(Float, default=0.0)
    source_document   = Column(String(50))
    source_page       = Column(Integer)              # which page the value was found on
    bbox_x            = Column(Float)
    bbox_y            = Column(Float)
    bbox_w            = Column(Float)
    bbox_h            = Column(Float)
    parser            = Column(String(80))
    extraction_method = Column(String(30))           # spatial_anchor / regex_primary / regex_fallback / not_found
    raw_ocr_text      = Column(Text)                 # value before OCR correction (training signal)
    normalization_steps = Column(Text)
    failure_reason    = Column(Text)
    correction_applied = Column(Boolean, default=False)  # True if ocr_correction.py changed the value
    created_at        = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="fields")

    __table_args__ = (
        Index("ix_extracted_doc_field", "document_id", "field_name"),
    )


# ── Rule results ──────────────────────────────────────────────────────────────

class RuleResultRecord(Base):
    __tablename__ = "rule_results"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    document_id      = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    processing_job_id = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id"))
    rule_id          = Column(String(20), nullable=False)
    rule_name        = Column(String(200))
    status           = Column(String(20))            # pass / fail / verify
    severity         = Column(String(30))
    message          = Column(Text)
    action_item      = Column(Text)
    appraisal_value  = Column(Text)
    engagement_value = Column(Text)
    extracted_value  = Column(Text)
    expected_value   = Column(Text)
    confidence_score = Column(Float)
    target_field     = Column(String(100))
    rule_version     = Column(String(50))
    review_required  = Column(Boolean, default=False)
    source_documents = Column(Text)
    compared_fields  = Column(Text)
    compared_values  = Column(Text)
    comparison_method = Column(String(80))
    decision_path    = Column(Text)
    exception_type   = Column(String(120))
    exception_trace  = Column(Text)
    stage            = Column(String(80))
    retry_eligible   = Column(Boolean, default=False)
    source_page      = Column(Integer)
    bbox_x           = Column(Float)
    bbox_y           = Column(Float)
    bbox_w           = Column(Float)
    bbox_h           = Column(Float)
    created_at       = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="rule_results")

    __table_args__ = (
        Index("ix_rule_results_doc_rule", "document_id", "rule_id"),
        Index("ix_rule_results_job_rule", "processing_job_id", "rule_id"),
        Index("ix_rule_results_status", "status"),
    )


# ── Feedback events (operator corrections) ────────────────────────────────────

class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    document_id        = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    processing_job_id  = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id"))
    correlation_id     = Column(String(128), index=True)
    rule_id            = Column(String(20))
    field_name         = Column(String(100))
    original_status    = Column(String(20))
    corrected_status   = Column(String(20))
    original_value     = Column(Text)
    corrected_value    = Column(Text)
    operator_comment   = Column(Text)
    reviewer_role      = Column(String(50))
    decision_latency_ms = Column(Integer)
    acknowledged       = Column(Boolean)
    source_page        = Column(Integer)
    bbox_x             = Column(Float)
    bbox_y             = Column(Float)
    bbox_w             = Column(Float)
    bbox_h             = Column(Float)
    confidence_score   = Column(Float)
    feedback_timestamp = Column(DateTime, default=datetime.utcnow)
    used_for_training  = Column(Boolean, default=False)

    document          = relationship("Document", back_populates="feedback")
    training_examples = relationship("TrainingExample", back_populates="source_feedback")

    __table_args__ = (
        Index("ix_feedback_doc", "document_id"),
        Index("ix_feedback_not_trained", "used_for_training"),
    )


class ConfidenceCalibration(Base):
    """
    Reviewer-derived calibration for raw extraction confidence.

    Raw extractor confidence is method-local: a 0.70 regex score and a 0.70
    OCR/model score do not mean the same thing. This table stores observed
    reviewer correctness by field + extraction method so later runs can adjust
    confidence using product evidence instead of hardcoded intuition.
    """
    __tablename__ = "confidence_calibration"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    field_name          = Column(String(100), nullable=False)
    extraction_method   = Column(String(50), nullable=False)
    reviewed_count      = Column(Integer, default=0, nullable=False)
    correct_count       = Column(Integer, default=0, nullable=False)
    incorrect_count     = Column(Integer, default=0, nullable=False)
    historical_precision = Column(Float)
    historical_recall   = Column(Float)
    sample_size         = Column(Integer, default=0, nullable=False)
    last_calibrated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("field_name", "extraction_method", name="uq_conf_calibration_field_method"),
        Index("ix_conf_calibration_field_method", "field_name", "extraction_method"),
    )


# ── Training examples (auto-generated from feedback) ─────────────────────────

class RuleConfig(Base):
    """
    DB-driven rule configuration (Phase 3).
    Allows toggling rules, changing severity, and restricting to loan types
    WITHOUT a code deploy — just update this table.
    """
    __tablename__ = "rules_config"

    rule_id              = Column(String(20), primary_key=True)
    rule_name            = Column(String(200), nullable=False)
    rule_category        = Column(String(50))                    # Subject / Contract / Narrative
    is_active            = Column(Boolean, default=True)         # toggle without restart
    severity_level       = Column(String(20), default="STANDARD")  # BLOCKING / STANDARD / ADVISORY
    applicable_loan_types = Column(String(200), default="ALL")   # comma-separated: ALL, Purchase, Refinance
    execution_order      = Column(Integer, default=100)          # lower = runs first
    last_modified_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by          = Column(String(100), default="system")

    __table_args__ = (
        Index("ix_rules_config_active", "is_active"),
    )


class LLMResponseCache(Base):
    """
    Cache LLM (ollama) responses by hash of input text (Phase 4).
    Same commentary text → same LLM answer, no repeated API call.
    """
    __tablename__ = "llm_response_cache"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    input_hash   = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 of prompt
    task         = Column(String(50))                           # "canned_detection", "market_quality", etc.
    response     = Column(Text)                                 # Raw LLM response string
    model_name   = Column(String(100))
    created_at   = Column(DateTime, default=datetime.utcnow)
    hit_count    = Column(Integer, default=0)                   # How many times this cache entry was used


class TrainingExample(Base):
    __tablename__ = "training_examples"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    feature_type       = Column(String(50), nullable=False)
    # e.g. "ocr_correction", "commentary_quality", "field_extraction", "checkbox_state"
    input_text         = Column(Text, nullable=False)
    label              = Column(String(100), nullable=False)
    source_feedback_id = Column(Integer, ForeignKey("feedback_events.id"))
    model_version      = Column(String(50))          # which model version was trained on this
    created_at         = Column(DateTime, default=datetime.utcnow)

    source_feedback = relationship("FeedbackEvent", back_populates="training_examples")

    __table_args__ = (
        Index("ix_training_feature_type", "feature_type"),
        Index("ix_training_label", "label"),
    )
