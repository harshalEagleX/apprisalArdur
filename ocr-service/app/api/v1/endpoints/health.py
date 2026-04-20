from datetime import datetime
import logging

from fastapi import APIRouter

from app.config import OCR_CONFIG, get_system_info, validate_binaries

try:
    import pytesseract  # noqa: F401

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    binary_issues = validate_binaries()
    system_info = get_system_info()

    if binary_issues:
        logger.warning("Health check degraded", extra={"issues": binary_issues})
    else:
        logger.debug("Health check passed")

    return {
        "status": "healthy" if not binary_issues else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "tesseract_available": TESSERACT_AVAILABLE,
        "binary_issues": binary_issues,
        "system_info": system_info,
        "ocr_config": {
            "tesseract_cmd": OCR_CONFIG["tesseract_cmd"],
            "pdf_dpi": OCR_CONFIG["pdf_dpi"],
            "max_workers": OCR_CONFIG["max_workers"],
        },
    }
