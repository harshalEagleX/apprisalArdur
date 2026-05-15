"""
Apprisal OCR Service — FastAPI Entry Point

Days 1-6 endpoints:
  GET  /health              — service health + schema info
  POST /schema/reload       — reload field_schema.yaml without restart
  GET  /schema/fields       — list schema fields (optional ?section=subject)
  POST /qc/process          — extract from a document (path or upload)
  POST /corrections         — submit a reviewer correction (Day 5)
  GET  /corrections/{doc}   — get all corrections for a document
  GET  /corrections/stats   — correction count by reason and field
  GET  /baseline/latest     — latest baseline run summary
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from app.config import MODEL_VERSION
from app.core.schema import schema_loader
from app.database import verify_connection
from app.services.correction_service import (
    CorrectionRequest,
    CorrectionResponse,
    get_correction_stats,
    get_corrections_for_document,
    save_correction,
)

app = FastAPI(
    title="Apprisal OCR Service",
    description="Adaptive document extraction platform — Week 1",
    version="0.2.0",
)


@app.on_event("startup")
async def startup():
    log = logging.getLogger(__name__)
    log.info("Schema: version=%s fields=%d", schema_loader.schema_version, len(schema_loader.all_fields()))
    if verify_connection():
        log.info("Database: connected")
    else:
        log.warning("Database: NOT connected — check DATABASE_URL in .env")


# ---------------------------------------------------------------------------
# Health / schema endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "schema_version": schema_loader.schema_version,
        "field_count": len(schema_loader.all_fields()),
        "model_version": MODEL_VERSION,
        "database": "connected" if verify_connection() else "disconnected",
    }


@app.post("/schema/reload")
async def reload_schema():
    schema_loader.reload()
    return {"reloaded": True, "field_count": len(schema_loader.all_fields())}


@app.get("/schema/fields")
async def list_fields(section: Optional[str] = Query(None)):
    fields = schema_loader.fields_for_section(section) if section else schema_loader.all_fields()
    return [
        {
            "canonical_name": f.canonical_name,
            "data_type": f.data_type,
            "required": f.required,
            "sections": f.sections,
            "source_authority": f.source_authority,
            "synonym_count": len(f.synonyms),
            "required_for_review": f.required_for_review,
        }
        for f in fields
    ]


# ---------------------------------------------------------------------------
# Document processing endpoint
# ---------------------------------------------------------------------------

class ProcessRequest(BaseModel):
    document_path: str
    document_type: str  # appraisal_report | engagement_letter | sales_contract
    amc_id: Optional[str] = None
    store_results: bool = True


@app.post("/qc/process")
async def process_document(req: ProcessRequest):
    """
    Extract fields from a document and optionally store results in the DB.
    Returns the extraction result set as JSON.
    """
    from app.ocr.document import load_pdf
    from app.extraction.tier3_pattern import Tier3PatternExtractor
    from app.database import get_db
    from app.models.db_models import ExtractionResultRow

    doc_path = Path(req.document_path)
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {req.document_path}")

    valid_types = {"appraisal_report", "engagement_letter", "sales_contract", "qc_checklist"}
    if req.document_type not in valid_types:
        raise HTTPException(status_code=422, detail=f"document_type must be one of {sorted(valid_types)}")

    try:
        loaded = load_pdf(doc_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to load PDF: {exc}")

    extractor = Tier3PatternExtractor()
    result_set = extractor.extract(loaded, req.document_type)

    # Persist if requested
    if req.store_results:
        try:
            with get_db() as session:
                for canonical, result in result_set:
                    row = ExtractionResultRow(
                        document_id=str(doc_path.name),
                        amc_id=req.amc_id,
                        document_type=req.document_type,
                        document_path=str(doc_path),
                        total_pages=result_set.total_pages,
                        field_name=canonical,
                        field_value=result.value,
                        raw_source_text=result.raw_source_text,
                        extraction_method=result.extraction_method,
                        confidence_score=result.effective_confidence,
                        source_page=result.source_page,
                        char_start=result.char_start,
                        normalization_steps=json.dumps(result.normalization_applied or []),
                        sanity_check_failed=result.sanity_check_failed,
                        hallucination_flag=result.hallucination_flag,
                        model_version=MODEL_VERSION,
                    )
                    session.add(row)
        except Exception as exc:
            logging.getLogger(__name__).error("DB persist failed: %s", exc)

    summary = result_set.summary()
    found = [
        {
            "field": r.canonical_name,
            "value": r.value,
            "confidence": r.effective_confidence,
            "method": r.extraction_method,
            "page": r.source_page,
        }
        for _, r in result_set if r.found
    ]

    return {
        "summary": summary,
        "found_fields": found,
        "missing_required": result_set.required_missing(schema_loader),
    }


# ---------------------------------------------------------------------------
# Correction endpoints (Day 5)
# ---------------------------------------------------------------------------

@app.post("/corrections", response_model=CorrectionResponse)
async def submit_correction(req: CorrectionRequest):
    """
    Record a human reviewer correction.
    Called by the Java backend when a reviewer changes an extracted value.
    Stores the correction with full context for ML training loop.
    """
    try:
        return save_correction(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/corrections/{document_id:path}", response_model=list[CorrectionResponse])
async def list_corrections(document_id: str):
    """Return all corrections recorded for a document."""
    return get_corrections_for_document(document_id)


@app.get("/corrections")
async def correction_stats():
    """Return correction counts by reason and field — for the ops dashboard."""
    return get_correction_stats()


# ---------------------------------------------------------------------------
# Baseline endpoints (Day 4)
# ---------------------------------------------------------------------------

@app.get("/baseline/latest")
async def latest_baseline():
    """Return the most recent baseline run summary."""
    from app.database import get_db
    from app.models.db_models import BaselineRunRow

    with get_db() as session:
        row = session.query(BaselineRunRow).order_by(
            BaselineRunRow.run_at.desc()
        ).first()
        if not row:
            return {"message": "No baseline runs yet. POST /baseline/run to start."}
        return {
            "run_label": row.run_label,
            "run_at": row.run_at.isoformat(),
            "schema_version": row.schema_version,
            "model_version": row.model_version,
            "total_documents": row.total_documents,
            "fields_correct": row.fields_correct,
            "total_fields_tested": row.total_fields_tested,
            "field_accuracy_rate": row.field_accuracy_rate,
            "document_accuracy_rate": row.document_accuracy_rate,
            "amc_accuracy": json.loads(row.amc_accuracy_json or "{}"),
        }


@app.post("/baseline/run")
async def trigger_baseline(label: str = "manual"):
    """Run a full baseline measurement and store the results."""
    from app.services.baseline_service import run_baseline
    try:
        report = run_baseline(label=label)
        return {
            "run_label": report.run_label,
            "documents": len(report.document_results),
            "field_accuracy": round(report.overall_field_accuracy, 3),
            "document_accuracy": round(report.overall_document_accuracy, 3),
            "amc_accuracy": report.amc_accuracy(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
