"""
Report builder + API tests (rpt-1.0.0 / api-1.0.0) — SHALqc.md §8 / §9.
"""

from pathlib import Path

import pytest

import app.rules  # register rules
from app.report.builder import build_report
from app.rules.verdict import Evidence, Status, Verdict

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "ESTX-0007568"


def _v(rule_id, status, field, message="", key=None):
    return Verdict(rule_id=rule_id, status=status, message=message, message_key=key,
                   fields_involved=[field], evidence=[Evidence(field=field, value="x", page=1)])


def test_report_orders_and_collapses():
    verdicts = [
        _v("S-3", Status.PASS, "owner_of_public_record"),
        _v("S-5", Status.FAIL, "neighborhood_name", "Neighborhood blank."),
        _v("S-1b", Status.VERIFY, "city", "Confirm city."),
        _v("C-1", Status.NOT_APPLICABLE, "did_analyze_contract"),
    ]
    rep = build_report("ORD-1", verdicts, rule_names={"S-5": "Neighborhood name valid"})
    # PASS/NA collapse to counts, only exceptions become cards
    for k, v in {"passed": 1, "failed": 1, "hold": 0, "to_verify": 1, "not_applicable": 1}.items():
        assert rep["summary"][k] == v
    assert len(rep["cards"]) == 2
    # FAIL card is first (severity order)
    assert rep["cards"][0]["status"] == "FAIL"
    assert rep["cards"][0]["what_we_checked"] == "Neighborhood name valid"
    # report.versions always present (§12 DoD #5)
    assert "components" in rep["versions"] and "config_hashes" in rep["versions"]


def test_same_root_field_collapses_to_one_card():
    # two findings on the same root field → ONE card (§8)
    verdicts = [
        _v("S-1", Status.FAIL, "property_address"),
        _v("S-1x", Status.VERIFY, "engagement.property_address"),
    ]
    rep = build_report("ORD-2", verdicts)
    assert len(rep["cards"]) == 1
    assert rep["cards"][0]["status"] == "FAIL"     # most-severe wins the card


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="fixture not present")
def test_api_qc_process_end_to_end(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    # The auth middleware reads the settings singleton (read once at boot in prod), so
    # override it directly rather than via env+reload.
    monkeypatch.setattr(main.settings, "internal_api_key", "k")
    c = TestClient(main.app)

    assert c.get("/live").status_code == 200
    assert "versions" in c.get("/health").json()
    assert c.get("/qc/rules").status_code == 401              # auth enforced
    h = {"X-API-Key": "k"}
    assert c.get("/qc/rules", headers=h).json()["count"] >= 18
    # This test validates the deterministic LEGACY rule engine (no LLM). The default
    # judge_mode is now "language" (the product path, covered by tests/test_language),
    # so pin legacy explicitly; persist:false avoids a G-3 cache hit from a prior
    # language-mode run of the same fixture (cache keys on package hash, not mode).
    r = c.post("/qc/process", headers=h,
               json={"order_dir": str(FIXTURE_DIR), "mode": "legacy", "persist": False})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK"
    assert body["summary"]["failed"] == 0        # normalizer + plausibility → no false FAIL
    assert "versions" in body
