"""
api.health (api-1.0.0) — SHALqc.md §9 health/version endpoints.

Routes: /live (liveness), /health (returns every component version — the §1
fingerprint table). No auth (§9: X-API-Key on everything EXCEPT health/docs).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.report.versions import report_versions

__version__ = "api-1.0.0"

router = APIRouter(tags=["health"])


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/health")
def health():
    """All component versions + config hashes (SHALqc.md §9 / §1)."""
    return {"status": "ok", "versions": report_versions()}
