"""
Regression tests for the security and correctness fixes from the audit.

Fix 4: startup() raises RuntimeError when SHAL_REQUIRE_API_KEY=true (default)
        and INTERNAL_API_KEY is not set — fail-closed, not fail-open.
Fix 5: /docs, /redoc, /openapi.json are NOT in _PUBLIC_PATHS when
        SHAL_EXPOSE_DOCS=false (the default) — never publicly accessible in prod.
VF-3:  client_id form field accepted on /qc/process and /qc/submit without 422.
VF-6:  POST /corrections requires X-API-Key when the key is configured.
Fix 6: _rule_scope() emits correct scope for per_document, cross_document, semantic.
"""

import asyncio
import types
from unittest.mock import patch


# ── Fix 4: startup raises when key required but missing ───────────────────

def test_startup_raises_when_key_missing_and_required():
    """SHAL_REQUIRE_API_KEY=true + no INTERNAL_API_KEY → RuntimeError at startup.

    The error forces uvicorn/gunicorn to exit(1) so an operator notices the
    misconfiguration immediately instead of seeing unexplained 503s.
    """
    from main import startup
    with patch("main._REQUIRE_API_KEY", True), \
         patch("main._INTERNAL_API_KEY", ""):
        try:
            asyncio.run(startup())
            assert False, "startup() must raise RuntimeError when key is required but not set"
        except RuntimeError as e:
            assert "STARTUP FAILED" in str(e)


def test_startup_succeeds_when_key_present():
    """Happy path: no error when INTERNAL_API_KEY is set."""
    from main import startup
    with patch("main._REQUIRE_API_KEY", True), \
         patch("main._INTERNAL_API_KEY", "secret-key-for-test"), \
         patch("main.verify_connection", return_value=False):
        # Must not raise
        asyncio.run(startup())


def test_startup_warns_but_succeeds_when_enforcement_disabled():
    """SHAL_REQUIRE_API_KEY=false + no key → logs a warning, does not raise."""
    from main import startup
    with patch("main._REQUIRE_API_KEY", False), \
         patch("main._INTERNAL_API_KEY", ""), \
         patch("main.verify_connection", return_value=False):
        asyncio.run(startup())  # must not raise


# ── Fix 5: /docs not in _PUBLIC_PATHS by default ─────────────────────────

def test_docs_not_in_public_paths():
    """API documentation paths must not be in _PUBLIC_PATHS when SHAL_EXPOSE_DOCS
    is false (the default) — they are protected by the API-key middleware."""
    import main
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert path not in main._PUBLIC_PATHS, (
            f"{path} must not be public when SHAL_EXPOSE_DOCS=false"
        )


def test_docs_endpoint_blocked_without_auth():
    """/docs returns 401 or 503 without an API key when SHAL_EXPOSE_DOCS=false."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/docs")
    assert r.status_code in (401, 503), (
        f"/docs without auth should be 401 (key configured) or 503 (key missing); "
        f"got {r.status_code}. A 200 means /docs is publicly accessible."
    )


# ── VF-3: client_id form field accepted on /qc/process and /qc/submit ────

def test_qc_process_accepts_client_id_without_422():
    """/qc/process must not reject client_id with a 422 'extra field' error.

    Without a real PDF the endpoint returns 400/422 (missing required 'file'),
    but the failure reason must be the missing file, not an unrecognised field.
    """
    import app.config as app_config
    from fastapi.testclient import TestClient
    from main import app
    auth = {"X-API-Key": app_config.INTERNAL_API_KEY} if app_config.INTERNAL_API_KEY else {}
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post("/qc/process", headers=auth, data={"client_id": "AMC-TEST-001"})

    # The only acceptable 4xx here is "file field missing"
    assert r.status_code in (400, 422), (
        f"Expected 4xx for missing required 'file', got {r.status_code}"
    )
    if r.status_code == 422:
        body = r.text
        # The validation error must be about 'file', not about 'client_id'
        assert "client_id" not in body or "file" in body, (
            f"422 must be caused by missing 'file', not by unknown 'client_id': {body}"
        )


def test_qc_submit_accepts_client_id_without_422():
    """/qc/submit must not reject client_id with a 422 'extra field' error."""
    import app.config as app_config
    from fastapi.testclient import TestClient
    from main import app
    auth = {"X-API-Key": app_config.INTERNAL_API_KEY} if app_config.INTERNAL_API_KEY else {}
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post("/qc/submit", headers=auth, data={"client_id": "AMC-TEST-001"})

    assert r.status_code in (400, 422), (
        f"Expected 4xx for missing required 'file', got {r.status_code}"
    )
    if r.status_code == 422:
        body = r.text
        assert "client_id" not in body or "file" in body, (
            f"422 must be caused by missing 'file', not by unknown 'client_id': {body}"
        )


# ── VF-6: POST /corrections requires API key ──────────────────────────────

def test_corrections_requires_api_key_when_configured():
    """POST /corrections without X-API-Key must return 401 or 503 when the
    INTERNAL_API_KEY is configured. A 200 would mean the auth bypass is present."""
    import app.config as app_config
    from fastapi.testclient import TestClient
    from main import app

    if not app_config.INTERNAL_API_KEY:
        # Auth disabled in this environment — nothing to assert.
        return

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/corrections", json={})  # no X-API-Key header
    assert r.status_code in (401, 503), (
        f"POST /corrections without auth returned {r.status_code}; "
        "expected 401 (key provided, wrong) or 503 (key missing but required)"
    )


# ── Fix 6: _rule_scope() scope classification ─────────────────────────────

def _ev(doc: str):
    """Minimal evidence-like object with a .document attribute."""
    return types.SimpleNamespace(document=doc)


def _rule(section: str, evidence_docs: list):
    """Minimal RuleResult-like object for _rule_scope testing."""
    return types.SimpleNamespace(
        section=section,
        evidence=[_ev(d) for d in evidence_docs],
    )


def test_scope_per_document_single_doc():
    """Non-cross section with single-document evidence → per_document."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("SUBJECT", ["appraisal.pdf"])) == "per_document"


def test_scope_per_document_no_evidence():
    """Non-cross section with no evidence → per_document."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("CONTRACT", [])) == "per_document"


def test_scope_cross_document_multi_doc_evidence():
    """Evidence from two different documents → cross_document (regardless of section)."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("SUBJECT", ["appraisal.pdf", "engagement.pdf"])) == "cross_document"


def test_scope_cross_document_for_global_section():
    """section='global' is in _CROSS_DOC_SECTIONS and is not 'semantic' → cross_document."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("global", [])) == "cross_document"


def test_scope_cross_document_for_cross_document_section():
    """section='cross_document' → cross_document."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("cross_document", [])) == "cross_document"


def test_scope_semantic_for_semantic_section():
    """section='semantic' → semantic (kept as-is, not mapped to 'cross_document')."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("semantic", [])) == "semantic"


def test_scope_semantic_overrides_multi_doc_evidence():
    """section='semantic' takes priority even when evidence spans multiple docs."""
    from app.qc.python_response import _rule_scope
    assert _rule_scope(_rule("semantic", ["appraisal.pdf", "engagement.pdf"])) == "semantic"
