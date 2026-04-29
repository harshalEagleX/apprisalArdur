"""
OCR Microservice for Appraisal Document Processing
FastAPI application that extracts fields from appraisal PDFs.
"""

import hashlib
import os
import re
import time
import shutil
import tempfile
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, WebSocket, WebSocketDisconnect, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import fitz  # PyMuPDF

# Import Logging Configuration
from app.logging_config import setup_logging

# Setup logging immediately
logger = setup_logging()

# Import OCR configuration
from app.config import OCR_CONFIG, TESSERACT_CMD, MAX_FILE_SIZE_BYTES, MAX_PAGE_COUNT, validate_binaries, get_system_info
from app.ocr.ocr_pipeline import OCRPipeline

# Import rules at startup so @rule decorators register against the global engine
import app.rules  # noqa: F401  (side-effect import)

# Seed DB rule config (idempotent — does nothing if already seeded)
from app.rule_engine.rules_db import seed_rules_config
seed_rules_config()

# Try to import Tesseract, but make it optional
try:
    import pytesseract
    from PIL import Image
    
    # Configure Tesseract to use M1-optimized binary
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    TESSERACT_AVAILABLE = True
    logger.info(f"Tesseract configured", extra={"path": TESSERACT_CMD})
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract not available")

# ── Rate limiting ──────────────────────────────────────────────────────────────
# PROD: /qc/process is expensive (14-30s OCR). Limit per IP to prevent abuse.
_limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]          # no global limit — apply per-route
)

app = FastAPI(
    title="Appraisal OCR Service",
    description="Extracts key fields from appraisal PDF documents",
    version="1.0.0"
)

app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — restrict to Java backend + local dev ───────────────────────────────
_ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# ── API-Key authentication ─────────────────────────────────────────────────────
_API_KEY        = os.getenv("PYTHON_API_KEY", "")          # empty = dev mode (no key required)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def _require_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Validate X-API-Key header. Skipped in dev mode (PYTHON_API_KEY not set)."""
    if not _API_KEY:
        return  # dev mode — no key required
    if api_key != _API_KEY:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Invalid or missing API key"})

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    # Add request_id to request state for access in endpoints if needed
    request.state.request_id = request_id
    
    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "request_id": request_id,
            "client_host": request.client.host if request.client else None
        }
    )
    
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": process_time_ms,
                "request_id": request_id
            }
        )
        return response
    except Exception as e:
        process_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "duration_ms": process_time_ms,
                "request_id": request_id
            },
            exc_info=True
        )
        raise

class ExtractedFields(BaseModel):
    borrowerName: Optional[str] = None
    coBorrowerName: Optional[str] = None
    propertyAddress: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    appraisedValue: Optional[float] = None
    effectiveDate: Optional[str] = None
    salePrice: Optional[float] = None
    lenderName: Optional[str] = None
    appraiserName: Optional[str] = None
    appraiserLicenseNumber: Optional[str] = None


class CheckboxFields(BaseModel):
    isInFloodZone: bool = False
    isForSale: bool = False
    hasPoolOrSpa: bool = False
    isCondoOrPUD: bool = False
    isPud: bool = False
    isManufacturedHome: bool = False
    didAnalyzeContract: bool = False


class OcrResponse(BaseModel):
    success: bool
    processingTimeMs: int
    confidenceScore: float
    formType: Optional[str] = None
    extractedFields: ExtractedFields
    checkboxes: CheckboxFields
    rawText: Optional[str] = None
    warnings: list[str] = []
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str


@app.get("/health")
async def health_check():
    """Health check endpoint with binary validation."""
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
            "tesseract_cmd": OCR_CONFIG['tesseract_cmd'],
            "pdf_dpi": OCR_CONFIG['pdf_dpi'],
            "max_workers": OCR_CONFIG['max_workers'],
        }
    }


# Import QC processor (lazy import to avoid circular dependencies)
def get_qc_processor():
    from app.qc_processor import qc_processor
    return qc_processor


def get_extraction_service():
    """Lazy import for extraction service."""
    from app.services.extraction_service import extraction_service
    return extraction_service


@app.post("/qc/extract")
async def extract_facts(
    request: Request,
    _auth: None = Security(_require_api_key),
    file: UploadFile = File(...),
    engagement_letter: Optional[UploadFile] = None,
    env_file: Optional[UploadFile] = None,
):
    """
    Pure Fact Extraction Endpoint - Python sees, Java thinks, Humans decide.
    """
    request_id = getattr(request.state, "request_id", None)
    
    # Validate file type
    # Validate file extension (basic check)
    if not file.filename.lower().endswith('.pdf'):
        logger.warning(
            "Invalid file extension", 
            extra={"uploaded_filename": file.filename, "request_id": request_id}
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"}
        )
    
    try:
        logger.info(
            "Starting extraction", 
            extra={
                "uploaded_filename": file.filename, 
                "has_engagement_letter": engagement_letter is not None,
                "has_env_file": env_file is not None,
                "request_id": request_id
            }
        )
        
        # Use TemporaryDirectory for robust cleanup
        with tempfile.TemporaryDirectory() as temp_dir:
            # stream file to disk to avoid memory spike
            pdf_path = os.path.join(temp_dir, f"input_{uuid.uuid4()}.pdf")
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Security: Magic Byte Check
            if not is_valid_pdf(pdf_path):
                 logger.warning("Invalid PDF magic bytes", extra={"request_id": request_id})
                 raise HTTPException(
                    status_code=400,
                    detail={"error": "INVALID_FILE_CONTENT", "message": "File does not appear to be a valid PDF"}
                )

            # Process engagement letter if provided
            engagement_text = None
            if engagement_letter:
                eng_path = os.path.join(temp_dir, f"eng_{uuid.uuid4()}")
                # Copy engagement letter safely
                with open(eng_path, "wb") as buffer:
                    shutil.copyfileobj(engagement_letter.file, buffer)
                
                if engagement_letter.filename.lower().endswith('.pdf'):
                     if is_valid_pdf(eng_path):
                        # Run in threadpool to avoid blocking
                        engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)
                     else:
                        logger.warning("Invalid Engagement Letter PDF magic bytes") # Log but maybe don't fail hard?
                else:
                    # Assume text file
                    with open(eng_path, "rb") as f:
                        engagement_text = f.read().decode('utf-8', errors='ignore')
            
            # Read ENV file if provided
            env_content = None
            if env_file:
                env_content = await env_file.read() # keeping as read() since these are usually small JSONs
            
            # Run extraction service in threadpool
            service = get_extraction_service()
            result = await run_in_threadpool(
                service.extract_and_compare,
                pdf_path=pdf_path,
                engagement_letter_text=engagement_text,
                env_content=env_content
            )
            
            logger.info("Extraction completed successfully", extra={"request_id": request_id})
            return result.model_dump()
            
    except HTTPException:
        raise
    except fitz.FileDataError:
        logger.error("Corrupted PDF", extra={"request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        logger.error("Extraction error", extra={"error": str(e), "request_id": request_id}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "EXTRACTION_ERROR", "message": str(e)}
        )


@app.post("/qc/process")
@_limiter.limit("20/minute")   # PROD: max 20 QC requests/min per IP — OCR is expensive
async def process_qc(
    request: Request,
    _auth: None = Security(_require_api_key),
    file: UploadFile = File(...),
    engagement_letter: Optional[UploadFile] = None,
    contract_file: Optional[UploadFile] = None,
):
    """
    Full QC pipeline: OCR → Extract → Subject & Contract Rules → Results

    - file: Appraisal PDF (required)
    - engagement_letter: Order form / engagement letter PDF (optional but recommended)
    - contract_file: Purchase agreement PDF (optional; used when appraisal indicates
      contract was analyzed, enables C-2/C-4/C-5 cross-checks)
    """
    request_id = getattr(request.state, "request_id", None)

    if not file.filename.lower().endswith('.pdf'):
        logger.warning(
            "Invalid file type in process_qc",
            extra={"uploaded_filename": file.filename, "request_id": request_id}
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"}
        )

    try:
        logger.info(
            "Starting QC processing",
            extra={
                "uploaded_filename": file.filename,
                "has_engagement_letter": engagement_letter is not None,
                "has_contract_file": contract_file is not None,
                "request_id": request_id
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            # Stream appraisal PDF to disk
            pdf_path = os.path.join(temp_dir, f"qc_input_{uuid.uuid4()}.pdf")
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            err = validate_upload(pdf_path, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_FILE", "message": err})

            file_hash = sha256_file(pdf_path)

            # Process engagement letter if provided
            engagement_text = None
            if engagement_letter:
                eng_path = os.path.join(temp_dir, f"qc_eng_{uuid.uuid4()}")
                with open(eng_path, "wb") as buffer:
                    shutil.copyfileobj(engagement_letter.file, buffer)
                if engagement_letter.filename.lower().endswith(".pdf"):
                    if is_valid_pdf(eng_path):
                        engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)
                else:
                    with open(eng_path, "rb") as f:
                        engagement_text = f.read().decode('utf-8', errors='ignore')

            # Process contract / purchase agreement if provided
            contract_text = None
            if contract_file:
                con_path = os.path.join(temp_dir, f"qc_con_{uuid.uuid4()}")
                with open(con_path, "wb") as buffer:
                    shutil.copyfileobj(contract_file.file, buffer)
                if contract_file.filename.lower().endswith(".pdf"):
                    if is_valid_pdf(con_path):
                        contract_text = await run_in_threadpool(extract_text_from_pdf, con_path)
                else:
                    with open(con_path, "rb") as f:
                        contract_text = f.read().decode('utf-8', errors='ignore')

            # Run QC processor in threadpool
            processor = get_qc_processor()
            results = await run_in_threadpool(
                processor.process_document,
                pdf_path=pdf_path,
                engagement_letter_text=engagement_text,
                contract_text=contract_text,
                file_hash=file_hash,
                original_filename=file.filename,
            )

            logger.info("QC processing completed", extra={"request_id": request_id})
            payload = results.model_dump()
            payload["file_hash"] = file_hash
            return payload
            
    except HTTPException:
        raise
    except fitz.FileDataError:
        logger.error("Corrupted PDF in process_qc", extra={"request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        logger.error("QC Processing error", extra={"error": str(e), "request_id": request_id}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "QC_PROCESSING_ERROR", "message": str(e)}
        )


@app.get("/qc/rules")
async def list_qc_rules():
    """List all registered QC rules with DB configuration (Phase 3)."""
    from app.rule_engine.engine import engine
    from app.rule_engine.rules_db import load_rule_configs

    configs = load_rule_configs()
    rules_info = []
    counts = {"Subject": 0, "Contract": 0, "Narrative": 0, "Other": 0}

    for rule_id, rule_func in engine._rules.items():
        cfg = configs.get(rule_id)
        if rule_id.startswith("S-"):
            category = "Subject Section"
            counts["Subject"] += 1
        elif rule_id.startswith("C-"):
            category = "Contract Section"
            counts["Contract"] += 1
        elif rule_id.startswith("N-"):
            category = "Narrative Section"
            counts["Narrative"] += 1
        else:
            category = "Other"
            counts["Other"] += 1

        rules_info.append({
            "id": rule_id,
            "name": getattr(rule_func, "rule_name", rule_func.__name__),
            "category": category,
            "is_active": cfg.is_active if cfg else True,
            "severity": cfg.severity if cfg else "STANDARD",
            "execution_order": cfg.execution_order if cfg else 999,
            "applicable_loan_types": cfg.applicable_loan_types if cfg else "ALL",
            "doc": rule_func.__doc__[:150] if rule_func.__doc__ else None,
        })

    rules_info.sort(key=lambda r: r["execution_order"])
    return {
        "total_rules": len(rules_info),
        "active_rules": sum(1 for r in rules_info if r["is_active"]),
        "categories": counts,
        "rules": rules_info,
    }


@app.post("/admin/retrain")
async def trigger_retraining(
    request: Request,
    _auth: None = Security(_require_api_key),
    synthetic: bool = False,
):
    """
    Phase 6: Trigger the ML retraining pipeline manually.

    - Pulls all unprocessed feedback_events from the DB
    - Retrains: OCR correction model, commentary classifier, confidence model
    - Only deploys a new model if its accuracy improves over the current version
    - Marks all processed feedback as used_for_training=True
    - If ?synthetic=true: generates 30 synthetic examples first (useful for testing)

    Runs synchronously (blocks until complete — typically 5–30 seconds).
    For production, wire to a Celery task instead.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.info("Retraining triggered", extra={"request_id": request_id, "synthetic": synthetic})

    try:
        import sys
        sys.path.insert(0, "/Users/eaglexmac/Documents/functionalProject/ardur/apprisal/apprisalArdur/ocr-service")
        from training.retrain import run_retraining, generate_synthetic_feedback

        if synthetic:
            n = generate_synthetic_feedback(30)
            logger.info("Generated %d synthetic examples", n, extra={"request_id": request_id})

        result = await run_in_threadpool(run_retraining)
        return result

    except Exception as e:
        logger.error("Retraining failed: %s", e, extra={"request_id": request_id}, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "RETRAIN_FAILED", "message": str(e)})


@app.patch("/admin/rules/{rule_id}")
async def toggle_rule(rule_id: str, is_active: bool):
    """
    Toggle a rule on or off without restarting the server (Phase 3).
    Example: PATCH /admin/rules/S-5?is_active=false
    """
    try:
        from app.database import get_db
        from app.models.db_models import RuleConfig
        with get_db() as db:
            row = db.query(RuleConfig).filter(RuleConfig.rule_id == rule_id).first()
            if not row:
                raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found in DB config")
            row.is_active = is_active
        return {"rule_id": rule_id, "is_active": is_active, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr/appraisal", response_model=OcrResponse)
async def process_appraisal(request: Request, file: UploadFile = File(...)):
    """
    Process an appraisal PDF and extract key fields.
    """
    start_time = time.time()
    warnings = []
    request_id = getattr(request.state, "request_id", None)

    # Validate file type
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        logger.warning("Invalid file type", extra={"uploaded_filename": file.filename, "request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"}
        )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Stream file to disk
            tmp_path = os.path.join(temp_dir, f"ocr_input_{uuid.uuid4()}.pdf")
            with open(tmp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Security: Magic Byte Check
            if not is_valid_pdf(tmp_path):
                 raise HTTPException(
                    status_code=400,
                    detail={"error": "INVALID_FILE_CONTENT", "message": "File does not appear to be a valid PDF"}
                )

            logger.info("Starting simple OCR", extra={"uploaded_filename": file.filename, "request_id": request_id})
            
            # Run CPU-bound extraction in threadpool
            raw_text = await run_in_threadpool(extract_text_from_pdf, tmp_path)
            
            if not raw_text or len(raw_text.strip()) < 50:
                msg = "Low text content extracted from PDF"
                warnings.append(msg)
                logger.warning(msg, extra={"request_id": request_id})
            
            # Run parsing logic in threadpool (it involves many regexes)
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
                rawText=raw_text[:5000] if raw_text else None,  # Limit raw text
                warnings=warnings
            )

    except HTTPException:
        raise
    except fitz.FileDataError:
        logger.error("Corrupted PDF", extra={"request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        logger.error("Processing error", extra={"error": str(e), "request_id": request_id}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "PROCESSING_ERROR", "message": str(e)}
        )


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from all pages of a PDF using specialized OCR Pipeline."""
    pipeline = OCRPipeline(force_image_ocr=True)
    try:
        result = pipeline.extract_all_pages(pdf_path)
        return pipeline.get_full_text(result.page_index)
    except Exception as e:
        logger.error(f"OCR Pipeline failed: {e}")
        # Fallback to simple extraction if something catastrophic happens
        doc = fitz.open(pdf_path)
        text = "\n\n".join([page.get_text() for page in doc])
        doc.close()
        return text


def extract_fields(text: str) -> Dict[str, Any]:
    """Extract appraisal fields using regex patterns."""
    fields = {}
    
    # Borrower Name patterns
    borrower_patterns = [
        r"Borrower[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
        r"BORROWER[:\s]+([A-Z\s]+)",
        r"Borrower Name[:\s]+([^\n]+)",
    ]
    fields['borrowerName'] = extract_first_match(text, borrower_patterns)
    
    # Property Address patterns
    address_patterns = [
        r"Property Address[:\s]+([^\n]+)",
        r"Subject Property[:\s]+([^\n]+)",
        r"Address[:\s]+(\d+[^,\n]+(?:,\s*[^,\n]+){0,2})",
    ]
    fields['propertyAddress'] = extract_first_match(text, address_patterns)
    
    # Parse address components if found
    if fields['propertyAddress']:
        address_parts = parse_address(fields['propertyAddress'])
        fields.update(address_parts)
    
    # Appraised Value patterns
    value_patterns = [
        r"Appraised Value[:\s]*\$?([\d,]+)",
        r"APPRAISED VALUE[:\s]*\$?([\d,]+)",
        r"Market Value[:\s]*\$?([\d,]+)",
        r"Opinion of Value[:\s]*\$?([\d,]+)",
    ]
    value_str = extract_first_match(text, value_patterns)
    if value_str:
        fields['appraisedValue'] = parse_money(value_str)
    
    # Sale Price patterns
    sale_patterns = [
        r"Sale Price[:\s]*\$?([\d,]+)",
        r"Contract Price[:\s]*\$?([\d,]+)",
        r"Purchase Price[:\s]*\$?([\d,]+)",
    ]
    sale_str = extract_first_match(text, sale_patterns)
    if sale_str:
        fields['salePrice'] = parse_money(sale_str)
    
    # Effective Date patterns
    date_patterns = [
        r"Effective Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"Date of Value[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"As of[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    fields['effectiveDate'] = extract_first_match(text, date_patterns)
    
    # Lender Name patterns
    lender_patterns = [
        r"Lender[:\s]+([^\n]+)",
        r"Client[:\s]+([^\n]+)",
        r"Lender/Client[:\s]+([^\n]+)",
    ]
    fields['lenderName'] = extract_first_match(text, lender_patterns)
    
    # Appraiser patterns
    appraiser_patterns = [
        r"Appraiser[:\s]+([^\n]+)",
        r"Signed[:\s]+([^\n]+)",
    ]
    fields['appraiserName'] = extract_first_match(text, appraiser_patterns)
    
    # License number patterns
    license_patterns = [
        r"License\s*#?\s*:?\s*([A-Z]{2}[-\s]?\d+)",
        r"State License[:\s]+([^\n]+)",
        r"Certification\s*#?\s*:?\s*([A-Z0-9-]+)",
    ]
    fields['appraiserLicenseNumber'] = extract_first_match(text, license_patterns)
    
    return fields


def extract_first_match(text: str, patterns: list) -> Optional[str]:
    """Try multiple regex patterns and return the first match."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def parse_address(address: str) -> Dict[str, str]:
    """Parse address into components."""
    result = {}
    
    # Try to extract city, state, zip
    # Pattern: City, ST 12345 or City ST 12345
    state_zip = re.search(r'([A-Za-z\s]+),?\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)', address)
    if state_zip:
        result['city'] = state_zip.group(1).strip()
        result['state'] = state_zip.group(2)
        result['zipCode'] = state_zip.group(3)
    
    return result


def parse_money(value_str: str) -> Optional[float]:
    """Parse a money string to float."""
    try:
        # Remove commas and dollar signs
        cleaned = re.sub(r'[,$]', '', value_str)
        return float(cleaned)
    except:
        return None


def detect_form_type(text: str) -> Optional[str]:
    """Detect the appraisal form type."""
    form_patterns = {
        "1004": [r"Uniform Residential Appraisal Report", r"URAR", r"Form 1004"],
        "1025": [r"Small Residential Income Property", r"Form 1025"],
        "1073": [r"Individual Condominium", r"Form 1073"],
        "2055": [r"Exterior-Only Inspection", r"Form 2055"],
    }
    
    text_upper = text.upper()
    for form_type, patterns in form_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return form_type
    
    return None


def extract_checkboxes(text: str) -> Dict[str, bool]:
    """Extract checkbox/boolean fields from text."""
    checkboxes = {
        'isInFloodZone': False,
        'isForSale': False,
        'hasPoolOrSpa': False,
        'isCondoOrPUD': False,
        'isPud': False,
        'isManufacturedHome': False,
        'didAnalyzeContract': False,
    }
    
    text_lower = text.lower()
    
    # Check for flood zone
    if re.search(r'flood\s*(zone|area|hazard).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isInFloodZone'] = True
    
    # Check for sale status
    if re.search(r'(for sale|currently listed|on market).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isForSale'] = True
    
    # Check for pool/spa
    if re.search(r'(pool|spa).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['hasPoolOrSpa'] = True
    
    # Check for condo/PUD
    if re.search(r'(condo|pud|planned unit).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isCondoOrPUD'] = True
    
    # Check for manufactured home
    if re.search(r'(manufactured|mobile|modular).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isManufacturedHome'] = True
    
    return checkboxes


def calculate_confidence(fields: Dict[str, Any], raw_text: str) -> float:
    """Calculate a confidence score based on extraction quality."""
    score = 0.5  # Base score
    
    # Key fields that should be present
    key_fields = ['borrowerName', 'propertyAddress', 'appraisedValue']
    
    for field in key_fields:
        if fields.get(field):
            score += 0.1
    
    # Additional fields
    optional_fields = ['lenderName', 'effectiveDate', 'salePrice', 'appraiserName']
    for field in optional_fields:
        if fields.get(field):
            score += 0.05
    
    # Penalize if text is very short
    if len(raw_text) < 1000:
        score -= 0.2
    
    # Cap score between 0 and 1
    return max(0.0, min(1.0, score))


# ── Feedback models ────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    document_id: str
    rule_id: Optional[str] = None
    field_name: Optional[str] = None
    original_value: Optional[str] = None
    corrected_value: Optional[str] = None
    feedback_type: str = "CORRECTION"   # CORRECT / OCR_ERROR / EXTRACTION_ERROR / RULE_ERROR
    operator_comment: Optional[str] = None


@app.post("/qc/feedback")
async def submit_feedback(payload: FeedbackRequest, request: Request):
    """
    Phase 5: Store an operator correction for the learning loop.

    Every correction becomes a training example (Phase 6).
    """
    request_id = getattr(request.state, "request_id", None)

    try:
        import uuid as _uuid
        from app.database import get_db
        from app.models.db_models import FeedbackEvent, TrainingExample

        doc_uuid = _uuid.UUID(payload.document_id)

        with get_db() as db:
            event = FeedbackEvent(
                document_id=doc_uuid,
                rule_id=payload.rule_id,
                field_name=payload.field_name,
                original_value=payload.original_value,
                corrected_value=payload.corrected_value,
                operator_comment=payload.operator_comment,
                original_status=payload.feedback_type,
                corrected_status=payload.feedback_type,
                used_for_training=False,
            )
            db.add(event)
            db.flush()

            # Auto-generate training example for OCR corrections
            if payload.feedback_type == "OCR_ERROR" and payload.original_value and payload.corrected_value:
                db.add(TrainingExample(
                    feature_type="ocr_correction",
                    input_text=payload.original_value,
                    label=payload.corrected_value,
                    source_feedback_id=event.id,
                ))
                # Invalidate the learned-corrections cache so this applies immediately
                try:
                    from app.services.ocr_correction import invalidate_learned_cache
                    invalidate_learned_cache()
                except Exception:
                    pass

        logger.info(
            "Feedback stored",
            extra={"document_id": payload.document_id, "rule_id": payload.rule_id,
                   "feedback_type": payload.feedback_type, "request_id": request_id}
        )
        return {"success": True, "message": "Feedback recorded. Thank you."}

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document_id format.")
    except Exception as e:
        logger.error("Feedback save error: %s", e, extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket: real-time processing progress ──────────────────────────────────

@app.websocket("/qc/ws")
async def qc_websocket(websocket: WebSocket):
    """
    Phase 5: WebSocket for real-time processing progress.

    Client sends JSON: {"appraisal_b64": "...", "engagement_b64": "...", "contract_b64": "..."}
    Server pushes progress events then final results.

    Progress format: {"event": "progress", "stage": "ocr", "page": 5, "total": 27, "message": "..."}
    Result format:   {"event": "complete", "data": {...qc_results...}}
    Error format:    {"event": "error",    "message": "..."}
    """
    await websocket.accept()
    request_id = str(__import__("uuid").uuid4())

    try:
        import json as _json, base64, tempfile, shutil

        msg = await websocket.receive_json()
        appraisal_b64  = msg.get("appraisal_b64")
        engagement_b64 = msg.get("engagement_b64")
        contract_b64   = msg.get("contract_b64")

        if not appraisal_b64:
            await websocket.send_json({"event": "error", "message": "appraisal_b64 required"})
            return

        await websocket.send_json({"event": "progress", "stage": "upload",
                                   "message": "Files received. Starting validation..."})

        with tempfile.TemporaryDirectory() as tmp:
            # Write files
            pdf_path = f"{tmp}/appraisal.pdf"
            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(appraisal_b64))

            err = validate_upload(pdf_path, request_id)
            if err:
                await websocket.send_json({"event": "error", "message": err})
                return

            file_hash = sha256_file(pdf_path)
            await websocket.send_json({"event": "progress", "stage": "ocr",
                                       "message": "Extracting text from PDF...", "hash": file_hash})

            engagement_text = None
            if engagement_b64:
                eng_path = f"{tmp}/engagement.pdf"
                with open(eng_path, "wb") as f:
                    f.write(base64.b64decode(engagement_b64))
                engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)

            contract_text = None
            if contract_b64:
                con_path = f"{tmp}/contract.pdf"
                with open(con_path, "wb") as f:
                    f.write(base64.b64decode(contract_b64))
                contract_text = await run_in_threadpool(extract_text_from_pdf, con_path)

            await websocket.send_json({"event": "progress", "stage": "rules",
                                       "message": "Running compliance rules..."})

            processor = get_qc_processor()
            results = await run_in_threadpool(
                processor.process_document,
                pdf_path=pdf_path,
                engagement_letter_text=engagement_text,
                contract_text=contract_text,
                file_hash=file_hash,
                original_filename="upload.pdf",
            )

            payload = results.model_dump()
            payload["file_hash"] = file_hash
            await websocket.send_json({"event": "complete", "data": payload})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected", extra={"request_id": request_id})
    except Exception as e:
        logger.error("WebSocket error: %s", e, extra={"request_id": request_id})
        try:
            await websocket.send_json({"event": "error", "message": str(e)})
        except Exception:
            pass


def sha256_file(file_path: str) -> str:
    """Return the SHA-256 hex digest of a file — used for deduplication cache key."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_upload(file_path: str, request_id: str = None) -> Optional[str]:
    """
    Run Phase 1 ingestion checks after the file is written to disk.
    Returns an error message string if invalid, None if OK.
    """
    size = os.path.getsize(file_path)
    if size > MAX_FILE_SIZE_BYTES:
        mb = size / (1024 * 1024)
        logger.warning("File too large: %.1f MB", mb, extra={"request_id": request_id})
        return f"File size {mb:.1f} MB exceeds the 50 MB limit."

    if not is_valid_pdf(file_path):
        logger.warning("Invalid PDF magic bytes", extra={"request_id": request_id})
        return "File does not appear to be a valid PDF."

    try:
        import fitz as _fitz
        doc = _fitz.open(file_path)
        pages = len(doc)
        doc.close()
        if pages > MAX_PAGE_COUNT:
            logger.warning("Page count %d exceeds limit %d", pages, MAX_PAGE_COUNT, extra={"request_id": request_id})
            return f"Document has {pages} pages — maximum allowed is {MAX_PAGE_COUNT}."
    except Exception:
        return "Could not read PDF page count — file may be corrupted."

    return None


def is_valid_pdf(file_path: str) -> bool:
    """
    Check if the file has the PDF magic header %PDF-
    This prevents standard executables renamed as .pdf from being processed by some tools,
    though PyMuPDF is generally robust, this is a good security practice.
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(5)
            # Many PDFs start with %PDF-, but some start with garbage followed by %PDF-
            # For strictness we check the first 5 bytes. 
            # If we want to be looser: return b'%PDF-' in open(file_path, 'rb').read(1024)
            return header.startswith(b'%PDF-')
    except Exception:
        return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS ENDPOINTS  — operator-safe, no ML/OCR jargon exposed
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta
from typing import Optional
import statistics

_analytics_store: list[dict] = []   # in-process ring buffer (max 10000 entries)
_MAX_STORE = 10_000

def _record_metric(data: dict) -> None:
    """Append a processing event to the in-memory analytics ring buffer."""
    _analytics_store.append({**data, "ts": datetime.utcnow().isoformat()})
    while len(_analytics_store) > _MAX_STORE:
        _analytics_store.pop(0)


@app.get("/analytics/summary", tags=["analytics"])
async def analytics_summary(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Overall processing health for the last N days (default 30)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = [r for r in _analytics_store if r.get("ts","") >= cutoff.isoformat()]

    if not recent:
        return {
            "status": "ok",
            "period_days": days,
            "files_processed": 0,
            "avg_accuracy_pct": None,
            "avg_processing_seconds": None,
            "cache_hit_rate_pct": None,
            "message": "No data yet for this period."
        }

    confs   = [r["ocr_confidence"] for r in recent if r.get("ocr_confidence") is not None]
    times   = [r["processing_ms"]  for r in recent if r.get("processing_ms")  is not None]
    cached  = sum(1 for r in recent if r.get("cache_hit"))

    return {
        "status": "ok",
        "period_days": days,
        "files_processed": len(recent),
        "avg_accuracy_pct": round(statistics.mean(confs), 1) if confs else None,
        "avg_processing_seconds": round(statistics.mean(times) / 1000, 1) if times else None,
        "cache_hit_rate_pct": round(cached / len(recent) * 100, 1),
        "min_accuracy_pct": round(min(confs), 1) if confs else None,
        "max_processing_seconds": round(max(times) / 1000, 1) if times else None,
    }


@app.get("/analytics/rules", tags=["analytics"])
async def analytics_rules(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Per-rule pass/fail counts to show which rules are most commonly triggered."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = [r for r in _analytics_store if r.get("ts","") >= cutoff.isoformat()]

    rule_counts: dict[str, dict] = {}
    for record in recent:
        for rule in record.get("rule_results", []):
            rid  = rule.get("rule_id", "unknown")
            stat = rule.get("status", "unknown")
            if rid not in rule_counts:
                rule_counts[rid] = {"rule_id": rid, "rule_name": rule.get("rule_name",""), "pass": 0, "fail": 0, "verify": 0, "skip": 0}
            if stat == "PASS":   rule_counts[rid]["pass"]   += 1
            elif stat == "FAIL": rule_counts[rid]["fail"]   += 1
            elif stat in ("VERIFY","WARNING"): rule_counts[rid]["verify"] += 1
            else:                rule_counts[rid]["skip"]   += 1

    rows = sorted(rule_counts.values(), key=lambda x: x["fail"] + x["verify"], reverse=True)
    return {"status": "ok", "period_days": days, "rules": rows}


@app.get("/analytics/model-health", tags=["analytics"])
async def model_health(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Model performance in plain language: how confident the system is, trend over time."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = [r for r in _analytics_store if r.get("ts","") >= cutoff.isoformat()]

    confs = [r["ocr_confidence"] for r in recent if r.get("ocr_confidence") is not None]
    avg   = round(statistics.mean(confs), 1) if confs else None

    # Simple trend: compare first half vs second half of the period
    trend = "stable"
    if len(confs) >= 10:
        half  = len(confs) // 2
        first = statistics.mean(confs[:half])
        second = statistics.mean(confs[half:])
        if second - first > 2:   trend = "improving"
        elif first - second > 2: trend = "declining"

    confidence_label = "unknown"
    if avg is not None:
        if avg >= 85:   confidence_label = "high"
        elif avg >= 70: confidence_label = "medium"
        else:           confidence_label = "low"

    low_confidence_files = sum(1 for c in confs if c < 70)

    return {
        "status": "ok",
        "period_days": days,
        "avg_confidence_pct": avg,
        "confidence_level": confidence_label,
        "trend": trend,
        "files_analysed": len(recent),
        "files_needing_attention": low_confidence_files,
        "guidance": (
            "System is working well — no action needed." if confidence_label == "high" else
            "Some files had lower confidence. Review flagged items." if confidence_label == "medium" else
            "Confidence is low. Contact your system administrator."
        )
    }


@app.get("/analytics/operator-view", tags=["analytics"])
async def operator_analytics(
    days: int = 7,
    _auth: None = Security(_require_api_key)
):
    """Simple metrics an operator can understand: files done, time saved, issues found."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = [r for r in _analytics_store if r.get("ts","") >= cutoff.isoformat()]

    issues_found  = sum(r.get("failed_rules", 0)  for r in recent)
    needs_review  = sum(r.get("verify_rules", 0)  for r in recent)
    auto_passed   = sum(1 for r in recent if r.get("decision") == "AUTO_PASS")
    cache_hits    = sum(1 for r in recent if r.get("cache_hit"))

    return {
        "status": "ok",
        "period_days": days,
        "files_checked": len(recent),
        "issues_found": issues_found,
        "items_need_your_review": needs_review,
        "files_passed_automatically": auto_passed,
        "time_saved_by_cache_minutes": round(cache_hits * 0.25, 1),
        "summary": f"{len(recent)} files checked, {issues_found} issues found, {needs_review} need your review."
    }
