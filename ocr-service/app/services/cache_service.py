"""
OCR Cache Service — stores and retrieves per-page OCR results by PDF file hash.

When a PDF is submitted:
  1. Compute SHA-256 hash of the file
  2. Check cache: SELECT * FROM page_ocr_results WHERE file_hash = ?
  3. If ALL pages found → return cached PageText objects instantly (0 OCR cost)
  4. If NOT found → run OCR → save results → next request is instant

Also saves per-field extracted values with confidence scores.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Graceful degradation if DB is not available
try:
    from app.database import get_db, is_db_available
    from app.models.db_models import (
        Document, PageOCRResult, ExtractedFieldRecord, RuleResultRecord
    )
    DB_AVAILABLE = is_db_available()
    if DB_AVAILABLE:
        logger.info("Database available — OCR caching enabled")
    else:
        logger.warning("Database not available — caching disabled, results not persisted")
except Exception as e:
    DB_AVAILABLE = False
    logger.warning("Cache service init failed (%s) — running without persistence", e)


def _db_ok() -> bool:
    """Runtime DB check — handles cases where DB came up after startup."""
    global DB_AVAILABLE
    if not DB_AVAILABLE:
        try:
            from app.database import is_db_available
            DB_AVAILABLE = is_db_available()
        except Exception:
            pass
    return DB_AVAILABLE


# ── OCR Page Cache ─────────────────────────────────────────────────────────────

def get_document_id(file_hash: str) -> Optional[str]:
    """Return the document_id (UUID str) for a known file_hash, or None."""
    if not _db_ok():
        return None
    try:
        with get_db() as db:
            doc = db.query(Document).filter(Document.file_hash == file_hash).first()
            return str(doc.id) if doc else None
    except Exception as e:
        logger.warning("get_document_id failed: %s", e)
        return None


def get_cached_ocr(file_hash: str, expected_pages: int):
    """
    Return a list of PageText objects if all pages are cached, else None.

    Args:
        file_hash:      SHA-256 hex digest of the PDF
        expected_pages: Total page count (to verify cache is complete)

    Returns:
        List[PageText] if cache hit, None if cache miss or DB unavailable
    """
    if not _db_ok():
        return None

    try:
        from app.ocr.ocr_pipeline import PageText, ExtractionMethod

        # Read ALL column values INSIDE the session — once the session closes,
        # SQLAlchemy ORM objects become detached and attribute access raises an error.
        with get_db() as db:
            rows = (
                db.query(PageOCRResult)
                .filter(PageOCRResult.file_hash == file_hash)
                .order_by(PageOCRResult.page_number)
                .all()
            )

            if len(rows) != expected_pages:
                return None  # Cache incomplete

            # Materialise all values while session is still open
            pages = [
                PageText(
                    page_number=r.page_number,
                    text=r.raw_text or "",
                    method=ExtractionMethod(r.extraction_method or "embedded"),
                    confidence=r.confidence_score or 0.5,
                    word_count=r.word_count or 0,
                    has_tables=r.has_tables or False,
                )
                for r in rows
            ]

        logger.info("Cache HIT: %s (%d pages)", file_hash[:12], len(pages))
        return pages

    except Exception as e:
        logger.warning("Cache lookup failed: %s", e)
        return None


def save_ocr_pages(file_hash: str, filename: str, pages) -> Optional[str]:
    """
    Persist OCR page results to the database.

    Returns:
        document_id (UUID string) if saved, None if DB unavailable
    """
    if not _db_ok():
        return None

    try:
        doc_id = uuid.uuid4()

        with get_db() as db:
            # Upsert document record (read inside session)
            existing = db.query(Document).filter(Document.file_hash == file_hash).first()
            if existing:
                doc_id = existing.id
            else:
                doc = Document(
                    id=doc_id,
                    file_hash=file_hash,
                    original_filename=filename,
                    page_count=len(pages),
                    upload_timestamp=datetime.utcnow(),
                )
                db.add(doc)
                db.flush()  # get DB-assigned id before child rows

            # Get existing page numbers in one query (avoid N+1)
            existing_page_nums = {
                row[0]
                for row in db.query(PageOCRResult.page_number)
                .filter(PageOCRResult.file_hash == file_hash)
                .all()
            }

            for pt in pages:
                if pt.page_number in existing_page_nums:
                    # Update via direct SQL to avoid session binding issues
                    db.query(PageOCRResult).filter(
                        PageOCRResult.file_hash == file_hash,
                        PageOCRResult.page_number == pt.page_number,
                    ).update({
                        "raw_text": pt.text,
                        "word_count": pt.word_count,
                        "confidence_score": pt.confidence,
                        "extraction_method": pt.method.value,
                        "has_tables": pt.has_tables,
                    })
                else:
                    page_row = PageOCRResult(
                        document_id=doc_id,
                        file_hash=file_hash,
                        page_number=pt.page_number,
                        extraction_method=pt.method.value,
                        word_count=pt.word_count,
                        confidence_score=pt.confidence,
                        raw_text=pt.text,
                        has_tables=pt.has_tables,
                    )
                    db.add(page_row)

        logger.info("Saved OCR cache: %s (%d pages)", file_hash[:12], len(pages))
        return str(doc_id)

    except Exception as e:
        logger.warning("Cache save failed: %s", e)
        return None


# ── Field confidence save ──────────────────────────────────────────────────────

def save_extracted_fields(document_id: str, fields: Dict[str, Any], page_confidences: List[float]):
    """
    Persist extracted field values with confidence scores.
    Accepts either:
      - Dict[str, Any]             (legacy Phase 1: field_name → value)
      - Dict[str, FieldMetaResult] (Phase 2: field_name → FieldMetaResult)
    """
    if not _db_ok() or not document_id:
        return

    avg_conf = sum(page_confidences) / len(page_confidences) if page_confidences else 0.7
    HIGH_CONF = {"zip_code", "census_tract", "assessors_parcel_number", "tax_year"}
    LOW_CONF  = {"neighborhood_name", "legal_description", "owner_of_public_record"}

    try:
        from app.models.field_meta import FieldMetaResult as FMR
        doc_uuid = uuid.UUID(document_id)

        with get_db() as db:
            for field_name, value in fields.items():
                if isinstance(value, FMR):
                    # Phase 2 path — rich metadata available
                    db_dict = value.to_db_dict()
                    record = ExtractedFieldRecord(
                        document_id=doc_uuid,
                        field_name=db_dict["field_name"],
                        field_value=db_dict["field_value"],
                        confidence_score=db_dict["confidence_score"],
                        source_page=db_dict["source_page"],
                        extraction_method=db_dict["extraction_method"],
                        raw_ocr_text=db_dict["raw_ocr_text"],
                        correction_applied=db_dict["correction_applied"],
                    )
                else:
                    # Phase 1 legacy path — plain value
                    if value is None:
                        conf = 0.0
                    elif field_name in HIGH_CONF:
                        conf = round(min(1.0, avg_conf + 0.10), 3)
                    elif field_name in LOW_CONF:
                        conf = round(max(0.0, avg_conf - 0.10), 3)
                    else:
                        conf = round(avg_conf, 3)
                    record = ExtractedFieldRecord(
                        document_id=doc_uuid,
                        field_name=field_name,
                        field_value=str(value) if value is not None else None,
                        confidence_score=conf,
                        extraction_method="regex",
                    )
                db.add(record)

    except Exception as e:
        logger.warning("Field save failed: %s", e)


# ── Rule results save ──────────────────────────────────────────────────────────

def save_rule_results(document_id: str, rule_results: list):
    """Persist rule results for a document."""
    if not _db_ok() or not document_id:
        return

    try:
        doc_uuid = uuid.UUID(document_id)
        with get_db() as db:
            for r in rule_results:
                record = RuleResultRecord(
                    document_id=doc_uuid,
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    status=r.status.value if hasattr(r.status, "value") else str(r.status),
                    message=r.message,
                    action_item=r.action_item,
                    appraisal_value=r.appraisal_value,
                    engagement_value=r.engagement_value,
                    review_required=r.review_required,
                )
                db.add(record)
    except Exception as e:
        logger.warning("Rule results save failed: %s", e)
