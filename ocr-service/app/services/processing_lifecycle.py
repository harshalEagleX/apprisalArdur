"""
Durable Python-side processing lifecycle.

Java owns business lifecycle. This module records Python's technical journey:
job creation, stage timings, retry/failure state, idempotency, and LLM metadata.
All functions are best-effort; lifecycle tracking must never break OCR itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

_CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar("processing_job_id", default=None)
_CURRENT_CORRELATION_ID: ContextVar[Optional[str]] = ContextVar("processing_correlation_id", default=None)
_CURRENT_STAGE: ContextVar[Optional[str]] = ContextVar("processing_stage", default=None)
_CURRENT_TRACEPARENT: ContextVar[Optional[str]] = ContextVar("processing_traceparent", default=None)


def current_job_id() -> Optional[str]:
    return _CURRENT_JOB_ID.get()


def current_correlation_id() -> Optional[str]:
    return _CURRENT_CORRELATION_ID.get()


def current_stage() -> Optional[str]:
    return _CURRENT_STAGE.get()


def current_traceparent() -> Optional[str]:
    return _CURRENT_TRACEPARENT.get()


@contextmanager
def processing_context(job_id: Optional[str], correlation_id: Optional[str] = None, traceparent: Optional[str] = None):
    job_token = _CURRENT_JOB_ID.set(str(job_id) if job_id else None)
    corr_token = _CURRENT_CORRELATION_ID.set(correlation_id)
    trace_token = _CURRENT_TRACEPARENT.set(traceparent)
    try:
        yield
    finally:
        _CURRENT_JOB_ID.reset(job_token)
        _CURRENT_CORRELATION_ID.reset(corr_token)
        _CURRENT_TRACEPARENT.reset(trace_token)


def make_idempotency_key(
    *,
    batch_file_id: Optional[str],
    source_document_hash: Optional[str],
    model_provider: str,
    model_name: Optional[str],
    vision_model: Optional[str],
    rule_set_version: str = "1.0",
) -> Optional[str]:
    if not source_document_hash:
        return None
    raw = "|".join([
        str(batch_file_id or "no-batch-file"),
        source_document_hash,
        model_provider or "ollama",
        model_name or "",
        vision_model or "",
        rule_set_version or "1.0",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_or_get_job(
    *,
    idempotency_key: Optional[str],
    source_document_hash: Optional[str],
    original_filename: Optional[str],
    correlation_id: Optional[str],
    batch_id: Optional[str],
    batch_file_id: Optional[str],
    qc_result_id: Optional[str],
    model_provider: str,
    model_name: Optional[str],
    vision_model: Optional[str],
    traceparent: Optional[str] = None,
    tracestate: Optional[str] = None,
    rule_set_version: str = "1.0",
):
    """Return (job_id, status, reused)."""
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        with get_db() as db:
            job = None
            if idempotency_key:
                job = db.query(ProcessingJob).filter(
                    ProcessingJob.idempotency_key == idempotency_key
                ).first()
            if job:
                _update_job_context(job, correlation_id, batch_id, batch_file_id, qc_result_id, traceparent, tracestate)
                return str(job.id), job.status, True

            job = ProcessingJob(
                id=uuid.uuid4(),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                batch_id=str(batch_id) if batch_id is not None else None,
                batch_file_id=str(batch_file_id) if batch_file_id is not None else None,
                qc_result_id=str(qc_result_id) if qc_result_id is not None else None,
                source_document_hash=source_document_hash,
                original_filename=original_filename,
                model_provider=model_provider,
                model_name=model_name,
                vision_model=vision_model,
                traceparent=traceparent,
                tracestate=tracestate,
                rule_set_version=rule_set_version,
                current_stage="queued",
                status="queued",
            )
            db.add(job)
            try:
                db.flush()
            except IntegrityError:
                # Concurrent duplicate submit: another request won the unique
                # idempotency race. Roll back this transaction and return the
                # durable job instead of surfacing a 500 to Java.
                db.rollback()
                if not idempotency_key:
                    raise
                job = db.query(ProcessingJob).filter(
                    ProcessingJob.idempotency_key == idempotency_key
                ).first()
                if job:
                    _update_job_context(job, correlation_id, batch_id, batch_file_id, qc_result_id, traceparent, tracestate)
                    return str(job.id), job.status, True
                raise
            return str(job.id), job.status, False
    except Exception as exc:
        logger.info("processing job create/get skipped: %s", exc)
        return None, "untracked", False


def get_job_status(job_id: str) -> Optional[dict[str, Any]]:
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        job_uuid = uuid.UUID(str(job_id))
        with get_db() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_uuid).first()
            if not job:
                return None
            return {
                "job_id": str(job.id),
                "status": job.status,
                "stage": job.current_stage,
                "result_json": job.result_json,
                "error": job.failure_reason,
                "retry_count": job.retry_count or 0,
            }
    except Exception as exc:
        logger.debug("processing job status unavailable for %s: %s", job_id, exc)
        return None


def get_job_audit(job_id: str) -> Optional[dict[str, Any]]:
    """Return job, stage, and LLM metadata for support/debug endpoints."""
    try:
        from app.database import get_db
        from app.models.db_models import LLMCallLog, ProcessingJob, ProcessingStage

        job_uuid = uuid.UUID(str(job_id))
        with get_db() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_uuid).first()
            if not job:
                return None
            stages = db.query(ProcessingStage).filter(
                ProcessingStage.job_id == job_uuid
            ).order_by(ProcessingStage.started_at.asc(), ProcessingStage.id.asc()).all()
            llm_calls = db.query(LLMCallLog).filter(
                LLMCallLog.job_id == job_uuid
            ).order_by(LLMCallLog.started_at.asc(), LLMCallLog.id.asc()).all()

            return {
                "job": {
                    "job_id": str(job.id),
                    "idempotency_key": job.idempotency_key,
                    "correlation_id": job.correlation_id,
                    "batch_id": job.batch_id,
                    "batch_file_id": job.batch_file_id,
                    "qc_result_id": job.qc_result_id,
                    "source_document_hash": job.source_document_hash,
                    "original_filename": job.original_filename,
                    "model_provider": job.model_provider,
                    "model_name": job.model_name,
                    "vision_model": job.vision_model,
                    "rule_set_version": job.rule_set_version,
                    "traceparent": job.traceparent,
                    "status": job.status,
                    "stage": job.current_stage,
                    "retry_count": job.retry_count or 0,
                    "document_id": str(job.document_id) if job.document_id else None,
                    "failure_reason": job.failure_reason,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "failed_at": job.failed_at.isoformat() if job.failed_at else None,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                },
                "stages": [
                    {
                        "stage_name": row.stage_name,
                        "status": row.status,
                        "started_at": row.started_at.isoformat() if row.started_at else None,
                        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                        "duration_ms": row.duration_ms,
                        "error_message": row.error_message,
                        "metadata": _safe_json_loads(row.metadata_json),
                    }
                    for row in stages
                ],
                "llm_calls": [
                    {
                        "stage_name": row.stage_name,
                        "task_name": row.task_name,
                        "prompt_hash": row.prompt_hash,
                        "response_hash": row.response_hash,
                        "model_name": row.model_name,
                        "status": row.status,
                        "timed_out": bool(row.timed_out),
                        "fallback_path": row.fallback_path,
                        "confidence_label": row.confidence_label,
                        "started_at": row.started_at.isoformat() if row.started_at else None,
                        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                        "duration_ms": row.duration_ms,
                        "error_message": row.error_message,
                    }
                    for row in llm_calls
                ],
            }
    except Exception as exc:
        logger.debug("processing job audit unavailable for %s: %s", job_id, exc)
        return None


def find_jobs(
    *,
    correlation_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    batch_file_id: Optional[str] = None,
    qc_result_id: Optional[str] = None,
    source_document_hash: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find Python jobs by Java correlation context or document hash."""
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        with get_db() as db:
            query = db.query(ProcessingJob)
            if correlation_id:
                query = query.filter(ProcessingJob.correlation_id == correlation_id)
            if batch_id:
                query = query.filter(ProcessingJob.batch_id == str(batch_id))
            if batch_file_id:
                query = query.filter(ProcessingJob.batch_file_id == str(batch_file_id))
            if qc_result_id:
                query = query.filter(ProcessingJob.qc_result_id == str(qc_result_id))
            if source_document_hash:
                query = query.filter(ProcessingJob.source_document_hash == source_document_hash)

            rows = query.order_by(ProcessingJob.started_at.desc()).limit(max(1, min(limit, 200))).all()
            return [
                {
                    "job_id": str(row.id),
                    "correlation_id": row.correlation_id,
                    "batch_id": row.batch_id,
                    "batch_file_id": row.batch_file_id,
                    "qc_result_id": row.qc_result_id,
                    "source_document_hash": row.source_document_hash,
                    "original_filename": row.original_filename,
                    "status": row.status,
                    "stage": row.current_stage,
                    "retry_count": row.retry_count or 0,
                    "document_id": str(row.document_id) if row.document_id else None,
                    "model_provider": row.model_provider,
                    "model_name": row.model_name,
                    "vision_model": row.vision_model,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "failed_at": row.failed_at.isoformat() if row.failed_at else None,
                    "failure_reason": row.failure_reason,
                }
                for row in rows
            ]
    except Exception as exc:
        logger.debug("processing job search unavailable: %s", exc)
        return []


def mark_job_started(job_id: Optional[str], stage: str = "started") -> None:
    update_job(job_id, status="in_progress", current_stage=stage)


def mark_job_queued(job_id: Optional[str], stage: str = "queued", reason: Optional[str] = None) -> None:
    values: dict[str, Any] = {"status": "queued", "current_stage": stage}
    if reason is not None:
        values["failure_reason"] = str(reason)[:4000]
    update_job(job_id, **values)


def try_claim_job(
    job_id: Optional[str],
    *,
    stage: str,
    stale_after_seconds: int = 1800,
    allow_failed_retry: bool = True,
) -> bool:
    """
    Atomically claim a durable job for execution.

    Returns False when another live worker/request owns it. Stale in-progress
    jobs may be reclaimed so a worker crash does not permanently wedge Java.
    """
    if not job_id:
        return False
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        with get_db() as db:
            job = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.id == uuid.UUID(str(job_id)))
                .with_for_update()
                .first()
            )
            if not job:
                return False

            status = (job.status or "").lower()
            if status == "completed":
                return False
            if status == "failed" and not allow_failed_retry:
                return False
            if status == "in_progress":
                # Older/badly interrupted rows may have status=in_progress but
                # no real owner stage. Treat those as claimable so a queued
                # Celery task does not back off forever from its own durable job.
                stage_name = (job.current_stage or "").strip().lower()
                if stage_name in {"", "queued", "queue_submit", "retry_wait"}:
                    pass
                else:
                    updated_at = job.updated_at or job.started_at
                    stale_cutoff = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
                    if updated_at and updated_at > stale_cutoff:
                        return False

            job.status = "in_progress"
            job.current_stage = stage
            job.failure_reason = None
            job.failed_at = None
            job.updated_at = datetime.utcnow()
            return True
    except Exception as exc:
        logger.debug("processing job claim skipped for %s: %s", job_id, exc)
        return False


def increment_retry(job_id: Optional[str]) -> None:
    if not job_id:
        return
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        with get_db() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(str(job_id))).first()
            if job:
                job.retry_count = (job.retry_count or 0) + 1
                job.updated_at = datetime.utcnow()
    except Exception as exc:
        logger.debug("retry count update skipped: %s", exc)


def complete_job(job_id: Optional[str], *, document_id: Optional[str], result_payload: Optional[dict[str, Any]]) -> None:
    values: dict[str, Any] = {
        "status": "completed",
        "current_stage": "completed",
        "completed_at": datetime.utcnow(),
        "failed_at": None,
        "failure_reason": None,
    }
    if document_id:
        values["document_id"] = uuid.UUID(str(document_id))
    if result_payload is not None:
        values["result_json"] = json.dumps(result_payload, default=str)
    update_job(job_id, **values)


def fail_job(job_id: Optional[str], reason: str, stage: Optional[str] = None) -> None:
    update_job(
        job_id,
        status="failed",
        current_stage=stage or current_stage() or "failed",
        failed_at=datetime.utcnow(),
        failure_reason=str(reason)[:4000],
    )


def update_job(job_id: Optional[str], **values: Any) -> None:
    if not job_id:
        return
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingJob

        with get_db() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(str(job_id))).first()
            if not job:
                return
            for key, value in values.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = datetime.utcnow()
    except Exception as exc:
        logger.debug("processing job update skipped: %s", exc)


@contextmanager
def stage(stage_name: str, metadata: Optional[dict[str, Any]] = None):
    job_id = current_job_id()
    stage_token = _CURRENT_STAGE.set(stage_name)
    stage_id: Optional[int] = None
    started = time.time()
    if job_id:
        update_job(job_id, status="in_progress", current_stage=stage_name)
        stage_id = _create_stage(job_id, stage_name, metadata)
    with _otel_span(stage_name, metadata):
        try:
            yield
            if stage_id:
                _finish_stage(stage_id, "completed", None, started)
        except Exception as exc:
            if stage_id:
                _finish_stage(stage_id, "failed", str(exc), started)
            fail_job(job_id, str(exc), stage_name)
            raise
        finally:
            _CURRENT_STAGE.reset(stage_token)


def log_llm_call(
    *,
    prompt: str,
    model_name: str,
    task_name: Optional[str],
    started_at: float,
    response: Optional[str] = None,
    status: str = "completed",
    timed_out: bool = False,
    fallback_path: Optional[str] = None,
    confidence_label: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    try:
        from app.database import get_db
        from app.models.db_models import LLMCallLog

        job_id = current_job_id()
        corr_id = current_correlation_id()
        prompt_hash = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
        response_hash = hashlib.sha256(response.encode("utf-8")).hexdigest() if response else None
        started_dt = datetime.utcfromtimestamp(started_at)
        completed = datetime.utcnow()
        row = LLMCallLog(
            job_id=uuid.UUID(str(job_id)) if job_id else None,
            correlation_id=corr_id,
            stage_name=current_stage(),
            task_name=task_name,
            prompt_hash=prompt_hash,
            model_name=model_name,
            started_at=started_dt,
            completed_at=completed,
            duration_ms=int((time.time() - started_at) * 1000),
            status=status,
            timed_out=timed_out,
            fallback_path=fallback_path,
            confidence_label=confidence_label,
            response_hash=response_hash,
            error_message=(error_message or "")[:4000] if error_message else None,
        )
        with get_db() as db:
            db.add(row)
    except Exception as exc:
        logger.debug("llm call log skipped: %s", exc)


def _create_stage(job_id: str, stage_name: str, metadata: Optional[dict[str, Any]]) -> Optional[int]:
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingStage

        with get_db() as db:
            row = ProcessingStage(
                job_id=uuid.UUID(str(job_id)),
                stage_name=stage_name,
                status="started",
                metadata_json=json.dumps(metadata, default=str) if metadata else None,
            )
            db.add(row)
            db.flush()
            return row.id
    except Exception as exc:
        logger.debug("processing stage create skipped: %s", exc)
        return None


def _finish_stage(stage_id: int, status: str, error_message: Optional[str], started: float) -> None:
    try:
        from app.database import get_db
        from app.models.db_models import ProcessingStage

        with get_db() as db:
            row = db.query(ProcessingStage).filter(ProcessingStage.id == stage_id).first()
            if not row:
                return
            row.status = status
            row.completed_at = datetime.utcnow()
            row.duration_ms = int((time.time() - started) * 1000)
            row.error_message = (error_message or "")[:4000] if error_message else None
    except Exception as exc:
        logger.debug("processing stage finish skipped: %s", exc)


def _update_job_context(job, correlation_id, batch_id, batch_file_id, qc_result_id, traceparent=None, tracestate=None) -> None:
    if correlation_id and not job.correlation_id:
        job.correlation_id = correlation_id
    if batch_id is not None and not job.batch_id:
        job.batch_id = str(batch_id)
    if batch_file_id is not None and not job.batch_file_id:
        job.batch_file_id = str(batch_file_id)
    if qc_result_id is not None and not job.qc_result_id:
        job.qc_result_id = str(qc_result_id)
    if traceparent and not getattr(job, "traceparent", None):
        job.traceparent = traceparent
    if tracestate and not getattr(job, "tracestate", None):
        job.tracestate = tracestate


def _safe_json_loads(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


@contextmanager
def _otel_span(stage_name: str, metadata: Optional[dict[str, Any]] = None):
    """
    Optional OpenTelemetry span.

    The service remains runnable without OpenTelemetry installed, but when an
    OTel runtime is present these stage rows also become distributed trace spans.
    """
    span_cm = nullcontext(None)
    try:
        from opentelemetry import trace
        parent_context = None
        active_span = trace.get_current_span()
        active_context_valid = False
        try:
            active_context_valid = active_span.get_span_context().is_valid
        except Exception:
            active_context_valid = False
        if current_traceparent() and not active_context_valid:
            try:
                from opentelemetry.propagate import extract
                carrier = {"traceparent": current_traceparent()}
                parent_context = extract(carrier)
            except Exception:
                parent_context = None
        span_cm = trace.get_tracer("appraisal_ocr").start_as_current_span(
            f"ocr.{stage_name}",
            context=parent_context,
        )
    except Exception:
        pass

    with span_cm as span:
        if span is not None:
            if current_job_id():
                span.set_attribute("processing.job_id", current_job_id())
            if current_correlation_id():
                span.set_attribute("correlation_id", current_correlation_id())
            if current_traceparent():
                span.set_attribute("traceparent", current_traceparent())
            if metadata:
                for key, value in metadata.items():
                    if value is not None:
                        span.set_attribute(f"ocr.{key}", str(value))
        yield
