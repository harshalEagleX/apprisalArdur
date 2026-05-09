"""
Reviewer-backed confidence calibration.

The extractor emits raw confidence by method. This service keeps that raw score
useful for product decisions by blending it with reviewer outcomes recorded
through feedback_events.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

MIN_SAMPLES_TO_APPLY = 25


def calibrated_confidence(field_name: str, extraction_method: str, raw_confidence: float) -> float:
    """Return confidence adjusted by historical reviewer precision when useful."""
    if raw_confidence is None:
        return 0.0
    raw = max(0.0, min(1.0, float(raw_confidence)))
    if not field_name or not extraction_method:
        return raw

    try:
        from app.database import get_db
        from app.models.db_models import ConfidenceCalibration

        with get_db() as db:
            row = db.query(ConfidenceCalibration).filter(
                ConfidenceCalibration.field_name == field_name,
                ConfidenceCalibration.extraction_method == extraction_method,
            ).first()
            if not row or (row.sample_size or 0) < MIN_SAMPLES_TO_APPLY or row.historical_precision is None:
                return raw

            historical = max(0.0, min(1.0, float(row.historical_precision)))
            # Keep the extractor signal, but let reviewer evidence pull it toward reality.
            return round((raw * 0.70) + (historical * 0.30), 3)
    except Exception as exc:
        logger.debug("confidence calibration lookup skipped: %s", exc)
        return raw


def record_feedback_outcome(
    *,
    document_id: str,
    field_name: Optional[str],
    corrected_value: Optional[str],
    feedback_type: Optional[str],
) -> None:
    """
    Update calibration from a reviewer/feedback event.

    A PASS/CORRECT decision means the extractor was correct. A FAIL/ERROR-style
    decision means it was not. If a corrected value is present and differs from
    the extracted value, that is also treated as incorrect.
    """
    if not document_id or not field_name:
        return

    try:
        from app.database import get_db
        from app.models.db_models import ConfidenceCalibration, ExtractedFieldRecord

        doc_uuid = uuid.UUID(str(document_id))
        with get_db() as db:
            extracted = db.query(ExtractedFieldRecord).filter(
                ExtractedFieldRecord.document_id == doc_uuid,
                ExtractedFieldRecord.field_name == field_name,
            ).order_by(ExtractedFieldRecord.created_at.desc()).first()
            if not extracted:
                return

            method = extracted.extraction_method or "unknown"
            raw_value = (extracted.field_value or "").strip()
            corrected = (corrected_value or "").strip()
            kind = (feedback_type or "").strip().upper()
            decision_value = corrected.upper()

            if kind == "REVIEW_DECISION" and decision_value in {"PASS", "FAIL"}:
                is_correct = decision_value == "PASS"
            elif kind in {"PASS", "CORRECT", "ACCEPTED"}:
                is_correct = True
            elif kind in {"FAIL", "RULE_ERROR", "EXTRACTION_ERROR", "OCR_ERROR", "REVIEW_DECISION_FAIL"}:
                is_correct = False
            elif corrected:
                is_correct = corrected.lower() == raw_value.lower()
            else:
                return

            row = db.query(ConfidenceCalibration).filter(
                ConfidenceCalibration.field_name == field_name,
                ConfidenceCalibration.extraction_method == method,
            ).first()
            if not row:
                row = ConfidenceCalibration(
                    field_name=field_name,
                    extraction_method=method,
                    reviewed_count=0,
                    correct_count=0,
                    incorrect_count=0,
                    sample_size=0,
                )
                db.add(row)

            row.reviewed_count = (row.reviewed_count or 0) + 1
            if is_correct:
                row.correct_count = (row.correct_count or 0) + 1
            else:
                row.incorrect_count = (row.incorrect_count or 0) + 1
            row.sample_size = row.reviewed_count
            row.historical_precision = (
                float(row.correct_count or 0) / float(row.reviewed_count or 1)
            )
            # The current feedback payload gives reviewed extraction outcomes,
            # not complete false-negative population data. Store the same
            # observed correctness rate as recall until richer sampling exists.
            row.historical_recall = row.historical_precision
    except Exception as exc:
        logger.debug("confidence calibration update skipped: %s", exc)
