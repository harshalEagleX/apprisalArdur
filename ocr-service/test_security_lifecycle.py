import importlib
import io
import os
import sys

import fitz
from fastapi.testclient import TestClient


def _load_main_with_api_key(monkeypatch):
    monkeypatch.setenv("PYTHON_API_KEY", "test-secret")
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_protected_endpoints_reject_missing_api_key(monkeypatch):
    main = _load_main_with_api_key(monkeypatch)
    client = TestClient(main.app)

    checks = [
        ("GET", "/qc/rules"),
        ("GET", "/qc/progress/missing-token"),
        ("GET", "/qc/job/00000000-0000-0000-0000-000000000000"),
        ("GET", "/qc/jobs?correlation_id=batch:1"),
        ("GET", "/analytics/summary"),
        ("POST", "/qc/feedback"),
    ]

    for method, path in checks:
        response = client.request(method, path, json={})
        assert response.status_code == 401, (method, path, response.status_code, response.text)


def test_health_remains_public_when_api_key_is_enabled(monkeypatch):
    main = _load_main_with_api_key(monkeypatch)
    client = TestClient(main.app)

    response = client.get("/health")
    assert response.status_code == 200


def test_expensive_qc_endpoint_is_rate_limited(monkeypatch):
    main = _load_main_with_api_key(monkeypatch)
    client = TestClient(main.app)
    headers = {"X-API-Key": "test-secret"}
    pdf_bytes = _minimal_pdf_bytes()

    responses = [
        client.post(
            "/qc/process",
            headers=headers,
            files={"file": ("rate.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        for _ in range(21)
    ]

    assert any(response.status_code == 429 for response in responses)


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Uniform Residential Appraisal Report")
    data = doc.tobytes()
    doc.close()
    return data


def teardown_module():
    os.environ.pop("PYTHON_API_KEY", None)
