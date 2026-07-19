"""
app.main (api-1.1.0) — SHALqc.md §9 FastAPI app.

Mounts the health, qc, admin, and corrections routers and enforces the X-API-Key
middleware on everything EXCEPT health/docs/metrics (§9). The key is INTERNAL_API_KEY
(the value Java sends as X-API-Key).

Deploy posture (settings.is_production, one switch shared with the Java side):
  * production  → fail-CLOSED: the app refuses to start if the API key is unset or any
                  other production_problems() are present.
  * local dev   → fail-OPEN: auth disabled with a loud warning so a fresh box still runs.

Observability (§0): Prometheus metrics at /metrics + a per-request latency/count/inflight
middleware (app.observability). LLM call/token/cost counters are incremented from the
LLM client.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import admin, corrections, health, qc
from app.config import settings
from app import observability as obs

logger = logging.getLogger(__name__)

__version__ = "api-1.1.0"

# Paths reachable without X-API-Key (SHALqc.md §9: health + docs + metrics scrape).
_OPEN_PREFIXES = ("/live", "/health", "/metrics", "/docs", "/redoc", "/openapi.json")

app = FastAPI(title="SHALqc", version=__version__)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    path = request.url.path
    if settings.internal_api_key and not path.startswith(_OPEN_PREFIXES):
        if request.headers.get("X-API-Key", "") != settings.internal_api_key:
            return JSONResponse(status_code=401, content={"detail": "invalid or missing X-API-Key"})
    return await call_next(request)


@app.on_event("startup")
def _validate_startup():
    """Fail-closed in production, fail-open (warn) in dev — the single posture switch."""
    problems = settings.production_problems()
    if problems:
        if settings.is_production:
            raise RuntimeError(
                "SHALqc refuses to start: production posture (APP_DEPLOY_STRICT / APP_ENV=prod) "
                "but insecure/incomplete config:\n  - " + "\n  - ".join(problems))
        for p in problems:
            logger.warning("startup (dev, fail-open): %s", p)


obs.install(app)  # /metrics + request middleware

app.include_router(health.router)
app.include_router(qc.router)
app.include_router(admin.router)
app.include_router(corrections.router)
