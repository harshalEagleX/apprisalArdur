"""
§14 intake gates + §15 revision diff + §16 partial-failure tests.

DB-free: the revision diff is a pure function; persistence runs in its no-op
mode (no DATABASE_URL in the test env), which is itself the §15 graceful path.
"""

import zipfile
from pathlib import Path

import pytest

from app.persistence.repo import diff_findings


# ── §14 G-1 package safety ──────────────────────────────────────────────────

def test_g1_rejects_path_traversal(tmp_path):
    from app.pipeline.intake import safe_extract_zip
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ValueError, match="unsafe path"):
        safe_extract_zip(bad, tmp_path / "out")


def test_g1_rejects_zip_bomb(tmp_path):
    from app.pipeline.intake import safe_extract_zip
    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", "0" * (5 * 1024 * 1024))   # 5MB of zeros → tiny compressed
    with pytest.raises(ValueError, match="zip-bomb"):
        safe_extract_zip(bomb, tmp_path / "out")


def test_g1_accepts_normal_zip(tmp_path):
    from app.pipeline.intake import safe_extract_zip
    ok = tmp_path / "ok.zip"
    with zipfile.ZipFile(ok, "w") as zf:
        zf.writestr("a.txt", "hello world")
    out = safe_extract_zip(ok, tmp_path / "out")
    assert (out / "a.txt").read_text() == "hello world"


# ── §14 G-2 XML-belongs-to-report ───────────────────────────────────────────

_FIX = Path(__file__).parent.parent / "fixtures" / "ESTX-0007568" / "appraisal"
_FOREIGN_XML = Path("/Users/eaglex/Documents/indevelopment/eaglex/SHAL/ocr-service/"
                    "exttestfile/ESMI-0048528/apprisal/10735 Secor Rd.xml")


@pytest.mark.skipif(not _FIX.exists(), reason="fixture not present")
def test_g2_matching_xml_keeps_overlay():
    from app.pipeline.intake import OrderDocuments, apply_g2_xml_gate
    o = OrderDocuments(order_dir=_FIX, appraisal_pdf=_FIX / "7243 Foxtail Meadow Ct.pdf",
                       xml=_FIX / "7243 Foxtail Meadow Ct.xml", order_id="right")
    apply_g2_xml_gate(o)
    assert o.xml_overlay_disabled is False


@pytest.mark.skipif(not (_FIX.exists() and _FOREIGN_XML.exists()),
                    reason="fixture or foreign XML not present")
def test_g2_wrong_xml_disables_overlay():
    from app.pipeline.intake import OrderDocuments, apply_g2_xml_gate
    o = OrderDocuments(order_dir=_FIX, appraisal_pdf=_FIX / "7243 Foxtail Meadow Ct.pdf",
                       xml=_FOREIGN_XML, order_id="wrong")
    apply_g2_xml_gate(o)
    assert o.xml_overlay_disabled is True   # §20 DoD #6


# ── §14 G-3 idempotency hash ────────────────────────────────────────────────

def test_g3_package_hash_stable_and_sensitive(tmp_path):
    from app.pipeline.intake import package_sha256
    d = tmp_path / "order"
    d.mkdir()
    (d / "a.txt").write_text("one")
    h1 = package_sha256(d)
    h2 = package_sha256(d)
    assert h1 == h2                       # stable
    (d / "a.txt").write_text("two")
    assert package_sha256(d) != h1        # content change → new hash


# ── §15 revision diff (pure) ────────────────────────────────────────────────

def test_revision_diff_labels():
    prev = [
        {"rule_id": "S-1", "message_key": "S-1.address_mismatch", "root_field": "property_address"},
        {"rule_id": "S-5", "message_key": "S-5.neighborhood_invalid", "root_field": "neighborhood_name"},
    ]
    curr = [
        {"rule_id": "S-1", "message_key": "S-1.address_mismatch", "root_field": "property_address"},  # still open
        {"rule_id": "C-1", "message_key": "C-1.not_analyzed", "root_field": "did_analyze_contract"},   # new
    ]
    d = diff_findings(prev, curr)
    assert [f["rule_id"] for f in d["still_open"]] == ["S-1"]
    assert [f["rule_id"] for f in d["new"]] == ["C-1"]
    assert [f["rule_id"] for f in d["resolved"]] == ["S-5"]


# ── §16 partial-failure contract ────────────────────────────────────────────

def test_partial_failure_completes_with_degradation(monkeypatch):
    """An injected mid-stage (extraction) exception must yield a COMPLETE report
    with degradations[] populated — never a raised 5xx (§16 / §20 DoD #8)."""
    import app.pipeline.orchestrator as orch

    FIXTURE = Path(__file__).parent.parent / "fixtures" / "ESTX-0007568"
    if not FIXTURE.exists():
        pytest.skip("fixture not present")

    def boom(**kwargs):
        raise RuntimeError("injected extraction failure")

    monkeypatch.setattr(orch, "run_extraction", boom)
    rep = orch.run_qc(FIXTURE, llm_client=None, persist=False)
    assert rep["status"] == "OK"                        # completed, not crashed
    assert any("stage_failed:extraction" in d for d in rep["degradations"])
    assert "versions" in rep


# ── §15 persistence no-op path ──────────────────────────────────────────────

def test_persistence_graceful_without_db(monkeypatch):
    from app.persistence import repo
    # force no-op mode regardless of env
    monkeypatch.setattr(repo, "_engine_ready", True, raising=False)
    monkeypatch.setattr(repo, "_engine", None, raising=False)
    assert repo.available() is False
    assert repo.get_cached_run("O", "hash") is None      # safe no-op
    assert repo.next_revision_no("O") == 0
    assert repo.save_run("O", "EQUITYSOLUTIONS", "h", "fp", 0, {"summary": {}}) is None
