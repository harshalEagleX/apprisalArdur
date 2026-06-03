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

# Allow the Next.js dev frontend to call the QC endpoints directly (demo).
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    log = logging.getLogger(__name__)
    log.info("Schema: version=%s fields=%d", schema_loader.schema_version, len(schema_loader.all_fields()))
    if verify_connection():
        log.info("Database: connected")
        # Day 23: seed routing config from schema on startup if not already done
        try:
            from app.services.routing_config import seed_routing_config
            seeded = seed_routing_config()
            if seeded:
                log.info("Routing config seeded: %d fields", seeded)
        except Exception as exc:
            log.warning("Routing config seed failed: %s", exc)
    else:
        log.warning("Database: NOT connected — check DATABASE_URL in .env")


# ---------------------------------------------------------------------------
# Health / schema endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    from app.extraction.llm_resilience import check_ollama_health
    ollama_status = check_ollama_health()
    return {
        "status": "ok",
        "schema_version": schema_loader.schema_version,
        "field_count": len(schema_loader.all_fields()),
        "model_version": MODEL_VERSION,
        "database": "connected" if verify_connection() else "disconnected",
        "ollama": ollama_status,
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
    Run the full pipeline on a document — classify, extract (strong layered
    orchestrator), validate, route — and persist every stage to the DB.
    Returns a summary of the document journey.

    document_type may be passed explicitly or left to the classifier; an
    explicit, recognised type is honoured, otherwise classification decides.
    """
    from app.services.pipeline_runner import process_and_persist

    doc_path = Path(req.document_path)
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {req.document_path}")

    valid_types = {"appraisal_report", "engagement_letter", "sales_contract", "qc_checklist"}
    explicit_type = req.document_type if req.document_type in valid_types else None

    try:
        return process_and_persist(
            doc_path,
            document_type=explicit_type,
            amc_id=req.amc_id,
            store=req.store_results,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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


# ---------------------------------------------------------------------------
# Week 4 — Semantic validation + routing config + AMC profile endpoints
# ---------------------------------------------------------------------------

@app.post("/validate/{document_id}")
async def validate_document(document_id: str, doc_type: str = "appraisal_report"):
    """Day 21: Run semantic validation on an extracted document."""
    from app.database import get_db
    from app.models.db_models import ExtractionResultRow
    from app.core.result import ExtractionResult, ExtractionResultSet, ExtractionMethod
    from app.services.semantic_validator import validate

    # Reconstruct ExtractionResultSet from DB results
    rs = ExtractionResultSet(document_path="", document_type=doc_type)
    try:
        with get_db() as session:
            rows = session.query(ExtractionResultRow).filter_by(
                document_id=document_id, document_type=doc_type
            ).order_by(ExtractionResultRow.extracted_at.desc()).all()

            seen = set()
            for row in rows:
                if row.field_name in seen:
                    continue
                seen.add(row.field_name)
                rs.add(ExtractionResult(
                    canonical_name=row.field_name,
                    document_type=doc_type,
                    value=row.field_value,
                    extraction_method=row.extraction_method or ExtractionMethod.NOT_FOUND,
                    confidence=row.confidence_score or 0.0,
                    source_page=row.source_page or 0,
                ))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB read failed: {exc}")

    results = validate(rs, document_id)
    return {
        "document_id": document_id,
        "rules_run": len(results),
        "failures": [{"rule": r.rule_id, "explanation": r.explanation} for r in results if r.result == "fail"],
        "warnings": [{"rule": r.rule_id, "explanation": r.explanation} for r in results if r.result == "warning"],
        "passes": sum(1 for r in results if r.result == "pass"),
    }


@app.get("/routing/config")
async def get_routing_config(field_name: Optional[str] = None, amc_id: Optional[str] = None):
    """Day 23: Get confidence thresholds for a field (from DB)."""
    from app.services.routing_config import get_thresholds
    from app.core.schema import schema_loader
    if field_name:
        return get_thresholds(field_name, amc_id)
    # Return all fields
    return {f.canonical_name: get_thresholds(f.canonical_name, amc_id) for f in schema_loader.all_fields()}


class RoutingUpdateRequest(BaseModel):
    field_name: str
    auto_accept: float
    review: float
    reject: float
    amc_id: Optional[str] = None
    rationale: str = ""


@app.put("/routing/config")
async def update_routing_config(req: RoutingUpdateRequest):
    """Day 23: Update routing threshold — no developer needed, no deployment."""
    from app.services.routing_config import update_threshold
    success = update_threshold(
        field_name=req.field_name,
        auto_accept=req.auto_accept,
        review=req.review,
        reject=req.reject,
        amc_id=req.amc_id,
        rationale=req.rationale,
        updated_by="admin_api",
    )
    return {"updated": success, "field_name": req.field_name, "amc_id": req.amc_id}


@app.get("/amc/profiles")
async def list_amc_profiles():
    """Day 24: List all AMC profiles — for the operations dashboard."""
    from app.services.amc_profile_service import list_profiles
    return list_profiles()


# ---------------------------------------------------------------------------
# QC rule engine — transaction-level QC + reviewer report
# ---------------------------------------------------------------------------

class TransactionQCRequest(BaseModel):
    folder: str                     # transaction folder with appraisal/engagement/contract
    store_results: bool = True


@app.post("/qc/transaction")
async def qc_transaction(req: TransactionQCRequest):
    """Run the full QC rule engine on a transaction folder (extract all docs,
    run rules, persist). Returns the reviewer report."""
    from app.qc.transaction import run_transaction_qc
    from app.qc.report import transaction_report

    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {req.folder}")
    rep = run_transaction_qc(folder, persist=req.store_results)
    if req.store_results:
        return transaction_report(rep.transaction_id)
    # not persisted → render in-memory
    return {
        "transaction_id": rep.transaction_id,
        "overall": rep.overall.value,
        "counts": rep.counts(),
        "findings": [
            {"rule_id": r.rule_id, "status": r.status.value, "section": r.section,
             "message": r.message, "fields": r.fields_involved}
            for r in rep.results if r.status.value in ("FAIL", "VERIFY", "HOLD")
        ],
    }


@app.get("/qc/report/{transaction_id:path}")
async def qc_report(transaction_id: str):
    """Return the persisted reviewer QC report for a transaction."""
    from app.qc.report import transaction_report
    report = transaction_report(transaction_id)
    if report["rule_count"] == 0:
        raise HTTPException(status_code=404, detail="No QC results for this transaction.")
    return report


@app.get("/qc/transactions")
async def qc_transactions():
    """List every transaction that has QC results, with its overall outcome —
    for the reviewer dashboard transaction picker."""
    from app.database import get_db
    from app.models.db_models import ValidationResultRow
    from app.qc.report import transaction_report

    with get_db() as session:
        rows = (session.query(ValidationResultRow.transaction_id)
                .filter(ValidationResultRow.transaction_id.isnot(None))
                .distinct().all())
    out = []
    for (tid,) in rows:
        try:
            rep = transaction_report(tid)
        except Exception:
            continue
        if rep["rule_count"]:
            out.append({
                "transaction_id": tid,
                "overall": rep["overall"],
                "exception_count": rep["exception_count"],
                "rule_count": rep["rule_count"],
                "counts": rep["counts"],
            })
    out.sort(key=lambda r: r["transaction_id"])
    return out
