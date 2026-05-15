"""
Day 5 — Correction Capture Service

Stores and retrieves human reviewer corrections.

Design constraints from CLAUDE.md Rule 10 and the plan:
  - Every correction must include: original_ocr_text, system_extracted_value,
    operator_provided_value, rule_id (if known), source_page.
  - Missing any of these makes the training example useless.
  - Today is ONLY capture — no learning logic, no pattern updates.
    Fast-path learning and model retraining come in Week Five.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.database import get_db
from app.models.db_models import CorrectionRow, ExtractionResultRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / Output models (validated at the API boundary)
# ---------------------------------------------------------------------------

VALID_REASON_CATEGORIES = {
    "wrong_label_matched",
    "ocr_error",
    "value_wrong_location",
    "completely_absent",
    "ambiguous_context",
    "other",
}


class CorrectionRequest(BaseModel):
    """
    What the reviewer (or Java backend) sends to record a correction.
    All fields except corrected_value and rule_id are required for training value.
    """
    document_id: str = Field(..., description="Document identifier (batch:doc_type)")
    document_type: str = Field(..., description="appraisal_report | engagement_letter | sales_contract")
    amc_id: Optional[str] = None
    field_name: str = Field(..., description="Canonical field name from field schema")
    source_page: Optional[int] = Field(None, description="Page number where field was found (or expected)")
    original_extracted_value: Optional[str] = Field(None, description="What the system extracted")
    original_ocr_text: Optional[str] = Field(None, description="Verbatim OCR source text")
    corrected_value: Optional[str] = Field(None, description="What the reviewer says is correct (None = field is absent)")
    reason_category: str = Field("other", description="Why the extraction was wrong")
    explanation: Optional[str] = Field(None, description="Free-text explanation from reviewer")
    rule_id: Optional[str] = Field(None, description="QC rule ID that surfaced this correction")
    reviewer_id: str = Field("reviewer", description="Who made the correction")
    extraction_result_id: Optional[int] = Field(None, description="FK to adaptive_extraction_results row")

    @field_validator("reason_category")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if v not in VALID_REASON_CATEGORIES:
            raise ValueError(f"reason_category must be one of: {sorted(VALID_REASON_CATEGORIES)}")
        return v

    @field_validator("document_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        valid = {"appraisal_report", "engagement_letter", "sales_contract", "qc_checklist"}
        if v not in valid:
            raise ValueError(f"document_type must be one of: {sorted(valid)}")
        return v


class CorrectionResponse(BaseModel):
    correction_id: int
    document_id: str
    field_name: str
    corrected_value: Optional[str]
    reason_category: str
    corrected_at: str
    fast_path_candidate: bool


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def save_correction(req: CorrectionRequest) -> CorrectionResponse:
    """
    Persist a reviewer correction to the database.

    Marks the linked extraction_result row as has_correction=True so the
    system knows this field was reviewed and found incorrect.
    """
    with get_db() as session:
        row = CorrectionRow(
            document_id=req.document_id,
            document_type=req.document_type,
            amc_id=req.amc_id,
            field_name=req.field_name,
            source_page=req.source_page,
            original_extracted_value=req.original_extracted_value,
            original_ocr_text=req.original_ocr_text,
            corrected_value=req.corrected_value,
            reason_category=req.reason_category,
            explanation=req.explanation,
            rule_id=req.rule_id,
            reviewer_id=req.reviewer_id,
            extraction_result_id=req.extraction_result_id,
        )
        session.add(row)
        session.flush()
        correction_id = row.id

        # Mark the linked extraction result as corrected
        if req.extraction_result_id:
            er = session.get(ExtractionResultRow, req.extraction_result_id)
            if er:
                er.has_correction = True
                er.reviewer_confirmed = True

        # A wrong_label_matched correction is a fast-path learning candidate:
        # the next synonym can be added to the AMC profile without retraining.
        fast_path = req.reason_category == "wrong_label_matched"

        logger.info(
            "Correction saved: doc=%s field=%s reason=%s reviewer=%s",
            req.document_id, req.field_name, req.reason_category, req.reviewer_id,
        )

    return CorrectionResponse(
        correction_id=correction_id,
        document_id=req.document_id,
        field_name=req.field_name,
        corrected_value=req.corrected_value,
        reason_category=req.reason_category,
        corrected_at=datetime.now(timezone.utc).isoformat(),
        fast_path_candidate=fast_path,
    )


def get_corrections_for_document(document_id: str) -> List[CorrectionResponse]:
    """Return all corrections for a given document."""
    with get_db() as session:
        rows = session.query(CorrectionRow).filter_by(
            document_id=document_id
        ).order_by(CorrectionRow.corrected_at.desc()).all()

        return [
            CorrectionResponse(
                correction_id=r.id,
                document_id=r.document_id,
                field_name=r.field_name,
                corrected_value=r.corrected_value,
                reason_category=r.reason_category,
                corrected_at=r.corrected_at.isoformat(),
                fast_path_candidate=(r.reason_category == "wrong_label_matched"),
            )
            for r in rows
        ]


def get_correction_stats() -> dict:
    """Return counts of corrections by reason category — for observability."""
    with get_db() as session:
        rows = session.query(
            CorrectionRow.reason_category,
            CorrectionRow.field_name,
        ).all()

    from collections import Counter
    by_reason = Counter(r.reason_category for r in rows)
    by_field = Counter(r.field_name for r in rows)

    return {
        "total": len(rows),
        "by_reason": dict(by_reason.most_common()),
        "by_field": dict(by_field.most_common(15)),
    }
