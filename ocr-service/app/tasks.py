"""
Celery tasks for QC processing (Scaling Phase 1).

`qc_process_task` runs the exact same pipeline as the synchronous POST /qc/process
endpoint — `run_transaction_qc_paths` + `report_to_python_qc_response` — but off the
web process, on a Celery worker, with a durable Redis-backed result. Its return value
is the PythonQCResponse-shaped dict the Java backend deserialises from
`GET /qc/job/{id}.result` (PythonClientService.waitForJobResult).

Contract (P-12):
  Input : temp PDF paths (created by /qc/submit) + model/document metadata.
  Output: PythonQCResponse dict (JSON-serialisable — report_to_python_qc_response -> Dict).
  Errors: any exception → Celery FAILURE state; the temp uploads are always cleaned up.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.qc_process_task")
def qc_process_task(
    self,
    appraisal_path: str,
    engagement_path: Optional[str] = None,
    contract_path: Optional[str] = None,
    xml_path: Optional[str] = None,
    model_provider: str = "groq",
    text_model: str = "",
    vision_model: str = "",
    document_id: str = "",
    source_hash: str = "",
    engagement_status: Optional[str] = None,
    amc_id: Optional[str] = None,
) -> dict:
    """Extract + run QC for one transaction; return the PythonQCResponse dict."""
    # Imported lazily so worker boot stays cheap and import errors surface per-task.
    from app.qc.python_response import report_to_python_qc_response
    from app.qc.transaction import run_transaction_qc_paths

    started = time.time()
    logger.info("qc_process_task start: job=%s appraisal=%s xml=%s",
                self.request.id, appraisal_path, xml_path)

    # Stream live progress into the Celery task state so the Java backend (which
    # polls GET /qc/job/{id}) can show a moving progress bar on the async path —
    # not just "queued 2%" until done. Each stage emits state=PROGRESS with meta.
    def _progress(stage: str, message: str, pct: float) -> None:
        try:
            self.update_state(state="PROGRESS", meta={
                "stage": stage,
                "message": message,
                "sub_percent": max(0.0, min(1.0, float(pct) / 100.0)),
                "elapsed_ms": int((time.time() - started) * 1000),
            })
        except Exception:
            pass  # progress reporting must never break the job (P-6)

    try:
        report, ctx = run_transaction_qc_paths(
            Path(appraisal_path),
            Path(engagement_path) if engagement_path else None,
            Path(contract_path) if contract_path else None,
            xml_path=Path(xml_path) if xml_path else None,
            transaction_id=document_id or "transaction",
            persist=True,
            progress=_progress,
            engagement_status=engagement_status,
            amc_id=amc_id,
        )
        resp = report_to_python_qc_response(
            report,
            ctx,
            processing_time_ms=int((time.time() - started) * 1000),
            document_id=document_id or "",
            job_id=self.request.id,
            model_provider=model_provider,
            text_model=text_model,
            vision_model=vision_model,
            file_hash=source_hash or "",
        )
        logger.info(
            "qc_process_task done: job=%s elapsed_ms=%d total_rules=%s",
            self.request.id, int((time.time() - started) * 1000), resp.get("total_rules"),
        )
        return resp
    finally:
        # The /qc/submit uploads are throwaway copies (the source of record stays in the
        # batch store — P-5); this task owns their cleanup whether it succeeds or fails.
        for p in (appraisal_path, engagement_path, contract_path, xml_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
