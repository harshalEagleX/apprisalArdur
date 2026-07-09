"""
Tests for the engine's absence-claim safety guard (_guard_absence_claims).

The guard is the QC-audit hardening for "required content is missing" findings —
the class of false positive that dominated the 445 Sparrow Way audit. Two failure
modes are covered:

  * self-contradiction — a finding that declares content missing while citing the
    content as evidence (real example: rule C-4, "concessions not stated" + the
    concession text quoted in the same finding).
  * thin evidence — an absence claim whose only support is a low-confidence read
    (an extraction gap, not an appraiser omission).

These tests use synthetic RuleResults shaped exactly like the ones the engine
emits, so they pin the guard's behavior without needing the full pipeline.
"""

from app.qc.engine import _guard_absence_claims
from app.qc.result import Evidence, QCReport, RuleResult, RuleStatus


def _report(*results: RuleResult) -> QCReport:
    r = QCReport(transaction_id="test")
    r.results.extend(results)
    return r


def test_self_contradiction_fail_downgraded_and_tagged():
    """A FAIL that says 'not stated' but cites the content is downgraded + tagged."""
    finding = RuleResult(
        rule_id="C-4", checklist_num="", section="contract", status=RuleStatus.FAIL,
        message="Seller concessions / financial assistance not stated in the report.",
        evidence=[Evidence(document="appraisal",
                            value="Seller to compensate Buyer's Broker credits 2.5% of price",
                            confidence=0.82)],
        confidence=0.8, finding_type="hard_fail",
    )
    _guard_absence_claims(_report(finding))
    assert finding.status == RuleStatus.VERIFY
    assert finding.finding_type == "rule_self_conflict"
    assert finding.confidence <= 0.4
    assert "auto-guard" in (finding.reasoning or "")


def test_thin_evidence_absence_tagged_extraction_gap():
    """An absence claim resting on a low-confidence read is tagged extraction_failed."""
    finding = RuleResult(
        rule_id="R-EXPOSURE", checklist_num="", section="reconciliation",
        status=RuleStatus.FAIL,
        message="No specific exposure time period was found. Please add a statement.",
        evidence=[Evidence(document="appraisal", value="(USPAP defines", confidence=0.4)],
        confidence=0.7, finding_type="hard_fail",
    )
    _guard_absence_claims(_report(finding))
    assert finding.status == RuleStatus.VERIFY
    assert finding.finding_type == "extraction_failed"


def test_short_code_evidence_does_not_rebut():
    """A lone code (AsIs, Q4) must NOT trip the self-contradiction branch."""
    finding = RuleResult(
        rule_id="X-1", checklist_num="", section="site", status=RuleStatus.FAIL,
        message="Scope of work statement was not found.",
        evidence=[Evidence(document="appraisal", value="AsIs", confidence=0.97)],
        confidence=0.9, finding_type="hard_fail",
    )
    _guard_absence_claims(_report(finding))
    # High-confidence short token → neither self-conflict nor thin-evidence:
    # left untouched for the rule/extraction-layer fix, not silently downgraded.
    assert finding.status == RuleStatus.FAIL
    assert finding.finding_type == "hard_fail"


def test_non_absence_finding_untouched():
    """A finding with no absence language is never reclassified by the guard."""
    finding = RuleResult(
        rule_id="SCA-14", checklist_num="", section="sales_comparison",
        status=RuleStatus.VERIFY,
        message="Comp 1's quality (Q4) matches the subject, but a $-100000 adjustment "
                "was still applied. Please confirm this adjustment is warranted.",
        evidence=[Evidence(document="appraisal", value="Q4", confidence=0.88)],
        confidence=0.7, finding_type="manual_verify",
    )
    _guard_absence_claims(_report(finding))
    assert finding.status == RuleStatus.VERIFY
    assert finding.finding_type == "manual_verify"


def test_pass_finding_ignored():
    """PASS findings are outside the guard's scope."""
    finding = RuleResult(
        rule_id="N-6", checklist_num="", section="neighborhood", status=RuleStatus.PASS,
        message="", evidence=[], confidence=1.0,
    )
    _guard_absence_claims(_report(finding))
    assert finding.status == RuleStatus.PASS
