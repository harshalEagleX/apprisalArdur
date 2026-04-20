from fastapi import APIRouter

from app.api.v1.endpoints import feedback, health, ocr, qc

api_router = APIRouter()

# Keep legacy root paths for Java integration compatibility.
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(qc.router, prefix="/qc", tags=["QC Extractions"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["Legacy OCR"])
