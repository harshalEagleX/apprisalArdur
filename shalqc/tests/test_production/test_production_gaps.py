"""Regression tests for the production-hardening + gap-fix work (2026-07-16).

Covers, deterministically (no live LLM):
  * config posture: language default, is_production, signed-bundle resolution, prod validator
  * observability: recorders never raise + /metrics endpoint exposes the series
  * loan_program gate: engagement extraction + the four gated items are needs_engagement
  * basement WO/WU extraction from the MISMO XML (present vs feature-absent)
  * AUTO_PASS confidence-floor count in the summary
  * extraction-gap classification (XML-sourced only)
"""
import glob
import os

import pytest

from app.config import Settings


# ── config posture ───────────────────────────────────────────────────────────

def _settings(monkeypatch, **env):
    for k in ("JUDGE_MODE", "APP_DEPLOY_STRICT", "APP_ENV", "QC_REQUIRE_SIGNED_BUNDLE",
              "INTERNAL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_judge_mode_defaults_to_language(monkeypatch):
    assert _settings(monkeypatch).judge_mode == "language"


def test_production_switch_and_signed_bundle_default(monkeypatch):
    dev = _settings(monkeypatch)
    assert dev.is_production is False and dev.require_signed_bundle is False
    prod = _settings(monkeypatch, APP_DEPLOY_STRICT="true")
    assert prod.is_production is True and prod.require_signed_bundle is True   # defaults ON in prod
    # explicit override always wins
    assert _settings(monkeypatch, APP_DEPLOY_STRICT="true",
                     QC_REQUIRE_SIGNED_BUNDLE="false").require_signed_bundle is False
    assert _settings(monkeypatch, APP_ENV="production").is_production is True


def test_production_problems_flags_missing_key(monkeypatch):
    prod = _settings(monkeypatch, APP_DEPLOY_STRICT="true", TOGETHER_API_KEY_1="x")
    assert any("INTERNAL_API_KEY" in p for p in prod.production_problems())
    ok = _settings(monkeypatch, APP_DEPLOY_STRICT="true",
                   INTERNAL_API_KEY="k", TOGETHER_API_KEY_1="x")
    assert ok.production_problems() == []


# ── observability ────────────────────────────────────────────────────────────

def test_observability_recorders_never_raise():
    from app import observability as obs
    obs.record_llm_call("together", "gpt-oss-120b", cached=False, prompt_tokens=10, completion_tokens=5)
    obs.record_llm_error("together", "http_429")
    obs.record_order("EQUITYSOLUTIONS", "TO_VERIFY", 12.3)
    obs.record_order("EQUITYSOLUTIONS", "AUTO_PASS", None)


def test_metrics_endpoint_exposes_series():
    # /metrics is always open (no API key); no reload needed.
    from fastapi.testclient import TestClient
    import app.main as main
    c = TestClient(main.app)
    resp = c.get("/metrics")
    assert resp.status_code == 200
    assert b"shalqc_http_requests_total" in resp.content and b"shalqc_llm_calls_total" in resp.content


# ── loan_program gate (Gap 1) ────────────────────────────────────────────────

@pytest.mark.parametrize("order,expected", [
    ("ESTX-0007568", "FHA"), ("ESCA-0019968", "Conventional"), ("ESNV-0000885", "Conventional")])
def test_engagement_extracts_loan_program(order, expected):
    from app.extraction.engagement import extract_engagement
    files = glob.glob(f"testfiles/{order}/engagement/*")
    if not files:
        pytest.skip(f"no engagement fixture for {order}")
    fs = extract_engagement(files[0])
    assert (fs.value("loan_program") or "").startswith(expected)


def test_loan_gated_items_are_needs_engagement():
    from app.language.compiler import compile_checklist
    items = {it.item_id: it for it in compile_checklist("EQUITYSOLUTIONS", client=None)}
    for iid in ("EQ-93", "EQ-113", "EQ-114", "EQ-115"):
        it = items[iid]
        assert it.judgeable == "needs_engagement", iid
        assert "loan_program" in it.bound_labels and "fha_case_number" in it.bound_labels, iid
        # the dangerous purpose-type proxy must be gone
        assert "assignment_type" not in it.bound_labels, iid


# ── basement WO/WU extraction (Gap 3) ────────────────────────────────────────

def test_walkout_basement_extraction():
    from app.extraction.xml_extractor import extract_xml
    def load(o):
        return extract_xml(glob.glob(f"testfiles/{o}/appraisal/*.[xX][mM][lL]")[0])
    esnv = load("ESNV-0000885")
    assert esnv.value("basement_outside_entry") == "Yes"
    assert esnv.value("subject_basement_exit") == "WalkOut"
    # slab / crawlspace properties have no basement → feature-absent, not extracted
    for o in ("ESTX-0007568", "ESCA-0019968"):
        fs = load(o)
        assert fs.get("subject_basement_exit") is None


# ── AUTO_PASS confidence-floor (Gap 4) ───────────────────────────────────────

def test_confidence_floor_counted_in_summary():
    from app.language.run import build_language_report, AUTO_PASS_CONF_FLOOR
    from app.language.verdict_v2 import JudgeVerdict, StatusV2
    from app.extraction.result import ExtractedFieldSet
    v_low = JudgeVerdict(item_id="A", status=StatusV2.SATISFIED, severity="rejectable",
                         confidence=AUTO_PASS_CONF_FLOOR - 0.1)
    v_high = JudgeVerdict(item_id="B", status=StatusV2.SATISFIED, severity="rejectable",
                          confidence=0.95)
    v_info = JudgeVerdict(item_id="C", status=StatusV2.SATISFIED, severity="informational",
                          confidence=0.1)
    rep = build_language_report("O", "EQUITYSOLUTIONS",
                                {"A": v_low, "B": v_high, "C": v_info}, ExtractedFieldSet(), [])
    assert rep["summary"]["rejectable_satisfied_low_conf"] == 1   # only the low-conf rejectable


# ── extraction-gap classification (Gap P8) ───────────────────────────────────

def test_non_xml_nulled_field_is_not_an_engine_gap():
    from app.language.run import _extraction_gap
    from app.extraction.result import ExtractedFieldSet, ExtractedField, Source
    fs = ExtractedFieldSet()
    # a PDF/checkbox guess that plausibility nulled — NOT an engine gap
    fs.add(ExtractedField(canonical_name="basement_outside_entry", value=None,
                          raw_value="?", source=Source.PDF_DIGITAL, suppressed=True))
    # authoritative XML value that was suppressed — IS an engine gap
    fs.add(ExtractedField(canonical_name="legal_description", value=None,
                          raw_value="Lot 5", source=Source.XML, suppressed=True))
    assert _extraction_gap(fs, "basement_outside_entry")[0] is False
    assert _extraction_gap(fs, "legal_description")[0] is True
