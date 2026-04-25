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
        with get_db() as db:
            rows = (
                db.query(PageOCRResult)
                .filter(PageOCRResult.file_hash == file_hash)
                .order_by(PageOCRResult.page_number)
                .all()
            )

        if len(rows) != expected_pages:
            return None  # Cache incomplete (partial previous run or different doc)

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
            # Upsert document record
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
                db.flush()  # assign ID before child inserts

            # Upsert page OCR rows
            for pt in pages:
                existing_page = (
                    db.query(PageOCRResult)
                    .filter(
                        PageOCRResult.file_hash == file_hash,
                        PageOCRResult.page_number == pt.page_number
                    )
                    .first()
                )
                if existing_page:
                    # Update if we have a better result
                    if (pt.confidence or 0) > (existing_page.confidence_score or 0):
                        existing_page.raw_text = pt.text
                        existing_page.word_count = pt.word_count
                        existing_page.confidence_score = pt.confidence
                        existing_page.extraction_method = pt.method.value
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

    confidence = average OCR page confidence × field-specific multiplier
    """
    if not _db_ok() or not document_id:
        return

    # Average confidence of all OCR pages — base for per-field scores
    avg_conf = sum(page_confidences) / len(page_confidences) if page_confidences else 0.7

    # Field-specific confidence rules
    # Fields with tight format validation get a bonus; free-text fields are less certain
    HIGH_CONFIDENCE_FIELDS = {"zip_code", "census_tract", "assessors_parcel_number", "tax_year"}
    LOWER_CONFIDENCE_FIELDS = {"neighborhood_name", "legal_description", "owner_of_public_record"}

    try:
        doc_uuid = uuid.UUID(document_id)
        with get_db() as db:
            for field_name, value in fields.items():
                if value is None:
                    conf = 0.0
                elif field_name in HIGH_CONFIDENCE_FIELDS:
                    conf = min(1.0, avg_conf + 0.10)
                elif field_name in LOWER_CONFIDENCE_FIELDS:
                    conf = max(0.0, avg_conf - 0.10)
                else:
                    conf = avg_conf

                record = ExtractedFieldRecord(
                    document_id=doc_uuid,
                    field_name=field_name,
                    field_value=str(value) if value is not None else None,
                    confidence_score=round(conf, 3),
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
