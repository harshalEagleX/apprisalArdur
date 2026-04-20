import os
import shutil
import tempfile
import uuid
import time
import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
import fitz

from app.schemas.ocr_schemas import OcrResponse, ExtractedFields, CheckboxFields
from app.utils.validators import is_valid_pdf
from app.services.legacy.parser import (
    extract_text_from_pdf, 
    extract_fields, 
    detect_form_type, 
    calculate_confidence, 
    extract_checkboxes
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/appraisal", response_model=OcrResponse)
async def process_appraisal(request: Request, file: UploadFile = File(...)):
    """
    Process an appraisal PDF and extract key fields using legacy parsing logic.
    """
    start_time = time.time()
    warnings = []
    request_id = getattr(request.state, "request_id", None)

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"})

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = os.path.join(temp_dir, f"ocr_input_{uuid.uuid4()}.pdf")
            with open(tmp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            if not is_valid_pdf(tmp_path):
                 raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_CONTENT", "message": "File does not appear to be a valid PDF"})

            raw_text = await run_in_threadpool(extract_text_from_pdf, tmp_path)
            
            if not raw_text or len(raw_text.strip()) < 50:
                warnings.append("Low text content extracted from PDF")
            
            def process_text_logic(text):
                extracted = extract_fields(text)
                form_type = detect_form_type(text)
                confidence = calculate_confidence(extracted, text)
                checkboxes = extract_checkboxes(text)
                return extracted, form_type, confidence, checkboxes

            extracted, form_type, confidence, checkboxes = await run_in_threadpool(process_text_logic, raw_text)
            processing_time_ms = int((time.time() - start_time) * 1000)

            return OcrResponse(
                success=True,
                processingTimeMs=processing_time_ms,
                confidenceScore=confidence,
                formType=form_type,
                extractedFields=ExtractedFields(**extracted),
                checkboxes=CheckboxFields(**checkboxes),
                rawText=raw_text[:5000] if raw_text else None,
                warnings=warnings
            )

    except HTTPException:
        raise
    except fitz.FileDataError:
        raise HTTPException(status_code=400, detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"})
    except Exception as e:
        logger.error("Processing error", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "PROCESSING_ERROR", "message": str(e)})
