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
    field_name        = Column(String(100), nullable=False)
    field_value       = Column(Text)
    confidence_score  = Column(Float, default=0.0)
    source_page       = Column(Integer)              # which page the value was found on
    extraction_method = Column(String(20))           # embedded / tesseract / regex
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
    rule_id          = Column(String(20), nullable=False)
    rule_name        = Column(String(200))
    status           = Column(String(20))            # pass / fail / verify / warning / skipped
    message          = Column(Text)
    action_item      = Column(Text)
    appraisal_value  = Column(Text)
    engagement_value = Column(Text)
    review_required  = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="rule_results")

    __table_args__ = (
        Index("ix_rule_results_doc_rule", "document_id", "rule_id"),
        Index("ix_rule_results_status", "status"),
    )


# ── Feedback events (operator corrections) ────────────────────────────────────

class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    document_id        = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    rule_id            = Column(String(20))
    field_name         = Column(String(100))
    original_status    = Column(String(20))
    corrected_status   = Column(String(20))
    original_value     = Column(Text)
    corrected_value    = Column(Text)
    operator_comment   = Column(Text)
    feedback_timestamp = Column(DateTime, default=datetime.utcnow)
    used_for_training  = Column(Boolean, default=False)

    document          = relationship("Document", back_populates="feedback")
    training_examples = relationship("TrainingExample", back_populates="source_feedback")

    __table_args__ = (
        Index("ix_feedback_doc", "document_id"),
        Index("ix_feedback_not_trained", "used_for_training"),
    )


# ── Training examples (auto-generated from feedback) ─────────────────────────

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
