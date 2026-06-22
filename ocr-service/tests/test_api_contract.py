"""
API-contract regression tests for the FastAPI service (REGRESSION_AUDIT.md):
  - GET /qc/rules (added in a16bcfa) returns the registered rule catalog (200), and
    enforces the X-API-Key when INTERNAL_API_KEY is configured.
  - POST /qc/process with a missing required file is a client error (4xx), never a 500.
  - GET /live is public.

Uses Starlette's TestClient without the lifespan context manager so these run without
a live DB/Celery — they only exercise the request/response contract.
"""
import app.config as app_config
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
KEY = app_config.INTERNAL_API_KEY
AUTH = {"X-API-Key": KEY} if KEY else {}


def test_live_is_public():
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json().get("status") == "alive"


def test_qc_rules_returns_catalog():
    r = client.get("/qc/rules", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert body["total"] == len(body["rules"])
    assert body["total"] > 100  # ~134 registered rules
    sample = body["rules"][0]
    assert {"rule_id", "checklist_num", "section", "phase", "name"} <= set(sample)


def test_qc_rules_requires_api_key_when_configured():
    if not KEY:
        # Auth disabled in this environment (no INTERNAL_API_KEY) — nothing to assert.
        return
    r = client.get("/qc/rules")  # no X-API-Key
    assert r.status_code == 401


def test_qc_process_missing_file_is_client_error_not_500():
    # No multipart 'file' part → FastAPI rejects as a validation (4xx) error,
    # and must never surface as a 500.
    r = client.post("/qc/process", headers=AUTH)
    assert r.status_code < 500
    assert r.status_code in (400, 422)
