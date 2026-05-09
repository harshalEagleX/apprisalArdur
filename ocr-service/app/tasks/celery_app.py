"""
Celery application for async document processing.

Broker + result backend: Redis (Homebrew on Mac)

Start the worker (separate terminal, --concurrency=1 is intentional on M1 8 GB
because Ollama/llava:7b occupies the full unified memory during inference):

    conda activate apprisal
    cd ocr-service
    celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1

Submit a job via POST /qc/submit → poll GET /qc/job/{job_id}.
Java uses PythonClientService.submitQCJob() + waitForJobResult().
"""

import logging
import os
import shutil
import time

from celery import Celery

os.environ.setdefault("TZ", "Asia/Kolkata")
if hasattr(time, "tzset"):
    time.tzset()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "appraisal_qc",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,           # re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1,  # one task at a time — Ollama is single-lane on M1
    result_expires=3600,           # keep results 1 hour
)


@celery_app.task(bind=True, name="process_document")
def process_document_async(
    self,
    pdf_path: str,
    file_hash: str,
    original_filename: str,
    # New path-based params (from /qc/submit — files saved to job_dir)
    engagement_path: str = None,
    contract_path: str = None,
    model_provider: str = "ollama",
    text_model: str = None,
    vision_model: str = None,
    job_dir: str = None,
    processing_job_id: str = None,
    correlation_id: str = None,
    batch_id: str = None,
    batch_file_id: str = None,
    qc_result_id: str = None,
    idempotency_key: str = None,
    traceparent: str = None,
    tracestate: str = None,
    # Legacy text params kept for any direct Celery callers
    engagement_text: str = None,
    contract_text: str = None,
):
    """
    Background task: run the full QC pipeline on a document.

    Accepts either:
      - engagement_path / contract_path  (from /qc/submit — preferred)
      - engagement_text / contract_text  (legacy direct-call form)

    Saves results to the database and returns the full QC payload as the
    Celery task result (readable via GET /qc/job/{task_id}).

    Cleans up job_dir on completion or failure.
    """
    from app.qc_processor import qc_processor
    from app.services import processing_lifecycle

    cleanup_job_dir = False
    tracked = processing_lifecycle.get_job_status(processing_job_id) if processing_job_id else None
    if tracked and tracked.get("status") == "completed" and tracked.get("result_json"):
        import json
        logger.info("Async QC task reused completed processing job: %s", processing_job_id)
        _cleanup_job_dir(job_dir)
        return json.loads(tracked["result_json"])
    if not processing_job_id:
        raise RuntimeError("Durable processing job is required for async QC")
    if not processing_lifecycle.try_claim_job(processing_job_id, stage="worker_started"):
        logger.info(
            "Async QC task backing off because processing job %s is not claimable at stage %s",
            processing_job_id,
            tracked.get("stage") if tracked else None,
        )
        raise self.retry(
            exc=RuntimeError("Processing job already in progress"),
            max_retries=3,
            countdown=min(300, 30 * (self.request.retries + 1)),
        )

    self.update_state(state="STARTED", meta={"file_hash": file_hash,
                                              "filename": original_filename})
    processing_lifecycle.mark_job_started(processing_job_id, "worker_started")

    try:
        # --- Resolve engagement text ---
        with processing_lifecycle.processing_context(processing_job_id, correlation_id, traceparent):
            if engagement_text is None and engagement_path and os.path.exists(engagement_path):
                with processing_lifecycle.stage("supporting_ocr_engagement"):
                    engagement_text = _extract_supporting_text(
                        engagement_path, "Engagement letter", os.path.basename(engagement_path))

            # --- Resolve contract text ---
            if contract_text is None and contract_path and os.path.exists(contract_path):
                with processing_lifecycle.stage("supporting_ocr_contract"):
                    contract_text = _extract_supporting_text(
                        contract_path, "Contract", os.path.basename(contract_path))

        # --- Run QC pipeline ---
        from app.services.ollama_service import ollama_request_guard, use_model_selection
        executable_text_model = text_model if (model_provider or "ollama").lower() == "ollama" else None

        with ollama_request_guard():
            with use_model_selection(text_model=executable_text_model, vision_model=vision_model):
                results = qc_processor.process_document(
                    pdf_path=pdf_path,
                    engagement_letter_text=engagement_text,
                    contract_text=contract_text,
                    file_hash=file_hash,
                    original_filename=original_filename,
                    model_provider=model_provider or "ollama",
                    model_name=text_model,
                    vision_model=vision_model,
                    processing_job_id=processing_job_id,
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    batch_file_id=batch_file_id,
                    qc_result_id=qc_result_id,
                    idempotency_key=idempotency_key,
                    traceparent=traceparent,
                    tracestate=tracestate,
                )

        payload = results.model_dump()
        payload["file_hash"] = file_hash
        payload["processing_job_id"] = processing_job_id
        processing_lifecycle.complete_job(processing_job_id, document_id=results.document_id, result_payload=payload)

        logger.info("Async QC task complete: file=%s hash=%s", original_filename, file_hash[:12])
        cleanup_job_dir = True
        return payload

    except Exception as exc:
        logger.error("Async QC task failed for %s: %s", file_hash[:12], exc, exc_info=True)
        processing_lifecycle.increment_retry(processing_job_id)
        max_retries = 3
        if self.request.retries >= max_retries:
            processing_lifecycle.fail_job(processing_job_id, str(exc))
            cleanup_job_dir = True
            raise
        processing_lifecycle.update_job(
            processing_job_id,
            status="queued",
            current_stage="retry_wait",
            failure_reason=str(exc)[:4000],
        )
        raise self.retry(exc=exc, max_retries=max_retries, countdown=min(300, 30 * (self.request.retries + 1)))

    finally:
        if cleanup_job_dir:
            _cleanup_job_dir(job_dir)


def _extract_supporting_text(path: str, label: str, filename: str) -> str:
    """Extract text from an engagement-letter or contract PDF inside the worker."""
    from app.ocr.ocr_pipeline import OCRPipeline
    pipeline = OCRPipeline(use_tesseract=True, force_image_ocr=False, use_preprocessing=True)
    try:
        result = pipeline.extract_all_pages(path)
        text = pipeline.get_full_text(result.page_index)
        logger.info("%s extracted: chars=%d file=%s", label, len(text.strip()), filename)
        return text
    except Exception as exc:
        logger.warning("%s extraction failed (%s): %s — proceeding without it", label, filename, exc)
        return ""


def _cleanup_job_dir(job_dir: str | None) -> None:
    if job_dir and os.path.exists(job_dir):
        try:
            shutil.rmtree(job_dir)
            logger.debug("Cleaned up job dir: %s", job_dir)
        except Exception as exc:
            logger.warning("Could not clean up job dir %s: %s", job_dir, exc)
