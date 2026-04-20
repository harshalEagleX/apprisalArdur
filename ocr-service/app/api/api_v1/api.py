from fastapi import APIRouter

from app.api.api_v1.endpoints import health, qc, ocr

api_router = APIRouter()

# Register domains
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(qc.router, prefix="/qc", tags=["QC Extractions"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["Legacy OCR"])
