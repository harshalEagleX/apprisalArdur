from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.feedback_store import feedback_store

router = APIRouter()


class CorrectionRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    field_name: str = Field(..., min_length=1)
    predicted_value: Optional[str] = None
    corrected_value: Optional[str] = None
    confidence_score: Optional[float] = None
    section: Optional[str] = None
    operator_id: Optional[str] = None


@router.post("/correction")
async def submit_correction(payload: CorrectionRequest):
    was_correct = (payload.predicted_value or "") == (payload.corrected_value or "")
    record_id = feedback_store.save_correction(
        {
            "document_id": payload.document_id,
            "field_name": payload.field_name,
            "predicted_value": payload.predicted_value,
            "corrected_value": payload.corrected_value,
            "confidence_score": payload.confidence_score,
            "section": payload.section,
            "operator_id": payload.operator_id,
            "was_correct": was_correct,
        }
    )
    return {"status": "saved", "id": record_id, "was_correct": was_correct}
