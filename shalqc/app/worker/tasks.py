"""
worker.tasks — SHALqc.md §2/§9. The single pipeline task: run_qc(order).

Delegates to pipeline.orchestrator.run_qc (intake → extract → rules → report →
persist) so the async and sync paths run IDENTICAL logic — the only difference
is who invokes it (a Celery worker vs the request thread). When Celery isn't
configured, the task function is still importable/callable directly (the sync
fallback the API uses).
"""

from __future__ import annotations

from app.pipeline.orchestrator import run_qc as _run_qc
from app.worker.celery_app import celery_app

__version__ = "api-1.0.0"


def _run(order_dir: str, use_llm: bool = True) -> dict:
    client = None
    if use_llm:
        from app.llm.client import get_client
        client = get_client()
    return _run_qc(order_dir, llm_client=client)


if celery_app is not None:
    @celery_app.task(name="shalqc.run_qc")
    def run_qc_task(order_dir: str, use_llm: bool = True) -> dict:
        return _run(order_dir, use_llm=use_llm)
else:  # sync fallback — callable directly, no Celery registration
    def run_qc_task(order_dir: str, use_llm: bool = True) -> dict:  # type: ignore[misc]
        return _run(order_dir, use_llm=use_llm)
