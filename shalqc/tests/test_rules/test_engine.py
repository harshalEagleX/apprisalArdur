"""
Rule engine tests (rul-1.0.0) — SHALqc.md §5 needs[] gating + tier behavior.

Built on synthetic ExtractedFieldSets (no fixture PDF needed) so the gate/tier
guarantees are proven in isolation, plus one end-to-end check against the
ESTX-0007568 fixture through the orchestrator.
"""

from pathlib import Path

import pytest

import app.rules  # registers rules as a side effect
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.rules.registry import all_rules
from app.rules.verdict import Status

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "ESTX-0007568"


def _fs(**fields) -> ExtractedFieldSet:
    fs = ExtractedFieldSet()
    for name, (value, conf) in fields.items():
        fs.add(ExtractedField(canonical_name=name, value=value, raw_value=value,
                              source=Source.XML, confidence=conf, page=1))
    return fs


def _ctx(appraisal=None, engagement=None):
    return QCContext(order_id="T", appraisal=appraisal, engagement=engagement)


def _by_id(verdicts):
    return {v.rule_id: v for v in verdicts}


def test_rules_registered():
    ids = {r.rule_id for r in all_rules()}
    assert {"S-1", "S-2", "S-10a", "ST-5", "C-1", "N-CANNED"} <= ids


def test_cross_doc_match_passes_after_normalization():
    ctx = _ctx(
        appraisal=_fs(property_address=("7243 Foxtail Meadow Ct", 0.97)),
        engagement=_fs(property_address=("7243 Foxtail Mdw Ct", 0.92)),
    )
    v = _by_id(run_rules(ctx))["S-1"]
    assert v.status == Status.PASS  # normalizer resolves Mdw==Meadow


def test_missing_needed_field_verifies_never_fails():
    # engagement present but city missing → the significance resolver decides
    # (never a FAIL — §3.3/P4). city is critical + engagement-sourced, so the
    # resolution is a reviewer VERIFY_MISSING, not the old blanket missing_field.
    ctx = _ctx(appraisal=_fs(city=("Humble", 0.97)), engagement=_fs())
    v = _by_id(run_rules(ctx))["S-1b"]
    assert v.status == Status.VERIFY
    assert v.degraded_reason in ("verify_missing", "extraction_gap")
    assert v.actionable_by in ("appraiser", "engine")


def test_absent_document_makes_cross_doc_rule_not_applicable():
    # no engagement doc at all → S-1 cannot compare → NOT_APPLICABLE
    ctx = _ctx(appraisal=_fs(property_address=("7243 Foxtail Meadow Ct", 0.97)), engagement=None)
    v = _by_id(run_rules(ctx))["S-1"]
    assert v.status == Status.NOT_APPLICABLE


def test_low_confidence_input_cannot_fail():
    # values genuinely differ, but the appraisal read is below review_conf →
    # the gate degrades to VERIFY before the body can FAIL (P4 structural guard)
    ctx = _ctx(
        appraisal=_fs(city=("Dallas", 0.40)),
        engagement=_fs(city=("Humble", 0.92)),
    )
    v = _by_id(run_rules(ctx))["S-1b"]
    assert v.status == Status.VERIFY
    assert v.degraded_reason == "low_confidence_input"


def test_tier2_degrades_to_verify_without_llm_client():
    ctx = _ctx(appraisal=_fs(neighborhood_description=("Some real commentary here.", 0.9)))
    v = _by_id(run_rules(ctx, llm_client=None))["N-CANNED"]
    assert v.status == Status.VERIFY
    assert v.degraded_reason == "llm_unavailable"


def test_genuine_mismatch_fails_at_high_confidence():
    ctx = _ctx(
        appraisal=_fs(city=("Dallas", 0.97)),
        engagement=_fs(city=("Humble", 0.92)),
    )
    v = _by_id(run_rules(ctx))["S-1b"]
    assert v.status == Status.FAIL


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="fixture not present")
def test_end_to_end_orchestrator_on_fixture():
    # run_qc now returns the reviewer report (report.builder shape). The rule-
    # level status assertions live in the synthetic tests above; here we assert
    # the whole-order outcome: §4 normalization + §8 plausibility yield NO false
    # FAIL, and the report carries its version fingerprint (§12 DoD #5).
    from app.pipeline.orchestrator import run_qc
    # Validates the deterministic LEGACY rule engine; judge_mode now defaults to
    # "language" (the product path), so pin legacy for this rule-level assertion.
    # persist=False avoids a G-3 cache hit from a prior language-mode run (the cache
    # keys on package hash, not mode).
    rep = run_qc(FIXTURE_DIR, mode="legacy", persist=False)
    assert rep["status"] == "OK"
    assert rep["summary"]["failed"] == 0
    assert "components" in rep["versions"]
    # every card is a real exception (FAIL/HOLD/VERIFY), never a PASS
    assert all(c["status"] in ("FAIL", "HOLD", "VERIFY") for c in rep["cards"])
