"""
app.observability — Prometheus metrics for the QC service (SHALqc.md §0).

The Java side exposes micrometer-prometheus at /actuator/prometheus; this gives the
Python service the same visibility (request rate/latency/errors, LLM call/token/cost,
per-order QC decisions) so throughput, p95, and LLM spend are observable in prod
instead of invisible.

Dependency-graceful: if prometheus_client is not installed, every recorder is a no-op
and /metrics returns a short note — the app still runs. Install `prometheus-client`
(in requirements.txt) to get real metrics.
"""

from __future__ import annotations

import time
from typing import Optional

try:  # pragma: no cover - exercised by presence/absence of the dep
    from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge, Histogram,
                                   generate_latest)
    _ENABLED = True
except Exception:  # prometheus_client missing → no-op mode
    _ENABLED = False
    CONTENT_TYPE_LATEST = "text/plain"

    class _Noop:
        def labels(self, *_a, **_k): return self
        def inc(self, *_a, **_k): pass
        def observe(self, *_a, **_k): pass
        def set(self, *_a, **_k): pass
        def dec(self, *_a, **_k): pass

    def Counter(*_a, **_k): return _Noop()      # type: ignore
    def Gauge(*_a, **_k): return _Noop()        # type: ignore
    def Histogram(*_a, **_k): return _Noop()    # type: ignore
    def generate_latest():                       # type: ignore
        return b"# prometheus_client not installed - metrics disabled\n"


# ── metric definitions (one place) ───────────────────────────────────────────
HTTP_REQUESTS = Counter("shalqc_http_requests_total", "HTTP requests",
                        ["method", "path", "status"])
HTTP_LATENCY = Histogram("shalqc_http_request_seconds", "HTTP request latency",
                         ["method", "path"])
HTTP_INFLIGHT = Gauge("shalqc_http_inflight", "In-flight HTTP requests")

LLM_CALLS = Counter("shalqc_llm_calls_total", "LLM calls",
                    ["provider", "model", "cached"])
LLM_TOKENS = Counter("shalqc_llm_tokens_total", "LLM tokens",
                     ["provider", "model", "kind"])  # kind=prompt|completion
LLM_ERRORS = Counter("shalqc_llm_errors_total", "LLM call errors", ["provider", "reason"])

QC_ORDERS = Counter("shalqc_qc_orders_total", "QC orders processed", ["amc", "decision"])
QC_LATENCY = Histogram("shalqc_qc_order_seconds", "End-to-end QC latency per order", ["amc"])


# ── recorders (called from the LLM client / orchestrator) ────────────────────
def record_llm_call(provider: str, model: str, cached: bool,
                    prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    LLM_CALLS.labels(provider or "?", model or "?", str(bool(cached)).lower()).inc()
    if prompt_tokens:
        LLM_TOKENS.labels(provider or "?", model or "?", "prompt").inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS.labels(provider or "?", model or "?", "completion").inc(completion_tokens)


def record_llm_error(provider: str, reason: str) -> None:
    LLM_ERRORS.labels(provider or "?", reason or "?").inc()


def record_order(amc: str, decision: str, seconds: Optional[float]) -> None:
    QC_ORDERS.labels(amc or "?", decision or "?").inc()
    if seconds is not None:
        QC_LATENCY.labels(amc or "?").observe(seconds)


# ── FastAPI wiring ───────────────────────────────────────────────────────────
def _route_template(request) -> str:
    """The matched route path ('/qc/job/{job_id}'), NOT the raw URL — keeps metric
    label cardinality bounded (no per-order-id explosion)."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


def install(app) -> None:
    """Add the /metrics endpoint + the per-request timing middleware."""
    from fastapi import Request
    from fastapi.responses import Response

    @app.middleware("http")
    async def _metrics_mw(request: Request, call_next):
        HTTP_INFLIGHT.inc()
        t0 = time.perf_counter()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
            return resp
        finally:
            path = _route_template(request)
            HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - t0)
            HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
            HTTP_INFLIGHT.dec()

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
