"""
Celery application for async document processing.

Broker + result backend: Redis (docker-compose service)

Usage:
    # Start worker (separate terminal):
    conda activate apprisal
    celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2

    # Submit a task from Python:
    from app.tasks.celery_app import process_document_async
    result = process_document_async.delay(pdf_path, engagement_text, contract_text)
    job_id = result.id
    # Poll:  result.status  /  result.get(timeout=120)
"""

import logging
import os
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
    task_acks_late=True,              # re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1,     # one task at a time per worker (OCR is heavy)
    result_expires=3600,              # keep results for 1 hour
)


@celery_app.task(bind=True, name="process_document")
def process_document_async(
    self,
    pdf_path: str,
    file_hash: str,
    original_filename: str,
    engagement_text: str = None,
    contract_text: str = None,
):
    """
    Background task: run the full QC pipeline on a document.

    Saves results to the database.  The caller polls by task ID.

    Returns:
        dict — same schema as /qc/process JSON response
    """
    from app.qc_processor import qc_processor
    from app.services.cache_service import save_rule_results

    self.update_state(state="STARTED", meta={"file_hash": file_hash})

    try:
        results = qc_processor.process_document(
            pdf_path=pdf_path,
            engagement_letter_text=engagement_text,
            contract_text=contract_text,
        )
        payload = results.model_dump()
        payload["file_hash"] = file_hash

        # Persist rule results if we have a document_id (set by cache_service)
        doc_id = payload.get("document_id")
        if doc_id:
            save_rule_results(doc_id, results.rule_results)

        return payload

    except Exception as exc:
        logger.error("Background task failed for %s: %s", file_hash[:12], exc)
        raise self.retry(exc=exc, max_retries=0)  # don't retry OCR failures
