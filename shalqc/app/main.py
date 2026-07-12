"""
app.main (api-1.0.0) — SHALqc.md §9 FastAPI app.

Mounts the health, qc, and admin routers and enforces the X-API-Key middleware
on everything EXCEPT health/docs (§9). The key is read from INTERNAL_API_KEY
(the value Java sends as X-API-Key). If INTERNAL_API_KEY is unset (local dev),
auth is disabled with a startup warning rather than locking everyone out.

Not wired in this build pass: OpenTelemetry instrumentation (§0) and the async
Celery path (§9). The synchronous /qc/process is fully functional.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import admin, corrections, health, qc

logger = logging.getLogger(__name__)

__version__ = "api-1.0.0"

_API_KEY = os.environ.get("INTERNAL_API_KEY", "").strip()
# Paths reachable without X-API-Key (SHALqc.md §9: health + docs).
_OPEN_PREFIXES = ("/live", "/health", "/docs", "/redoc", "/openapi.json")

app = FastAPI(title="SHALqc", version=__version__)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    path = request.url.path
    if _API_KEY and not path.startswith(_OPEN_PREFIXES):
        if request.headers.get("X-API-Key", "") != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "invalid or missing X-API-Key"})
    return await call_next(request)


@app.on_event("startup")
def _warn_if_open():
    if not _API_KEY:
        logger.warning("INTERNAL_API_KEY unset — API auth DISABLED (local dev mode).")


app.include_router(health.router)
app.include_router(qc.router)
app.include_router(admin.router)
app.include_router(corrections.router)
