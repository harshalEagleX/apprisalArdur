"""
api.qc (api-1.0.0) — SHALqc.md §9 QC endpoints.

Implemented here: POST /qc/process (synchronous) — accepts either an uploaded
order package (.zip, the normal Java→service flow) or, for local/testing, a
JSON body naming an already-unpacked order folder. Returns the reviewer report
(report.builder shape).

GET /qc/progress/{token} is live: /qc/process runs in the thread pool and
publishes eased stage progress to app.pipeline.progress, which this endpoint
serves to the Java poller (drives the admin "Background activity" bar).

The async submit trio (/qc/submit, /qc/job/{id}) still needs the Celery worker +
Redis (SHALqc.md §9) and falls back to the synchronous path until Part 9 lands.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.pipeline import progress as _progress
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
        # Mode A (Java): individual file parts appraisal/xml/engagement/contract
        # (mirrors PythonClientService.buildBaseBody). Mode B: a single `package`
        # zip. Individual files win when an `appraisal` part is present.
        if form.get("appraisal") is not None:
            extract_dir = await _order_dir_from_files(form)
        else:
            package = form.get("package")
            if package is None:
                raise HTTPException(status_code=400,
                                    detail="multipart request missing `appraisal` or `package` file")
            tmp = Path(tempfile.mkdtemp(prefix="shalqc_"))
            zip_path = tmp / (getattr(package, "filename", None) or "package.zip")
            zip_path.write_bytes(await package.read())
            try:
                extract_dir = safe_extract_zip(zip_path, tmp / "unpacked")
            except ValueError as exc:
                # G-1 package safety (path traversal etc.) → 422, never a 5xx (§14)
                raise HTTPException(status_code=422, detail=f"package_unsafe: {exc}")
        # Java integration runs the language judge (OrderQCResponse: cards +
        # coordinates + llm_interactions). use_llm defaults on.
        use_llm = str(form.get("use_llm", "true")).lower() not in ("false", "0", "no")
        # Java passes the client's AMC code so shalqc loads THAT AMC's compiled
        # bundle (e.g. EQUITYSOLUTIONS) rather than resolving from the temp order
        # dir and falling back to _base.
        amc_code = form.get("amc_code") or None
        # Java hands us a progress_token and polls GET /qc/progress/{token} to
        # drive the admin bar. Register it up front so the first poll (which can
        # arrive before run_qc reaches its first stage) already resolves.
        token = _clean_token(form.get("progress_token"))
        _progress.start(token)
        # run_qc is fully blocking (OCR + minutes of LLM). Run it in the thread
        # pool so the event loop stays free to answer /qc/progress/{token} and
        # /live DURING the run — on the loop it would freeze the whole service.
        try:
            return await run_in_threadpool(
                run_qc, extract_dir, llm_client=_resolve_client(use_llm),
                mode="language", amc_code=amc_code, progress_token=token)
        finally:
            _progress.finish(token)

    body = await request.json()
    order_dir = (body or {}).get("order_dir")
    if not order_dir:
        raise HTTPException(status_code=400, detail="provide a `package` upload or an `order_dir`")
    order_path = Path(order_dir)
    if not order_path.exists():
        raise HTTPException(status_code=404, detail=f"order_dir not found: {order_dir}")
    # Production path uses the LLM (tier-2/3 + gap-fill); pass use_llm:false to
    # run deterministic-only (tier-2/3 rules then degrade to VERIFY). `persist:false`
    # runs without touching the run cache/DB (local/test — avoids a G-3 cache hit from
    # a prior run of a different mode; the cache keys on package hash, not mode).
    mode = (body or {}).get("mode")   # None → settings.judge_mode
    persist = bool((body or {}).get("persist", True))
    token = _clean_token((body or {}).get("progress_token"))
    _progress.start(token)
    try:
        return await run_in_threadpool(
            run_qc, order_path, llm_client=_resolve_client((body or {}).get("use_llm", True)),
            mode=mode, persist=persist, progress_token=token)
    finally:
        _progress.finish(token)


async def _order_dir_from_files(form) -> Path:
    """Materialize an order folder from Java's individual multipart file parts,
    laid out the way assemble_order expects: appraisal/ (pdf + optional xml),
    engagement/, contract/. Returns the order dir path."""
    base = Path(tempfile.mkdtemp(prefix="shalqc_order_"))
    async def _save(part, subdir: str, default_name: str):
        if part is None:
            return
        d = base / subdir
        d.mkdir(parents=True, exist_ok=True)
        name = getattr(part, "filename", None) or default_name
        (d / name).write_bytes(await part.read())
    await _save(form.get("appraisal"), "appraisal", "appraisal.pdf")
    await _save(form.get("xml"), "appraisal", "appraisal.xml")
    await _save(form.get("engagement"), "engagement", "engagement.pdf")
    await _save(form.get("contract"), "contract", "contract.pdf")
    return base


def _resolve_client(use_llm):
    if not use_llm:
        return None
    from app.llm.client import get_client
    return get_client()   # None when no keys configured → rules degrade to VERIFY


def _clean_token(raw) -> Optional[str]:
    """A safe, bounded progress token from an untrusted form/JSON field."""
    if not raw:
        return None
    s = str(raw).strip()
    return s[:64] if s else None


@router.get("/progress/{token}")
def progress(token: str):
    """Live sub-progress for a running QC job (SHALqc.md §9). Java's
    PythonClientService polls this every ~1.5s to drive the admin bar; keys are
    {stage, message, sub_percent, elapsed_ms}. 404 when the token is unknown
    (not started yet, or already evicted) — the poller tolerates a few 404s."""
    snap = _progress.snapshot(token)
    if snap is None:
        raise HTTPException(status_code=404, detail="unknown or expired progress token")
    return snap


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
