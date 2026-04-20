import os
import shutil
import tempfile
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
import fitz

from app.utils.validators import is_valid_pdf
from app.qc_processor import qc_processor
from app.services.extraction_service import extraction_service
from app.services.legacy.parser import extract_text_from_pdf
from app.rule_engine.engine import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/extract")
async def extract_facts(
    request: Request,
    file: UploadFile = File(...),
    engagement_letter: Optional[UploadFile] = None,
    env_file: Optional[UploadFile] = None,
):
    """
    Pure Fact Extraction Endpoint - Python sees, Java thinks, Humans decide.
    """
    request_id = getattr(request.state, "request_id", None)
    
    if not file.filename.lower().endswith('.pdf'):
        logger.warning("Invalid file extension", extra={"uploaded_filename": file.filename, "request_id": request_id})
        raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"})
    
    try:
        logger.info("Starting extraction", extra={"uploaded_filename": file.filename, "request_id": request_id})
        
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, f"input_{uuid.uuid4()}.pdf")
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            if not is_valid_pdf(pdf_path):
                 raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_CONTENT", "message": "File does not appear to be a valid PDF"})

            engagement_text = None
            if engagement_letter:
                eng_path = os.path.join(temp_dir, f"eng_{uuid.uuid4()}")
                with open(eng_path, "wb") as buffer:
                    shutil.copyfileobj(engagement_letter.file, buffer)
                
                if engagement_letter.filename.lower().endswith('.pdf'):
                     if is_valid_pdf(eng_path):
                        engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)
                else:
                    with open(eng_path, "rb") as f:
                        engagement_text = f.read().decode('utf-8', errors='ignore')
            
            env_content = None
            if env_file:
                env_content = await env_file.read()
            
            result = await run_in_threadpool(
                extraction_service.extract_and_compare,
                pdf_path=pdf_path,
                engagement_letter_text=engagement_text,
                env_content=env_content
            )
            
            logger.info("Extraction completed successfully", extra={"request_id": request_id})
            return result.model_dump()
            
    except HTTPException:
        raise
    except fitz.FileDataError:
        raise HTTPException(status_code=400, detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"})
    except Exception as e:
        logger.error("Extraction error", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "EXTRACTION_ERROR", "message": str(e)})


@router.post("/process")
async def process_qc(
    request: Request,
    file: UploadFile = File(...),
    engagement_letter: Optional[UploadFile] = None,
):
    """
    Full QC pipeline: OCR → Extract → Subject & Contract Rules → Results
    """
    request_id = getattr(request.state, "request_id", None)

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"})
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, f"qc_input_{uuid.uuid4()}.pdf")
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            if not is_valid_pdf(pdf_path):
                 raise HTTPException(status_code=400, detail={"error": "INVALID_FILE_CONTENT", "message": "File does not appear to be a valid PDF"})
            
            engagement_text = None
            if engagement_letter:
                eng_path = os.path.join(temp_dir, f"qc_eng_{uuid.uuid4()}")
                with open(eng_path, "wb") as buffer:
                    shutil.copyfileobj(engagement_letter.file, buffer)
                
                if engagement_letter.filename.lower().endswith(".pdf") and is_valid_pdf(eng_path):
                    engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)
                else:
                    with open(eng_path, "rb") as f:
                        engagement_text = f.read().decode('utf-8', errors='ignore')
            
            results = await run_in_threadpool(
                qc_processor.process_document,
                pdf_path=pdf_path,
                engagement_letter_text=engagement_text,
            )
            
            return results.model_dump()
            
    except HTTPException:
        raise
    except fitz.FileDataError:
        raise HTTPException(status_code=400, detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"})
    except Exception as e:
        logger.error("QC Processing error", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "QC_PROCESSING_ERROR", "message": str(e)})


@router.get("/rules")
async def list_qc_rules():
    """List all registered QC rules."""
    rules_info = []
    subject_rules_count = contract_rules_count = 0
    
    for rule_func in engine._rules:
        rule_id = getattr(rule_func, 'rule_id', 'UNKNOWN')
        rule_name = getattr(rule_func, 'rule_name', rule_func.__name__)
        
        if rule_id.startswith('S-'):
            category = 'Subject Section'
            subject_rules_count += 1
        elif rule_id.startswith('C-'):
            category = 'Contract Section'
            contract_rules_count += 1
        else:
            category = 'Other'
        
        rules_info.append({
            "id": rule_id,
            "name": rule_name,
            "category": category,
            "doc": rule_func.__doc__[:200] if rule_func.__doc__ else None,
        })

    return {
        "total_rules": len(rules_info),
        "categories": {
            "subject_section": subject_rules_count,
            "contract_section": contract_rules_count
        },
        "rules": rules_info
    }
