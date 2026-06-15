"""
Celery application for the Apprisal OCR/QC service (Scaling Phase 1).

Wires the durable job queue the Java backend already expects (PythonClientService):
  POST /qc/submit        → enqueue qc_process_task, return {job_id}
  GET  /qc/job/{job_id}  → poll task status/result (waitForJobResult)
  /health.celery_worker_running → drives isCeleryWorkerRunning()

Broker + result backend are Redis (REDIS_URL). When Celery/Redis are unavailable the
FastAPI app still boots and /health reports celery_worker_running=false, so the Java
backend falls back to the synchronous /qc/process path (graceful degradation — P-6).

Run a worker (from the ocr-service/ directory):
    celery -A celery_app.celery_app worker \
        --concurrency=6 --prefetch-multiplier=1 --loglevel=info

Concurrency is the throughput knob (P-4); size it to the host per
readme/SCALABILITY_PLAN.md §4.1 (6–8 on a 12c/48GB box). The real ceiling above ~2
workers is the shared Groq TPM budget — see Phase 2 / Risk R-1.
"""

import os

from celery import Celery

# Single source of truth for the broker/backend URL (P-4 — configurable, no hardcode).
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

celery_app = Celery(
    "apprisal_qc",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    # Report STARTED the moment a worker picks the job up — lets the Java poller
    # (waitForJobResult) tell "queued, no worker" (PENDING > 180 s) apart from
    # "a worker is on it" inside its grace window.
    task_track_started=True,
    # Re-queue the job if the worker is killed mid-document — no lost work on
    # restart (Phase 4 resilience; P-6). Combined with prefetch=1 this is safe.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One heavy document at a time per worker slot (OCR is CPU/memory bound).
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Keep results 24 h so a late poll after a long batch still resolves.
    result_expires=86_400,
    broker_connection_retry_on_startup=True,
    # Hard ceilings so a wedged document cannot occupy a worker forever. A single
    # doc can legitimately take minutes (OCR + Groq); soft limit lets finally
    # blocks (temp-file cleanup) run before the hard kill.
    task_soft_time_limit=int(os.getenv("QC_TASK_SOFT_TIME_LIMIT", "1500")),  # 25 min
    task_time_limit=int(os.getenv("QC_TASK_TIME_LIMIT", "1800")),           # 30 min
)

# Aliases so `celery -A celery_app` resolves the app regardless of attribute lookup.
app = celery_app
