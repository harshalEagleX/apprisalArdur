"""
Optional OpenTelemetry setup for the OCR service.

The service must run without tracing dependencies in lightweight local setups.
When the opentelemetry packages and OTEL_EXPORTER_OTLP_ENDPOINT are present,
FastAPI requests and explicit processing_lifecycle stages join the distributed
trace propagated from Java through W3C traceparent/tracestate headers.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def setup_observability(app) -> None:
    if os.getenv("OTEL_ENABLED", "true").lower() in {"0", "false", "no"}:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:
        logger.debug("OpenTelemetry dependencies not installed: %s", exc)
        return

    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set; tracing exporter disabled")
        return

    provider = TracerProvider(
        resource=Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "shal-ocr-service"),
            "service.namespace": "shal",
        })
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    try:
        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass

    logger.info("OpenTelemetry tracing enabled for OCR service")
