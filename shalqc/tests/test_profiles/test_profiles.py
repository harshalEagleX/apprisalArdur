"""
AMC profile tests (prof-*) — SHALqc.md §6 / §12 DoD #3.

Proves the three things the profile layer must do without engine code changes:
deep-merge over _base, unknown-code fallback, and severity remap changing output.
"""

import app.rules  # register rules
from app.profiles.engine_binding import active_rules, apply_severity
from app.profiles.loader import load_profile, profile_loader
from app.rules.verdict import Status, Verdict


def setup_function(_):
    profile_loader.reload()  # drop cache between tests


def test_base_profile_loads():
    p = load_profile(None)
    assert p.amc_code == "_base"
    assert p.rules_default_on is True
    assert not p.is_fallback


def test_amc001_deep_merges_over_base():
    p = load_profile("AMC001")
    assert p.amc_code == "AMC001"
    assert not p.is_fallback
    # AMC001-specific severity remap present; base thresholds still inherited
    assert p.severity_overrides.get("S-5") == {"FAIL": "VERIFY"}
    assert p.threshold("SCA-NET.net_adjustment_pct") == 15


def test_unknown_amc_falls_back_to_base_with_hold_flag():
    p = load_profile("AMC_DOES_NOT_EXIST")
    assert p.is_fallback is True
    assert p.amc_code == "_base"


def test_severity_remap_changes_output():
    # SHALqc.md §12 DoD #3: flipping one severity line changes output, no restart.
    verdicts = [Verdict(rule_id="S-5", status=Status.FAIL, section="subject")]
    apply_severity(load_profile("AMC001"), verdicts)
    assert verdicts[0].status == Status.VERIFY   # remapped by AMC001
    assert "profile_remap:VERIFY" in (verdicts[0].degraded_reason or "")

    verdicts2 = [Verdict(rule_id="S-5", status=Status.FAIL, section="subject")]
    apply_severity(load_profile(None), verdicts2)
    assert verdicts2[0].status == Status.FAIL    # base does not remap


def test_active_rules_respects_on_off():
    p = load_profile("AMC001")
    ids = {r.rule_id for r in active_rules(p)}
    assert "S-1" in ids  # default on
