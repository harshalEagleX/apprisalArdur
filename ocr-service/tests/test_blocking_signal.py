"""Explicit blocking signal in the Python QC response (remediation E1).

The engine must emit `blocking` / `blocking_rules` derived from HOLD rules, so the
blocking contract is computed at the source of truth — not re-derived from the
verify count in the reviewer UI. Verifies HOLD → blocking True (and names the
rule), and no HOLD → blocking False.
"""

from app.qc.context import QCContext
from app.qc.result import QCReport, RuleResult, RuleStatus
from app.qc.python_response import report_to_python_qc_response


def _resp(*statuses):
    results = [
        RuleResult(rule_id=f"R-{i}", checklist_num=str(i), section="global", status=s)
        for i, s in enumerate(statuses)
    ]
    report = QCReport(transaction_id="t", results=results)
    return report_to_python_qc_response(report, QCContext("t"))


def test_hold_rule_sets_blocking_and_names_the_rule():
    resp = _resp(RuleStatus.PASS, RuleStatus.VERIFY, RuleStatus.HOLD)
    assert resp["blocking"] is True
    assert "R-2" in resp["blocking_rules"]


def test_no_hold_is_not_blocking():
    resp = _resp(RuleStatus.PASS, RuleStatus.VERIFY, RuleStatus.FAIL)
    assert resp["blocking"] is False
    assert resp["blocking_rules"] == []


def test_multiple_holds_all_listed():
    resp = _resp(RuleStatus.HOLD, RuleStatus.PASS, RuleStatus.HOLD)
    assert resp["blocking"] is True
    assert set(resp["blocking_rules"]) == {"R-0", "R-2"}
