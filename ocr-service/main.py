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

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

app = FastAPI(
    title="Appraisal OCR Service",
    description="Extracts key fields from appraisal PDF documents",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
async def process_qc(
    request: Request,
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
    """
    List all registered QC rules.
    """
    from app.rule_engine.engine import engine
    
    rules_info = []
    subject_rules_count = 0
    contract_rules_count = 0
    
    for rule_func in engine._rules:
        rule_id = getattr(rule_func, 'rule_id', 'UNKNOWN')
        rule_name = getattr(rule_func, 'rule_name', rule_func.__name__)
        
        # Categorize rules
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
    
    logger.debug(
        "Listed QC rules", 
        extra={
            "total_rules": len(rules_info),
            "subject_rules": subject_rules_count,
            "contract_rules": contract_rules_count
        }
    )

    return {
        "total_rules": len(rules_info),
        "categories": {
            "subject_section": subject_rules_count,
            "contract_section": contract_rules_count
        },
        "rules": rules_info
    }


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
