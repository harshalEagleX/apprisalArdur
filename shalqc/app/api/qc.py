"""
api.qc (api-1.0.0) — SHALqc.md §9 QC endpoints.

Implemented here: POST /qc/process (synchronous) — accepts either an uploaded
order package (.zip, the normal Java→service flow) or, for local/testing, a
JSON body naming an already-unpacked order folder. Returns the reviewer report
(report.builder shape).

The async trio (/qc/submit, /qc/job/{id}, /qc/progress/{token}) needs the
Celery worker + Redis (SHALqc.md §9) — not wired in this build pass; those
routes are declared so the contract is visible and return 501 until Part 9's
async half lands.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.pipeline.intake import safe_extract_zip
from app.pipeline.orchestrator import run_qc

__version__ = "api-1.0.0"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qc", tags=["qc"])


@router.post("/process")
async def process(request: Request):
    """Run the synchronous QC pipeline on one order → reviewer report.

    Two input modes, branched on Content-Type (mixing an UploadFile and a JSON
    body in one FastAPI signature forces multipart and breaks JSON parsing, so
    the raw request is inspected instead):
      * multipart form with a `package` file = the order .zip (unpacked safely,
        one folder = one order per §3.1.4), or
      * JSON `{"order_dir": "..."}` naming an already-unpacked folder (local/test).
    """
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        package = form.get("package")
        if package is None:
            raise HTTPException(status_code=400, detail="multipart request missing `package` file")
        tmp = Path(tempfile.mkdtemp(prefix="shalqc_"))
        zip_path = tmp / (getattr(package, "filename", None) or "package.zip")
        zip_path.write_bytes(await package.read())
        try:
            extract_dir = safe_extract_zip(zip_path, tmp / "unpacked")
        except ValueError as exc:
            # G-1 package safety (path traversal etc.) → 422, never a 5xx (§14)
            raise HTTPException(status_code=422, detail=f"package_unsafe: {exc}")
        return run_qc(extract_dir)

    body = await request.json()
    order_dir = (body or {}).get("order_dir")
    if not order_dir:
        raise HTTPException(status_code=400, detail="provide a `package` upload or an `order_dir`")
    order_path = Path(order_dir)
    if not order_path.exists():
        raise HTTPException(status_code=404, detail=f"order_dir not found: {order_dir}")
    # Production path uses the LLM (tier-2/3 + gap-fill); pass use_llm:false to
    # run deterministic-only (tier-2/3 rules then degrade to VERIFY).
    return run_qc(order_path, llm_client=_resolve_client((body or {}).get("use_llm", True)))


def _resolve_client(use_llm):
    if not use_llm:
        return None
    from app.llm.client import get_client
    return get_client()   # None when no keys configured → rules degrade to VERIFY


class SubmitByPath(BaseModel):
    order_dir: str
    use_llm: bool = True


@router.post("/submit")
def submit(order: SubmitByPath):
    """Async submit (SHALqc.md §9). Dispatches to Celery when configured; else
    falls back to the synchronous path and returns the report inline with
    `mode: sync` (the .env "no Redis on this device" topology stays usable)."""
    from app.worker.celery_app import celery_available
    from app.worker.tasks import run_qc_task

    if not Path(order.order_dir).exists():
        raise HTTPException(status_code=404, detail=f"order_dir not found: {order.order_dir}")
    if celery_available():
        async_result = run_qc_task.delay(order.order_dir, order.use_llm)
        return {"mode": "async", "job_id": async_result.id}
    return {"mode": "sync", "report": run_qc_task(order.order_dir, order.use_llm)}


@router.get("/job/{job_id}")
def job(job_id: str):
    """Poll an async job (SHALqc.md §9)."""
    from app.worker.celery_app import celery_app, celery_available
    if not celery_available():
        raise HTTPException(status_code=409, detail="async path disabled (no Redis) — use /qc/process or /qc/submit sync mode")
    res = celery_app.AsyncResult(job_id)
    body = {"job_id": job_id, "state": res.state}
    if res.successful():
        body["report"] = res.result
    return body
