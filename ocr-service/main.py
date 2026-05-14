"""
OCR Microservice for Appraisal Document Processing
FastAPI application that extracts fields from appraisal PDFs.
"""

import hashlib
import json
import logging
import os
import re
import time
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

_SERVICE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVICE_DIR.parent
_ROOT_ENV = _PROJECT_ROOT / ".env"
_SERVICE_ENV = _SERVICE_DIR / ".env"


def _defined_env_names(path: Path, names: set[str]) -> set[str]:
    if not path.is_file():
        return set()

    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in names:
            found.add(key)
    return found


# Shared auth lives in the project root .env. The service-local .env may contain
# Python-only settings, but must never duplicate the Java/Python shared API key.
_DUPLICATED_API_KEY_NAMES = _defined_env_names(_SERVICE_ENV, {"INTERNAL_API_KEY", "PYTHON_API_KEY"})
if _DUPLICATED_API_KEY_NAMES:
    names = ", ".join(sorted(_DUPLICATED_API_KEY_NAMES))
    raise RuntimeError(
        f"Do not define {names} in {_SERVICE_ENV}. Define INTERNAL_API_KEY once in {_ROOT_ENV}."
    )
load_dotenv(_SERVICE_ENV, override=False)
load_dotenv(_ROOT_ENV, override=False)

os.environ.setdefault("TZ", "Asia/Kolkata")
if hasattr(time, "tzset"):
    time.tzset()

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request, WebSocket, WebSocketDisconnect, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field as PydanticField
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
from app.services import processing_lifecycle

# Import rules at startup so @rule decorators register against the global engine
import app.rules  # noqa: F401  (side-effect import)

# Seed DB rule config (idempotent — does nothing if already seeded)
from app.database import ensure_schema_compatibility
from app.rule_engine.rules_db import seed_rules_config
ensure_schema_compatibility()
seed_rules_config()

_IST = ZoneInfo("Asia/Kolkata")
_LOG_RECORD_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"asctime", "message"}


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _flow_log(event: str, *, started: Optional[float] = None, level: str = "info", **fields: Any) -> None:
    payload: Dict[str, Any] = {
        "flow": "admin_batches",
        "event": event,
        "ist": datetime.now(_IST).isoformat(),
        "pid": os.getpid(),
        **fields,
    }
    if started is not None:
        payload["elapsed_ms"] = _elapsed_ms(started)

    # logging.extra cannot contain reserved LogRecord attributes such as
    # "filename", "module", or "thread". Rename collisions so observability
    # never breaks the request path.
    safe_payload = {
        (f"field_{key}" if key in _LOG_RECORD_RESERVED else key): value
        for key, value in payload.items()
    }
    getattr(logger, level)("admin_batches_timeline", extra=safe_payload)

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

try:
    from app.observability import setup_observability
    setup_observability(app)
except Exception as exc:
    logger.debug("OpenTelemetry setup skipped: %s", exc)

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
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Correlation-ID", "traceparent", "tracestate"],
)

# ── API-Key authentication ─────────────────────────────────────────────────────
_API_KEY = os.getenv("INTERNAL_API_KEY")
if not _API_KEY or not _API_KEY.strip():
    raise RuntimeError(
        f"Missing required INTERNAL_API_KEY. Define it once in {_ROOT_ENV} before starting Python."
    )
_API_KEY = _API_KEY.strip()
_flow_log(
    "python_service_ready",
    root_env=str(_ROOT_ENV),
    service_env=str(_SERVICE_ENV),
    api_key_configured=True,
)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def _require_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Validate X-API-Key header."""
    if api_key != _API_KEY:
        received_hint = (api_key[:6] + "...") if (api_key and len(api_key) > 6) else repr(api_key)
        expected_hint = _API_KEY[:6] + "..."
        _flow_log(
            "python_auth_failed",
            level="warning",
            received_hint=received_hint,
            expected_hint=expected_hint,
        )
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Auth failure: X-API-Key mismatch. received=%s expected=%s. "
            "Java and Python must both load INTERNAL_API_KEY from the project root .env.",
            received_hint, expected_hint,
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHORIZED",
                "message": "Invalid or missing X-API-Key header",
                "hint": "Java ocr.service.api-key and Python INTERNAL_API_KEY must come from the same root .env",
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )


def _require_ws_api_key(websocket: WebSocket) -> bool:
    supplied = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    return supplied == _API_KEY


def _require_durable_job(job_id: Optional[str]) -> str:
    if job_id:
        return job_id
    raise HTTPException(
        status_code=503,
        detail={
            "error": "OCR_DB_UNAVAILABLE",
            "message": "Python OCR cannot process documents without a durable processing job.",
        },
    )


_UPLOAD_CHUNK_BYTES = 1024 * 1024
_SUPPORTING_FILE_SIZE_BYTES = int(os.getenv("SUPPORTING_FILE_SIZE_BYTES", str(MAX_FILE_SIZE_BYTES)))
_ENV_FILE_SIZE_BYTES = int(os.getenv("ENV_FILE_SIZE_BYTES", str(2 * 1024 * 1024)))


def _payload_too_large(label: str, max_bytes: int) -> HTTPException:
    mb = max_bytes / (1024 * 1024)
    return HTTPException(
        status_code=413,
        detail={"error": "PAYLOAD_TOO_LARGE", "message": f"{label} exceeds the {mb:.1f} MB limit"},
    )


def _copy_upload_limited(
    upload: UploadFile,
    destination: str,
    *,
    max_bytes: int = MAX_FILE_SIZE_BYTES,
    label: str = "file",
) -> int:
    """Stream an UploadFile to disk while enforcing a hard byte limit."""
    total = 0
    with open(destination, "wb") as buffer:
        while True:
            chunk = upload.file.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _payload_too_large(label, max_bytes)
            buffer.write(chunk)
    if total == 0:
        raise HTTPException(
            status_code=400,
            detail={"error": "EMPTY_FILE", "message": f"{label} is empty"},
        )
    return total


async def _read_upload_limited(upload: UploadFile, *, max_bytes: int, label: str) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _payload_too_large(label, max_bytes)
    return data


def _decode_b64_document(value: str, *, label: str, max_bytes: int = MAX_FILE_SIZE_BYTES) -> bytes:
    """Decode a WebSocket base64 document with size and format checks."""
    import base64
    import binascii

    if "," in value and value.strip().lower().startswith("data:"):
        value = value.split(",", 1)[1]
    compact = re.sub(r"\s+", "", value or "")
    estimated_bytes = (len(compact) * 3) // 4
    if estimated_bytes > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes / (1024 * 1024):.1f} MB limit")
    try:
        data = base64.b64decode(compact, validate=True)
    except binascii.Error as exc:
        raise ValueError(f"{label} is not valid base64") from exc
    if not data:
        raise ValueError(f"{label} is empty")
    if len(data) > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes / (1024 * 1024):.1f} MB limit")
    return data


def _fail_job_for_http_exception(job_id: Optional[str], exc: HTTPException) -> None:
    if not job_id or exc.status_code == 409:
        return
    detail = exc.detail
    reason = detail if isinstance(detail, str) else json.dumps(detail, default=str)
    stage = "input_validation" if exc.status_code < 500 else None
    processing_lifecycle.fail_job(job_id, reason, stage)


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
            "correlation_id": request.headers.get("x-correlation-id"),
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
                "request_id": request_id,
                "correlation_id": request.headers.get("x-correlation-id"),
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
                "request_id": request_id,
                "correlation_id": request.headers.get("x-correlation-id"),
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
    processingJobId: Optional[str] = None
    documentId: Optional[str] = None
    fileHash: Optional[str] = None
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


async def _check_ollama_readiness() -> dict:
    """Probe Ollama for reachability and required model availability."""
    required_model = os.getenv("OLLAMA_TEXT_MODEL", "llava:7b")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
        if resp.status_code != 200:
            return {"reachable": False, "model_available": False,
                    "error": f"Ollama HTTP {resp.status_code}"}
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        base = required_model.split(":")[0]
        available = any(base in m for m in models)
        return {"reachable": True, "model_available": available,
                "required_model": required_model, "loaded_models": models}
    except Exception as exc:
        return {"reachable": False, "model_available": False, "error": str(exc)}


def _check_db_connection() -> bool:
    try:
        from app.database import get_db
        from sqlalchemy import text as _text
        with get_db() as db:
            db.execute(_text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_celery_worker() -> bool:
    """Return True if at least one Celery worker is connected to Redis."""
    try:
        from app.tasks.celery_app import celery_app as _celery
        # inspect().ping() returns {} when no workers respond; non-empty means at least one is up
        result = _celery.control.inspect(timeout=2.0).ping()
        return bool(result)
    except Exception:
        return False


@app.get("/live")
async def liveness():
    """Cheap liveness probe — Java calls this before every QC job instead of /health."""
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Full readiness check: binaries + DB + Ollama model readiness. Slow — do not call per-job."""
    binary_issues = validate_binaries()
    system_info = get_system_info()
    db_ok          = await run_in_threadpool(_check_db_connection)
    ollama         = await _check_ollama_readiness()
    celery_worker  = await run_in_threadpool(_check_celery_worker)

    degraded = bool(binary_issues) or not db_ok or not ollama.get("reachable")
    ready    = not degraded and ollama.get("model_available", False)
    status   = "ready" if ready else ("degraded" if degraded else "healthy")

    if degraded:
        logger.warning("Health check degraded",
                       extra={"binary_issues": binary_issues, "db_ok": db_ok, "ollama": ollama})
    else:
        logger.debug("Health check passed")

    return {
        "status": status,
        "ready": ready,
        "timestamp": datetime.utcnow().isoformat(),
        "tesseract_available": TESSERACT_AVAILABLE,
        "binary_issues": binary_issues,
        "db_connected": db_ok,
        "ollama": ollama,
        "celery_worker_running": celery_worker,
        "system_info": system_info,
        "ocr_config": {
            "tesseract_cmd": OCR_CONFIG['tesseract_cmd'],
            "pdf_dpi": OCR_CONFIG['pdf_dpi'],
            "max_workers": OCR_CONFIG['max_workers'],
        },
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
    correlation_id: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    batch_file_id: Optional[str] = Form(None),
    qc_result_id: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
):
    """
    Pure Fact Extraction Endpoint - Python sees, Java thinks, Humans decide.
    """
    request_id = getattr(request.state, "request_id", None)
    processing_job_id: Optional[str] = None
    
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
            _copy_upload_limited(file, pdf_path, label="appraisal PDF")
            
            err = validate_upload(pdf_path, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_FILE", "message": err})

            file_hash = sha256_file(pdf_path)
            effective_idempotency_key = idempotency_key or processing_lifecycle.make_idempotency_key(
                batch_file_id=batch_file_id,
                source_document_hash=file_hash,
                model_provider="fact-extract",
                model_name=None,
                vision_model=None,
            )
            processing_job_id, job_status, reused = processing_lifecycle.create_or_get_job(
                idempotency_key=effective_idempotency_key,
                source_document_hash=file_hash,
                original_filename=file.filename,
                correlation_id=correlation_id or request.headers.get("x-correlation-id"),
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                model_provider="fact-extract",
                model_name=None,
                vision_model=None,
                traceparent=request.headers.get("traceparent"),
                tracestate=request.headers.get("tracestate"),
            )
            processing_job_id = _require_durable_job(processing_job_id)
            if reused and job_status == "completed":
                existing = processing_lifecycle.get_job_status(processing_job_id)
                if existing and existing.get("result_json"):
                    payload = json.loads(existing["result_json"])
                    payload["file_hash"] = file_hash
                    payload["processing_job_id"] = processing_job_id
                    return payload
            if reused and job_status == "in_progress":
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id},
                )
            if not processing_lifecycle.try_claim_job(processing_job_id, stage="fact_extract_start"):
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id},
                )

            with processing_lifecycle.processing_context(
                processing_job_id,
                correlation_id or request.headers.get("x-correlation-id"),
                request.headers.get("traceparent"),
            ):
                # Process engagement letter if provided
                engagement_text = None
                if engagement_letter:
                    with processing_lifecycle.stage("supporting_engagement_read"):
                        eng_path = os.path.join(temp_dir, f"eng_{uuid.uuid4()}")
                        _copy_upload_limited(
                            engagement_letter,
                            eng_path,
                            max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                            label="engagement letter",
                        )
                        if engagement_letter.filename.lower().endswith('.pdf'):
                            err = validate_upload(eng_path, request_id)
                            if err:
                                raise HTTPException(
                                    status_code=400,
                                    detail={"error": "INVALID_ENGAGEMENT_FILE", "message": err},
                                )
                            engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)
                        else:
                            with open(eng_path, "rb") as f:
                                engagement_text = f.read().decode('utf-8', errors='ignore')
                
                # Read ENV file if provided
                env_content = None
                if env_file:
                    with processing_lifecycle.stage("env_file_read"):
                        env_content = await _read_upload_limited(
                            env_file,
                            max_bytes=_ENV_FILE_SIZE_BYTES,
                            label="ENV file",
                        )

                # Run extraction service in threadpool
                service = get_extraction_service()
                with processing_lifecycle.stage("fact_extraction"):
                    result = await run_in_threadpool(
                        service.extract_and_compare,
                        pdf_path=pdf_path,
                        engagement_letter_text=engagement_text,
                        env_content=env_content
                    )
            
            logger.info("Extraction completed successfully", extra={"request_id": request_id})
            payload = result.model_dump()
            payload["file_hash"] = file_hash
            payload["processing_job_id"] = processing_job_id
            processing_lifecycle.complete_job(processing_job_id, document_id=None, result_payload=payload)
            return payload
            
    except HTTPException as exc:
        _fail_job_for_http_exception(processing_job_id, exc)
        raise
    except fitz.FileDataError:
        processing_lifecycle.fail_job(processing_job_id, "PDF file is corrupted or encrypted", "input_validation")
        logger.error("Corrupted PDF", extra={"request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        processing_lifecycle.fail_job(processing_job_id, str(e))
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
    model_provider: str = Form("ollama"),
    text_model: Optional[str] = Form(None),
    vision_model: Optional[str] = Form(None),
    progress_token: Optional[str] = Form(None),
    correlation_id: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    batch_file_id: Optional[str] = Form(None),
    qc_result_id: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
):
    """
    Full QC pipeline: OCR → Extract → Subject & Contract Rules → Results

    - file: Appraisal PDF (required)
    - engagement_letter: Order form / engagement letter PDF (optional but recommended)
    - contract_file: Purchase agreement PDF (optional; used when appraisal indicates
      contract was analyzed, enables C-2/C-4/C-5 cross-checks)
    """
    request_id = getattr(request.state, "request_id", None)
    processing_job_id: Optional[str] = None
    flow_started = time.perf_counter()
    effective_correlation_id = correlation_id or request.headers.get("x-correlation-id")
    _flow_log(
        "python_qc_request_start",
        request_id=request_id,
        correlation_id=effective_correlation_id,
        batch_id=batch_id,
        batch_file_id=batch_file_id,
        qc_result_id=qc_result_id,
        filename=file.filename,
        has_engagement_letter=engagement_letter is not None,
        has_contract_file=contract_file is not None,
        model_provider=model_provider,
        text_model=text_model,
        vision_model=vision_model,
        progress_token=progress_token,
    )

    if not file.filename.lower().endswith('.pdf'):
        _flow_log(
            "python_qc_http_failed",
            started=flow_started,
            level="warning",
            request_id=request_id,
            correlation_id=effective_correlation_id,
            batch_id=batch_id,
            batch_file_id=batch_file_id,
            status_code=400,
            detail="Only PDF files are accepted",
        )
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
                "model_provider": model_provider,
                "text_model": text_model,
                "vision_model": vision_model,
                "request_id": request_id,
                "progress_token": progress_token,
            }
        )

        from app.services.progress_store import progress_store

        def _emit(stage: str, message: str, sub_percent: float) -> None:
            progress_store.set(progress_token, stage, message, sub_percent)

        _emit("starting", "Starting QC pipeline", 0.02)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Stream appraisal PDF to disk
            copy_started = time.perf_counter()
            pdf_path = os.path.join(temp_dir, f"qc_input_{uuid.uuid4()}.pdf")
            _copy_upload_limited(file, pdf_path, label="appraisal PDF")
            _flow_log(
                "python_qc_appraisal_saved",
                started=copy_started,
                request_id=request_id,
                correlation_id=effective_correlation_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                filename=file.filename,
                bytes=os.path.getsize(pdf_path),
            )

            err = validate_upload(pdf_path, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_FILE", "message": err})

            file_hash = sha256_file(pdf_path)
            effective_idempotency_key = idempotency_key or processing_lifecycle.make_idempotency_key(
                batch_file_id=batch_file_id,
                source_document_hash=file_hash,
                model_provider=model_provider,
                model_name=text_model,
                vision_model=vision_model,
            )
            processing_job_id, job_status, reused = processing_lifecycle.create_or_get_job(
                idempotency_key=effective_idempotency_key,
                source_document_hash=file_hash,
                original_filename=file.filename,
                correlation_id=correlation_id or request.headers.get("x-correlation-id"),
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                model_provider=model_provider,
                model_name=text_model,
                vision_model=vision_model,
                traceparent=request.headers.get("traceparent"),
                tracestate=request.headers.get("tracestate"),
            )
            processing_job_id = _require_durable_job(processing_job_id)
            _flow_log(
                "python_qc_job_ready",
                started=flow_started,
                request_id=request_id,
                correlation_id=effective_correlation_id,
                processing_job_id=processing_job_id,
                job_status=job_status,
                reused=reused,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                file_hash=file_hash,
            )
            if reused and job_status == "completed":
                existing = processing_lifecycle.get_job_status(processing_job_id)
                if existing and existing.get("result_json"):
                    payload = json.loads(existing["result_json"])
                    payload["file_hash"] = file_hash
                    payload["processing_job_id"] = processing_job_id
                    _flow_log(
                        "python_qc_return_cached_result",
                        started=flow_started,
                        request_id=request_id,
                        correlation_id=effective_correlation_id,
                        processing_job_id=processing_job_id,
                        batch_id=batch_id,
                        batch_file_id=batch_file_id,
                    )
                    return payload
            elif reused and job_status == "in_progress":
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id}
                )
            elif reused and job_status == "queued":
                logger.info(
                    "Taking over queued idempotent QC job via /qc/process",
                    extra={"processing_job_id": processing_job_id, "request_id": request_id},
                )

            if not processing_lifecycle.try_claim_job(processing_job_id, stage="sync_start"):
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id},
                )

            # Process engagement letter if provided
            engagement_text = None
            if engagement_letter:
                stage_started = time.perf_counter()
                _emit("ocr_engagement", "Reading engagement letter", 0.08)
                eng_path = os.path.join(temp_dir, f"qc_eng_{uuid.uuid4()}")
                _copy_upload_limited(
                    engagement_letter,
                    eng_path,
                    max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                    label="engagement letter",
                )
                if engagement_letter.filename.lower().endswith(".pdf"):
                    err = validate_upload(eng_path, request_id)
                    if err:
                        raise HTTPException(
                            status_code=400,
                            detail={"error": "INVALID_ENGAGEMENT_FILE", "message": err},
                        )
                    engagement_text = await run_in_threadpool(
                        extract_text_from_supporting_pdf,
                        eng_path,
                        "Engagement letter OCR",
                        engagement_letter.filename,
                    )
                else:
                    with open(eng_path, "rb") as f:
                        engagement_text = f.read().decode('utf-8', errors='ignore')
                _flow_log(
                    "python_qc_engagement_done",
                    started=stage_started,
                    request_id=request_id,
                    correlation_id=effective_correlation_id,
                    processing_job_id=processing_job_id,
                    batch_id=batch_id,
                    batch_file_id=batch_file_id,
                    filename=engagement_letter.filename,
                    chars=len(engagement_text or ""),
                )

            # Process contract / purchase agreement if provided
            contract_text = None
            if contract_file:
                stage_started = time.perf_counter()
                _emit("ocr_contract", "Reading purchase contract", 0.18)
                con_path = os.path.join(temp_dir, f"qc_con_{uuid.uuid4()}")
                _copy_upload_limited(
                    contract_file,
                    con_path,
                    max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                    label="contract file",
                )
                if contract_file.filename.lower().endswith(".pdf"):
                    err = validate_upload(con_path, request_id)
                    if err:
                        raise HTTPException(
                            status_code=400,
                            detail={"error": "INVALID_CONTRACT_FILE", "message": err},
                        )
                    contract_text = await run_in_threadpool(
                        extract_text_from_supporting_pdf,
                        con_path,
                        "Contract OCR",
                        contract_file.filename,
                    )
                else:
                    with open(con_path, "rb") as f:
                        contract_text = f.read().decode('utf-8', errors='ignore')
                _flow_log(
                    "python_qc_contract_done",
                    started=stage_started,
                    request_id=request_id,
                    correlation_id=effective_correlation_id,
                    processing_job_id=processing_job_id,
                    batch_id=batch_id,
                    batch_file_id=batch_file_id,
                    filename=contract_file.filename,
                    chars=len(contract_text or ""),
                )

            # Run QC processor in threadpool
            processor = get_qc_processor()
            def _run_processor():
                from app.services.ollama_service import ollama_request_guard, use_model_selection

                executable_text_model = text_model if model_provider.lower() == "ollama" else None
                if model_provider.lower() != "ollama":
                    logger.warning(
                        "Provider %s requested, but this service currently executes Ollama helpers; using default Ollama model.",
                        model_provider,
                        extra={"request_id": request_id}
                    )

                with ollama_request_guard():
                    with use_model_selection(text_model=executable_text_model, vision_model=vision_model):
                        return processor.process_document(
                            pdf_path=pdf_path,
                            engagement_letter_text=engagement_text,
                            contract_text=contract_text,
                            file_hash=file_hash,
                            original_filename=file.filename,
                            model_provider=model_provider,
                            model_name=text_model,
                            vision_model=vision_model,
                            report_progress=_emit,
                            processing_job_id=processing_job_id,
                            correlation_id=correlation_id or request.headers.get("x-correlation-id"),
                            batch_id=batch_id,
                            batch_file_id=batch_file_id,
                            qc_result_id=qc_result_id,
                            idempotency_key=effective_idempotency_key,
                            traceparent=request.headers.get("traceparent"),
                            tracestate=request.headers.get("tracestate"),
                        )

            processor_started = time.perf_counter()
            _flow_log(
                "python_qc_processor_start",
                started=flow_started,
                request_id=request_id,
                correlation_id=effective_correlation_id,
                processing_job_id=processing_job_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                filename=file.filename,
            )
            results = await run_in_threadpool(_run_processor)
            _flow_log(
                "python_qc_processor_complete",
                started=processor_started,
                request_id=request_id,
                correlation_id=effective_correlation_id,
                processing_job_id=processing_job_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                filename=file.filename,
                total_rules=results.total_rules,
                passed=results.passed,
                failed=results.failed,
                verify=results.verify,
                python_processing_ms=results.processing_time_ms,
            )

            _emit("complete", "QC pipeline complete", 1.0)
            logger.info("QC processing completed", extra={"request_id": request_id})
            payload = results.model_dump()
            payload["file_hash"] = file_hash
            payload["processing_job_id"] = processing_job_id
            processing_lifecycle.complete_job(processing_job_id, document_id=results.document_id, result_payload=payload)
            _flow_log(
                "python_qc_response_ready",
                started=flow_started,
                request_id=request_id,
                correlation_id=effective_correlation_id,
                processing_job_id=processing_job_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                total_rules=results.total_rules,
                passed=results.passed,
                failed=results.failed,
                verify=results.verify,
            )
            return payload
            
    except HTTPException as exc:
        _fail_job_for_http_exception(processing_job_id, exc)
        _flow_log(
            "python_qc_http_failed",
            started=flow_started,
            level="warning",
            request_id=request_id,
            correlation_id=effective_correlation_id,
            processing_job_id=processing_job_id,
            batch_id=batch_id,
            batch_file_id=batch_file_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise
    except fitz.FileDataError:
        processing_lifecycle.fail_job(processing_job_id, "PDF file is corrupted or encrypted", "input_validation")
        logger.error("Corrupted PDF in process_qc", extra={"request_id": request_id})
        _flow_log(
            "python_qc_failed",
            started=flow_started,
            level="error",
            request_id=request_id,
            correlation_id=effective_correlation_id,
            processing_job_id=processing_job_id,
            batch_id=batch_id,
            batch_file_id=batch_file_id,
            error="PDF file is corrupted or encrypted",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        processing_lifecycle.fail_job(processing_job_id, str(e))
        logger.error("QC Processing error", extra={"error": str(e), "request_id": request_id}, exc_info=True)
        _flow_log(
            "python_qc_failed",
            started=flow_started,
            level="error",
            request_id=request_id,
            correlation_id=effective_correlation_id,
            processing_job_id=processing_job_id,
            batch_id=batch_id,
            batch_file_id=batch_file_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "QC_PROCESSING_ERROR", "message": str(e)}
        )


# ── Async job queue (Celery) ──────────────────────────────────────────────────
# Jobs directory — files saved here survive until the Celery worker finishes.
# Keep this default in lockstep with app.tasks.celery_app._JOB_DIR_ROOT. The
# worker validates and later deletes job_dir, so /qc/submit must only create
# directories inside that same safe root.
_ASYNC_JOBS_DIR = os.path.realpath(
    os.getenv(
        "ASYNC_JOBS_DIR",
        os.getenv("JOB_DIR_ROOT", os.path.join(tempfile.gettempdir(), "apprisal_jobs")),
    )
)
os.makedirs(_ASYNC_JOBS_DIR, exist_ok=True, mode=0o700)


@app.post("/qc/submit", status_code=202)
@_limiter.limit("20/minute")
async def submit_qc_job(
    request: Request,
    _auth: None = Security(_require_api_key),
    file: UploadFile = File(...),
    engagement_letter: Optional[UploadFile] = None,
    contract_file: Optional[UploadFile] = None,
    model_provider: str = Form("ollama"),
    text_model: Optional[str] = Form(None),
    vision_model: Optional[str] = Form(None),
    correlation_id: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    batch_file_id: Optional[str] = Form(None),
    qc_result_id: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
):
    """
    Submit a QC job to the Celery async queue.

    Returns 202 immediately with a job_id.  Java polls GET /qc/job/{job_id}
    every few seconds until status == SUCCESS or FAILURE.

    The Celery worker must be running:
        celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1
    """
    request_id = getattr(request.state, "request_id", None)
    processing_job_id: Optional[str] = None

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400,
                            detail={"error": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted"})

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(_ASYNC_JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        # --- Save appraisal PDF ---
        pdf_path = os.path.join(job_dir, "appraisal.pdf")
        _copy_upload_limited(file, pdf_path, label="appraisal PDF")

        err = validate_upload(pdf_path, request_id)
        if err:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail={"error": "INVALID_FILE", "message": err})

        file_hash = sha256_file(pdf_path)
        effective_idempotency_key = idempotency_key or processing_lifecycle.make_idempotency_key(
            batch_file_id=batch_file_id,
            source_document_hash=file_hash,
            model_provider=model_provider,
            model_name=text_model,
            vision_model=vision_model,
        )
        processing_job_id, job_status, reused = processing_lifecycle.create_or_get_job(
            idempotency_key=effective_idempotency_key,
            source_document_hash=file_hash,
            original_filename=file.filename,
            correlation_id=correlation_id or request.headers.get("x-correlation-id"),
            batch_id=batch_id,
            batch_file_id=batch_file_id,
            qc_result_id=qc_result_id,
            model_provider=model_provider,
            model_name=text_model,
            vision_model=vision_model,
            traceparent=request.headers.get("traceparent"),
            tracestate=request.headers.get("tracestate"),
        )
        processing_job_id = _require_durable_job(processing_job_id)
        if reused:
            if job_status == "completed":
                shutil.rmtree(job_dir, ignore_errors=True)
                return {"job_id": processing_job_id, "status": "SUCCESS", "file_hash": file_hash,
                        "poll_url": f"/qc/job/{processing_job_id}", "reused": True}
            if job_status in {"queued", "in_progress"}:
                shutil.rmtree(job_dir, ignore_errors=True)
                return {"job_id": processing_job_id, "status": "QUEUED", "file_hash": file_hash,
                        "poll_url": f"/qc/job/{processing_job_id}", "reused": True}
        processing_lifecycle.mark_job_queued(processing_job_id, "queued")

        # --- Save optional supporting files ---
        engagement_path = None
        if engagement_letter:
            p = os.path.join(job_dir, "engagement.pdf")
            _copy_upload_limited(
                engagement_letter,
                p,
                max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                label="engagement letter",
            )
            err = validate_upload(p, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_ENGAGEMENT_FILE", "message": err})
            engagement_path = p

        contract_path = None
        if contract_file:
            p = os.path.join(job_dir, "contract.pdf")
            _copy_upload_limited(
                contract_file,
                p,
                max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                label="contract file",
            )
            err = validate_upload(p, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_CONTRACT_FILE", "message": err})
            contract_path = p

        # --- Enqueue Celery task ---
        from app.tasks.celery_app import process_document_async
        process_document_async.apply_async(
            task_id=processing_job_id or job_id,
            kwargs={
                "pdf_path": pdf_path,
                "file_hash": file_hash,
                "original_filename": file.filename,
                "engagement_path": engagement_path,
                "contract_path": contract_path,
                "model_provider": model_provider,
                "text_model": text_model,
                "vision_model": vision_model,
                "job_dir": job_dir,
                "processing_job_id": processing_job_id,
                "correlation_id": correlation_id or request.headers.get("x-correlation-id"),
                "batch_id": batch_id,
                "batch_file_id": batch_file_id,
                "qc_result_id": qc_result_id,
                "idempotency_key": effective_idempotency_key,
                "traceparent": request.headers.get("traceparent"),
                "tracestate": request.headers.get("tracestate"),
            },
        )

        logger.info("QC job queued", extra={"job_id": job_id, "file": file.filename,
                                             "request_id": request_id})
        return {"job_id": processing_job_id or job_id, "status": "QUEUED", "file_hash": file_hash,
                "poll_url": f"/qc/job/{processing_job_id or job_id}"}

    except HTTPException as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        _fail_job_for_http_exception(processing_job_id, exc)
        raise
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        processing_lifecycle.fail_job(processing_job_id, str(exc), "queue_submit")
        logger.error("Failed to queue QC job", extra={"error": str(exc), "request_id": request_id},
                     exc_info=True)
        raise HTTPException(status_code=500,
                            detail={"error": "QUEUE_ERROR", "message": str(exc)})


@app.get("/qc/job/{job_id}")
async def get_job_status(job_id: str, _auth: None = Security(_require_api_key)):
    """
    Poll the status of an async QC job submitted via POST /qc/submit.

    Returns:
        status  PENDING | STARTED | SUCCESS | FAILURE
        result  Full QC payload when status == SUCCESS, else null
        error   Error message when status == FAILURE, else null
    """
    try:
        tracked = processing_lifecycle.get_job_status(job_id)
        if tracked and tracked.get("status") == "completed" and tracked.get("result_json"):
            return {"job_id": job_id, "status": "SUCCESS", "result": json.loads(tracked["result_json"]), "error": None}
        if tracked and tracked.get("status") == "failed":
            return {"job_id": job_id, "status": "FAILURE", "result": None, "error": tracked.get("error")}
        if tracked and tracked.get("status") in {"queued", "in_progress"}:
            mapped = "STARTED" if tracked.get("status") == "in_progress" else "PENDING"
            return {"job_id": job_id, "status": mapped, "result": None, "error": None,
                    "meta": {"stage": tracked.get("stage"), "retry_count": tracked.get("retry_count", 0)}}

        from celery.result import AsyncResult
        from app.tasks.celery_app import celery_app as _celery
        ar = AsyncResult(job_id, app=_celery)
        state = ar.state

        if state == "SUCCESS":
            return {"job_id": job_id, "status": "SUCCESS", "result": ar.result, "error": None}
        elif state == "FAILURE":
            return {"job_id": job_id, "status": "FAILURE", "result": None,
                    "error": str(ar.result)}
        elif state == "STARTED":
            return {"job_id": job_id, "status": "STARTED", "result": None,
                    "meta": ar.info if isinstance(ar.info, dict) else {}}
        else:
            return {"job_id": job_id, "status": state or "PENDING", "result": None, "error": None}

    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail={"error": "STATUS_ERROR", "message": str(exc)})


@app.get("/qc/job/{job_id}/audit")
async def get_job_audit(job_id: str, _auth: None = Security(_require_api_key)):
    """
    Python-side technical audit for one processing job.

    This intentionally returns metadata, timings, hashes, and failure context,
    not borrower/property text. It is the support bridge from Java's QC result
    to Python's internal processing history.
    """
    audit = processing_lifecycle.get_job_audit(job_id)
    if audit is None:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND", "job_id": job_id})
    return audit


@app.get("/qc/jobs")
async def find_processing_jobs(
    _auth: None = Security(_require_api_key),
    correlation_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    batch_file_id: Optional[str] = None,
    qc_result_id: Optional[str] = None,
    source_document_hash: Optional[str] = None,
    limit: int = 50,
):
    """Find Python processing jobs from Java correlation context."""
    if not any([correlation_id, batch_id, batch_file_id, qc_result_id, source_document_hash]):
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_FILTER", "message": "Provide at least one correlation/job filter."},
        )
    jobs = processing_lifecycle.find_jobs(
        correlation_id=correlation_id,
        batch_id=batch_id,
        batch_file_id=batch_file_id,
        qc_result_id=qc_result_id,
        source_document_hash=source_document_hash,
        limit=limit,
    )
    return {"status": "ok", "count": len(jobs), "jobs": jobs}


@app.get("/qc/progress/{progress_token}")
async def get_qc_progress(progress_token: str, _auth: None = Security(_require_api_key)):
    """Return the current sub-stage for an in-flight /qc/process call.

    The Java QC worker generates a token, sends it as `progress_token` in the
    multipart form, and polls this endpoint while waiting for the response.
    Returns 404 if the token is unknown or has expired.
    """
    from app.services.progress_store import progress_store
    snapshot = progress_store.get(progress_token)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_TOKEN"})
    return snapshot


@app.get("/qc/rules")
async def list_qc_rules(_auth: None = Security(_require_api_key)):
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

        # P3.5 — Also retrain the auto-pass calibration model in the same request.
        try:
            from app.services.auto_pass_calibration import train as train_auto_pass
            auto_pass_result = await run_in_threadpool(train_auto_pass)
            result["auto_pass_calibration"] = auto_pass_result
        except Exception as exc:
            result["auto_pass_calibration"] = {"trained": False, "reason": str(exc)}

        return result

    except Exception as e:
        logger.error("Retraining failed: %s", e, extra={"request_id": request_id}, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "RETRAIN_FAILED", "message": str(e)})


@app.get("/admin/auto-pass-calibration")
async def auto_pass_calibration_status(_auth: None = Security(_require_api_key)):
    """
    P3.5 — Return current auto-pass calibration model status.

    Reports:
      - Whether the model has been trained
      - How many examples are available
      - Model accuracy (cross-validated)
      - Training date and model type

    When the model is not yet trained, the response explains how many more
    reviewer decisions are needed before the first training run.
    """
    try:
        from app.services.auto_pass_calibration import (
            get_model_metadata, MIN_EXAMPLES_TO_TRAIN
        )
        from app.database import get_db
        from app.models.db_models import AutoPassExample

        meta = get_model_metadata()

        with get_db() as db:
            total_examples = db.query(AutoPassExample).count()
            accepted = db.query(AutoPassExample).filter(
                AutoPassExample.reviewer_accepted.is_(True)
            ).count()
            rejected = db.query(AutoPassExample).filter(
                AutoPassExample.reviewer_accepted.is_(False)
            ).count()

        meta["examples_available"] = total_examples
        meta["examples_accepted"] = accepted
        meta["examples_rejected"] = rejected
        meta["examples_until_training"] = max(0, MIN_EXAMPLES_TO_TRAIN - total_examples)
        return meta

    except Exception as exc:
        return {
            "trained": False,
            "message": f"Status check failed: {exc}",
            "examples_available": 0,
            "examples_until_training": MIN_EXAMPLES_TO_TRAIN,
        }


@app.post("/admin/auto-pass-calibration/train")
async def trigger_auto_pass_training(force: bool = False, _auth: None = Security(_require_api_key)):
    """
    P3.5 — Manually trigger auto-pass calibration model training.

    Use ?force=true to train even when fewer than MIN_EXAMPLES_TO_TRAIN examples exist.
    """
    try:
        from app.services.auto_pass_calibration import train as train_auto_pass
        result = await run_in_threadpool(lambda: train_auto_pass(force=force))
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "TRAINING_FAILED", "message": str(exc)})


@app.patch("/admin/rules/{rule_id}")
async def toggle_rule(rule_id: str, is_active: bool, _auth: None = Security(_require_api_key)):
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
        from app.rule_engine.rules_db import invalidate_rule_config_cache
        invalidate_rule_config_cache()
        return {"rule_id": rule_id, "is_active": is_active, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr/appraisal", response_model=OcrResponse)
@_limiter.limit("20/minute")
async def process_appraisal(
    request: Request,
    _auth: None = Security(_require_api_key),
    file: UploadFile = File(...),
    correlation_id: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    batch_file_id: Optional[str] = Form(None),
    qc_result_id: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
):
    """
    Process an appraisal PDF and extract key fields.
    """
    start_time = time.time()
    warnings = []
    request_id = getattr(request.state, "request_id", None)
    processing_job_id: Optional[str] = None

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
            _copy_upload_limited(file, tmp_path, label="appraisal PDF")

            err = validate_upload(tmp_path, request_id)
            if err:
                raise HTTPException(status_code=400, detail={"error": "INVALID_FILE", "message": err})

            file_hash = sha256_file(tmp_path)
            effective_idempotency_key = idempotency_key or processing_lifecycle.make_idempotency_key(
                batch_file_id=batch_file_id,
                source_document_hash=file_hash,
                model_provider="simple-ocr",
                model_name=None,
                vision_model=None,
            )
            processing_job_id, job_status, reused = processing_lifecycle.create_or_get_job(
                idempotency_key=effective_idempotency_key,
                source_document_hash=file_hash,
                original_filename=file.filename,
                correlation_id=correlation_id or request.headers.get("x-correlation-id"),
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                model_provider="simple-ocr",
                model_name=None,
                vision_model=None,
                traceparent=request.headers.get("traceparent"),
                tracestate=request.headers.get("tracestate"),
            )
            processing_job_id = _require_durable_job(processing_job_id)
            if reused and job_status == "completed":
                existing = processing_lifecycle.get_job_status(processing_job_id)
                if existing and existing.get("result_json"):
                    cached_payload = json.loads(existing["result_json"])
                    return OcrResponse(**cached_payload)
            if reused and job_status == "in_progress":
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id},
                )
            if not processing_lifecycle.try_claim_job(processing_job_id, stage="simple_ocr_start"):
                raise HTTPException(
                    status_code=409,
                    detail={"error": "JOB_ALREADY_RUNNING", "job_id": processing_job_id},
                )

            logger.info("Starting simple OCR", extra={"uploaded_filename": file.filename, "request_id": request_id})

            def canonical_simple_extract(path: str):
                pipeline = OCRPipeline(use_tesseract=True, force_image_ocr=False, use_preprocessing=True)
                result = pipeline.extract_all_pages(path)
                text = pipeline.get_full_text(result.page_index)
                from app.services.phase2_extraction import phase2_engine
                subject, meta = phase2_engine.extract_subject(
                    text,
                    result.page_index,
                    page_images=result.page_images,
                    word_index=result.word_index,
                )
                confidences = [
                    m.effective_confidence for m in meta.values()
                    if getattr(m, "value", None) not in (None, "")
                ]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
                fields = {
                    "borrowerName": subject.borrower_name,
                    "coBorrowerName": subject.co_borrower_name,
                    "propertyAddress": subject.property_address,
                    "city": subject.city,
                    "state": subject.state,
                    "zipCode": subject.zip_code,
                    "lenderName": subject.lender_name,
                }
                checkboxes = {
                    "isInFloodZone": False,
                    "isForSale": bool(subject.offered_for_sale_12mo),
                    "hasPoolOrSpa": False,
                    "isCondoOrPUD": bool(subject.is_pud_checked),
                    "isPud": bool(subject.is_pud_checked),
                    "isManufacturedHome": False,
                    "didAnalyzeContract": False,
                }
                return result, text, fields, avg_conf, checkboxes

            with processing_lifecycle.processing_context(
                processing_job_id,
                correlation_id or request.headers.get("x-correlation-id"),
                request.headers.get("traceparent"),
            ):
                # Run CPU-bound extraction in threadpool
                with processing_lifecycle.stage("simple_ocr_extract"):
                    ocr_result, raw_text, extracted, confidence, checkboxes = await run_in_threadpool(
                        canonical_simple_extract,
                        tmp_path,
                    )
            
                if not raw_text or len(raw_text.strip()) < 50:
                    msg = "Low text content extracted from PDF"
                    warnings.append(msg)
                    logger.warning(msg, extra={"request_id": request_id})
                form_type = detect_form_type(raw_text)

                document_id = None
                if ocr_result.page_details:
                    with processing_lifecycle.stage("simple_ocr_persist"):
                        from app.services.cache_service import save_extracted_fields, save_ocr_pages

                        document_id = save_ocr_pages(
                            file_hash=file_hash,
                            filename=file.filename,
                            pages=ocr_result.page_details,
                        )
                        if not document_id:
                            raise RuntimeError("OCR cache persistence failed; durable document record is required")
                        page_confidences = [page.confidence for page in ocr_result.page_details]
                        save_extracted_fields(
                            document_id,
                            extracted,
                            page_confidences,
                            processing_job_id=processing_job_id,
                        )
            
            processing_time_ms = int((time.time() - start_time) * 1000)

            response = OcrResponse(
                success=True,
                processingTimeMs=processing_time_ms,
                confidenceScore=confidence,
                processingJobId=processing_job_id,
                documentId=document_id,
                fileHash=file_hash,
                formType=form_type,
                extractedFields=ExtractedFields(**extracted),
                checkboxes=CheckboxFields(**checkboxes),
                rawText=raw_text[:5000] if raw_text else None,  # Limit raw text
                warnings=warnings
            )
            processing_lifecycle.complete_job(
                processing_job_id,
                document_id=document_id,
                result_payload=response.model_dump(),
            )
            return response

    except HTTPException as exc:
        _fail_job_for_http_exception(processing_job_id, exc)
        raise
    except fitz.FileDataError:
        processing_lifecycle.fail_job(processing_job_id, "PDF file is corrupted or encrypted", "input_validation")
        logger.error("Corrupted PDF", extra={"request_id": request_id})
        raise HTTPException(
            status_code=400,
            detail={"error": "CORRUPTED_PDF", "message": "PDF file is corrupted or encrypted"}
        )
    except Exception as e:
        processing_lifecycle.fail_job(processing_job_id, str(e))
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


def extract_text_from_supporting_pdf(pdf_path: str, document_label: str, filename: str) -> str:
    """
    Extract text for engagement/contract PDFs with explicit logging.

    These files are used as comparison inputs, so we log whether OCR/native
    extraction produced enough text to make downstream rule failures trustworthy.
    """
    pipeline = OCRPipeline(
        use_tesseract=True,
        force_image_ocr=False,
        use_preprocessing=True,
    )
    try:
        result = pipeline.extract_all_pages(pdf_path)
        text = pipeline.get_full_text(result.page_index)
        total_chars = len(text.strip())
        logger.info(
            "%s extraction completed",
            document_label,
            extra={
                "supporting_filename": filename,
                "supporting_pages": result.total_pages,
                "supporting_characters": total_chars,
                "supporting_methods": sorted({page.method.value for page in result.page_details}),
            },
        )
        if total_chars < 50:
            logger.warning(
                "%s extraction produced very little text; downstream comparisons may be unreliable",
                document_label,
                extra={
                    "supporting_filename": filename,
                    "supporting_pages": result.total_pages,
                    "supporting_characters": total_chars,
                },
            )
        return text
    except Exception as e:
        logger.error("%s extraction failed: %s", document_label, e)
        return extract_text_from_pdf(pdf_path)


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
    document_id: str = PydanticField(max_length=64)
    processing_job_id: Optional[str] = PydanticField(default=None, max_length=64)
    correlation_id: Optional[str] = PydanticField(default=None, max_length=128)
    rule_id: Optional[str] = PydanticField(default=None, max_length=20)
    field_name: Optional[str] = PydanticField(default=None, max_length=100)
    original_value: Optional[str] = PydanticField(default=None, max_length=4000)
    corrected_value: Optional[str] = PydanticField(default=None, max_length=4000)
    feedback_type: str = PydanticField(default="CORRECTION", max_length=50)
    operator_comment: Optional[str] = PydanticField(default=None, max_length=2000)
    reviewer_role: Optional[str] = PydanticField(default=None, max_length=50)
    decision_latency_ms: Optional[int] = None
    acknowledged: Optional[bool] = None
    source_page: Optional[int] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None
    confidence_score: Optional[float] = None


@app.post("/qc/feedback")
async def submit_feedback(payload: FeedbackRequest, request: Request, _auth: None = Security(_require_api_key)):
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
        job_uuid = _uuid.UUID(payload.processing_job_id) if payload.processing_job_id else None

        with get_db() as db:
            event = FeedbackEvent(
                document_id=doc_uuid,
                processing_job_id=job_uuid,
                correlation_id=payload.correlation_id,
                rule_id=payload.rule_id,
                field_name=payload.field_name,
                original_value=payload.original_value,
                corrected_value=payload.corrected_value,
                operator_comment=payload.operator_comment,
                reviewer_role=payload.reviewer_role,
                decision_latency_ms=payload.decision_latency_ms,
                acknowledged=payload.acknowledged,
                source_page=payload.source_page,
                bbox_x=payload.bbox_x,
                bbox_y=payload.bbox_y,
                bbox_w=payload.bbox_w,
                bbox_h=payload.bbox_h,
                confidence_score=payload.confidence_score,
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
            elif (
                payload.feedback_type in {"REVIEW_DECISION", "CORRECTION", "EXTRACTION_ERROR", "RULE_ERROR"}
                and payload.field_name
                and payload.corrected_value
            ):
                training_payload = {
                    "document_id": payload.document_id,
                    "processing_job_id": payload.processing_job_id,
                    "correlation_id": payload.correlation_id,
                    "rule_id": payload.rule_id,
                    "field_name": payload.field_name,
                    "original_value": payload.original_value,
                    "confidence_score": payload.confidence_score,
                    "source_page": payload.source_page,
                    "bbox": {
                        "x": payload.bbox_x,
                        "y": payload.bbox_y,
                        "w": payload.bbox_w,
                        "h": payload.bbox_h,
                    },
                    "reviewer_role": payload.reviewer_role,
                    "decision_latency_ms": payload.decision_latency_ms,
                }
                db.add(TrainingExample(
                    feature_type="field_review_decision",
                    input_text=json.dumps(training_payload, default=str),
                    label=payload.corrected_value[:100],
                    source_feedback_id=event.id,
                ))

        try:
            from app.services.confidence_calibration import record_feedback_outcome
            record_feedback_outcome(
                document_id=payload.document_id,
                field_name=payload.field_name,
                corrected_value=payload.corrected_value,
                feedback_type=payload.feedback_type,
            )
        except Exception:
            pass

        # P3.5 — Record rule-level outcome for auto-pass calibration.
        # REVIEW_DECISION with corrected_status PASS/FAIL is the primary signal.
        # Only record when we have a rule_id and a clear decision.
        try:
            if payload.rule_id and payload.feedback_type:
                ft = payload.feedback_type.strip().upper()
                cv = (payload.corrected_value or "").strip().upper()
                if ft == "REVIEW_DECISION" and cv in {"PASS", "FAIL"}:
                    reviewer_accepted = cv == "PASS"
                elif ft in {"PASS", "CORRECT", "ACCEPTED"}:
                    reviewer_accepted = True
                elif ft in {"FAIL", "RULE_ERROR", "EXTRACTION_ERROR"}:
                    reviewer_accepted = False
                else:
                    reviewer_accepted = None

                if reviewer_accepted is not None:
                    from app.services.auto_pass_calibration import record_example
                    rule_family = (payload.rule_id or "").split("-", 1)[0].upper()
                    record_example(
                        rule_id=payload.rule_id,
                        rule_family=rule_family,
                        extraction_method=None,
                        confidence=payload.confidence_score,
                        source_page=payload.source_page,
                        bbox_x=payload.bbox_x,
                        has_compared_values=False,
                        has_extracted_value=bool(payload.original_value),
                        loan_type=None,
                        details=None,
                        reviewer_accepted=reviewer_accepted,
                        document_id=str(payload.document_id),
                        reviewer_comment=payload.operator_comment,
                    )
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
    if not _require_ws_api_key(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    request_id = str(__import__("uuid").uuid4())
    processing_job_id: Optional[str] = None

    try:
        import tempfile

        msg = await websocket.receive_json()
        appraisal_b64  = msg.get("appraisal_b64")
        engagement_b64 = msg.get("engagement_b64")
        contract_b64   = msg.get("contract_b64")
        correlation_id = msg.get("correlation_id")
        batch_id = msg.get("batch_id")
        batch_file_id = msg.get("batch_file_id")
        qc_result_id = msg.get("qc_result_id")
        idempotency_key = msg.get("idempotency_key")
        traceparent = msg.get("traceparent")
        tracestate = msg.get("tracestate")

        if not appraisal_b64:
            await websocket.send_json({"event": "error", "message": "appraisal_b64 required"})
            return

        await websocket.send_json({"event": "progress", "stage": "upload",
                                   "message": "Files received. Starting validation..."})

        with tempfile.TemporaryDirectory() as tmp:
            # Write files
            pdf_path = f"{tmp}/appraisal.pdf"
            with open(pdf_path, "wb") as f:
                f.write(_decode_b64_document(appraisal_b64, label="appraisal_b64"))

            err = validate_upload(pdf_path, request_id)
            if err:
                await websocket.send_json({"event": "error", "message": err})
                return

            file_hash = sha256_file(pdf_path)
            effective_idempotency_key = idempotency_key or processing_lifecycle.make_idempotency_key(
                batch_file_id=batch_file_id,
                source_document_hash=file_hash,
                model_provider="ollama",
                model_name=None,
                vision_model=None,
            )
            processing_job_id, job_status, reused = processing_lifecycle.create_or_get_job(
                idempotency_key=effective_idempotency_key,
                source_document_hash=file_hash,
                original_filename="websocket-upload.pdf",
                correlation_id=correlation_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                model_provider="ollama",
                model_name=None,
                vision_model=None,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            try:
                processing_job_id = _require_durable_job(processing_job_id)
            except HTTPException as exc:
                await websocket.send_json({"event": "error", "message": exc.detail})
                return
            if reused and job_status == "completed":
                existing = processing_lifecycle.get_job_status(processing_job_id)
                if existing and existing.get("result_json"):
                    payload = json.loads(existing["result_json"])
                    payload["file_hash"] = file_hash
                    payload["processing_job_id"] = processing_job_id
                    await websocket.send_json({"event": "complete", "data": payload})
                    return
            if reused and job_status == "in_progress":
                await websocket.send_json({
                    "event": "error",
                    "message": "Job is already running",
                    "job_id": processing_job_id,
                })
                return
            if not processing_lifecycle.try_claim_job(processing_job_id, stage="websocket_start"):
                await websocket.send_json({
                    "event": "error",
                    "message": "Job is already running",
                    "job_id": processing_job_id,
                })
                return

            await websocket.send_json({"event": "progress", "stage": "ocr",
                                       "message": "Extracting text from PDF...", "hash": file_hash,
                                       "processing_job_id": processing_job_id})

            with processing_lifecycle.processing_context(processing_job_id, correlation_id, traceparent):
                engagement_text = None
                if engagement_b64:
                    with processing_lifecycle.stage("supporting_ocr_engagement"):
                        eng_path = f"{tmp}/engagement.pdf"
                        with open(eng_path, "wb") as f:
                            f.write(_decode_b64_document(
                                engagement_b64,
                                label="engagement_b64",
                                max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                            ))
                        err = validate_upload(eng_path, request_id)
                        if err:
                            await websocket.send_json({"event": "error", "message": err})
                            processing_lifecycle.fail_job(processing_job_id, err, "supporting_ocr_engagement")
                            return
                        engagement_text = await run_in_threadpool(extract_text_from_pdf, eng_path)

                contract_text = None
                if contract_b64:
                    with processing_lifecycle.stage("supporting_ocr_contract"):
                        con_path = f"{tmp}/contract.pdf"
                        with open(con_path, "wb") as f:
                            f.write(_decode_b64_document(
                                contract_b64,
                                label="contract_b64",
                                max_bytes=_SUPPORTING_FILE_SIZE_BYTES,
                            ))
                        err = validate_upload(con_path, request_id)
                        if err:
                            await websocket.send_json({"event": "error", "message": err})
                            processing_lifecycle.fail_job(processing_job_id, err, "supporting_ocr_contract")
                            return
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
                processing_job_id=processing_job_id,
                correlation_id=correlation_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                idempotency_key=effective_idempotency_key,
                traceparent=traceparent,
                tracestate=tracestate,
            )

            payload = results.model_dump()
            payload["file_hash"] = file_hash
            payload["processing_job_id"] = processing_job_id
            await websocket.send_json({"event": "complete", "data": payload})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected", extra={"request_id": request_id})
    except Exception as e:
        processing_lifecycle.fail_job(processing_job_id, str(e))
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

# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS ENDPOINTS  — operator-safe, no ML/OCR jargon exposed
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta
from typing import Optional
import statistics


def _job_result_payload(job) -> dict:
    try:
        return json.loads(job.result_json or "{}")
    except Exception:
        return {}


def _job_result_bool(job, key: str) -> bool:
    return bool(_job_result_payload(job).get(key))


def _job_result_int(job, key: str, default: int = 0) -> int:
    try:
        return int(_job_result_payload(job).get(key, default) or default)
    except Exception:
        return default

@app.get("/analytics/summary", tags=["analytics"])
async def analytics_summary(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Overall processing health for the last N days (default 30)."""
    from sqlalchemy import func
    from app.database import get_db
    from app.models.db_models import ProcessingJob, ExtractedFieldRecord
    cutoff = datetime.utcnow() - timedelta(days=days)

    with get_db() as db:
        jobs = db.query(ProcessingJob).filter(ProcessingJob.started_at >= cutoff).all()
        field_stats = db.query(
            func.avg(ExtractedFieldRecord.confidence_score),
            func.min(ExtractedFieldRecord.confidence_score),
        ).filter(ExtractedFieldRecord.created_at >= cutoff).first()

    durations = [
        (j.completed_at - j.started_at).total_seconds() * 1000
        for j in jobs if j.completed_at and j.started_at
    ]
    cache_hits = sum(1 for j in jobs if _job_result_bool(j, "cache_hit"))
    avg_conf = float(field_stats[0]) if field_stats and field_stats[0] is not None else None
    min_conf = float(field_stats[1]) if field_stats and field_stats[1] is not None else None
    return {
        "status": "ok",
        "period_days": days,
        "files_processed": len(jobs),
        "avg_accuracy_pct": round(avg_conf * 100, 1) if avg_conf is not None and avg_conf <= 1 else round(avg_conf, 1) if avg_conf is not None else None,
        "avg_processing_seconds": round(statistics.mean(durations) / 1000, 1) if durations else None,
        "cache_hit_rate_pct": round(cache_hits / len(jobs) * 100, 1) if jobs else None,
        "min_accuracy_pct": round(min_conf * 100, 1) if min_conf is not None and min_conf <= 1 else round(min_conf, 1) if min_conf is not None else None,
        "max_processing_seconds": round(max(durations) / 1000, 1) if durations else None,
    }


@app.get("/analytics/rules", tags=["analytics"])
async def analytics_rules(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Per-rule pass/fail counts to show which rules are most commonly triggered."""
    from sqlalchemy import func
    from app.database import get_db
    from app.models.db_models import RuleResultRecord
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_db() as db:
        grouped = db.query(
            RuleResultRecord.rule_id,
            RuleResultRecord.rule_name,
            RuleResultRecord.status,
            func.count(RuleResultRecord.id),
        ).filter(RuleResultRecord.created_at >= cutoff).group_by(
            RuleResultRecord.rule_id, RuleResultRecord.rule_name, RuleResultRecord.status
        ).all()
    rule_counts: dict[str, dict] = {}
    for rid, name, status, count in grouped:
        row = rule_counts.setdefault(rid or "unknown", {
            "rule_id": rid or "unknown", "rule_name": name or "", "pass": 0, "fail": 0, "review": 0, "not_executed": 0, "not_applicable": 0
        })
        stat = (status or "unknown").lower()
        if stat == "pass": row["pass"] += count
        elif stat == "fail": row["fail"] += count
        elif stat in {"review", "verify", "extraction_failed", "ocr_low_confidence", "system_error", "source_missing", "cross_doc_mismatch"}:
            row["review"] += count
            row[stat] = row.get(stat, 0) + count
        elif stat == "not_executed":
            row["not_executed"] += count
        elif stat == "not_applicable":
            row["not_applicable"] += count
        else:
            row[stat] = row.get(stat, 0) + count
    rows = sorted(rule_counts.values(), key=lambda x: x["fail"] + x["review"], reverse=True)
    return {"status": "ok", "period_days": days, "rules": rows}


@app.get("/analytics/model-health", tags=["analytics"])
async def model_health(
    days: int = 30,
    _auth: None = Security(_require_api_key)
):
    """Model performance in plain language: how confident the system is, trend over time."""
    from app.database import get_db
    from app.models.db_models import ExtractedFieldRecord, ProcessingJob
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_db() as db:
        confs = [
            float(v[0]) * 100 if v[0] is not None and float(v[0]) <= 1 else float(v[0])
            for v in db.query(ExtractedFieldRecord.confidence_score)
            .filter(ExtractedFieldRecord.created_at >= cutoff, ExtractedFieldRecord.confidence_score != None)
            .order_by(ExtractedFieldRecord.created_at.asc(), ExtractedFieldRecord.id.asc())
            .all()
        ]
        files_analysed = db.query(ProcessingJob).filter(ProcessingJob.started_at >= cutoff).count()
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
        "files_analysed": files_analysed,
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
    from app.database import get_db
    from app.models.db_models import ProcessingJob, RuleResultRecord
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_db() as db:
        jobs = db.query(ProcessingJob).filter(ProcessingJob.started_at >= cutoff).all()
        issues_found = db.query(RuleResultRecord).filter(
            RuleResultRecord.created_at >= cutoff,
            RuleResultRecord.status == "fail",
        ).count()
        needs_review = db.query(RuleResultRecord).filter(
            RuleResultRecord.created_at >= cutoff,
            RuleResultRecord.status.in_((
                "review",
                "verify",
                "extraction_failed",
                "ocr_low_confidence",
                "system_error",
                "source_missing",
                "cross_doc_mismatch",
            )),
        ).count()
    auto_passed = sum(1 for j in jobs if _job_result_int(j, "failed") == 0 and _job_result_int(j, "verify") == 0)
    cache_hits = sum(1 for j in jobs if _job_result_bool(j, "cache_hit"))

    return {
        "status": "ok",
        "period_days": days,
        "files_checked": len(jobs),
        "issues_found": issues_found,
        "items_need_your_review": needs_review,
        "files_passed_automatically": auto_passed,
        "time_saved_by_cache_minutes": round(cache_hits * 0.25, 1),
        "summary": f"{len(jobs)} files checked, {issues_found} issues found, {needs_review} need your review."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
