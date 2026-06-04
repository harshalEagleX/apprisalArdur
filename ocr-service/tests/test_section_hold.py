"""Section-level HOLD escalation (>2 FAILs in a section => systematic HOLD)."""

from app.qc.engine import _escalate_sections
from app.qc.result import QCReport, RuleResult, RuleStatus


def _fail(rid, section):
    return RuleResult(rule_id=rid, checklist_num="", section=section, status=RuleStatus.FAIL,
                      message="x")


def test_three_fails_escalates_to_hold():
    rep = QCReport(transaction_id="t")
    rep.results += [_fail("SCA-A", "sales_comparison"), _fail("SCA-B", "sales_comparison"),
                    _fail("SCA-C", "sales_comparison")]
    _escalate_sections(rep)
    holds = [r for r in rep.results if r.status == RuleStatus.HOLD]
    assert len(holds) == 1 and holds[0].section == "sales_comparison"


def test_two_fails_no_hold():
    rep = QCReport(transaction_id="t")
    rep.results += [_fail("SCA-A", "sales_comparison"), _fail("SCA-B", "sales_comparison")]
    _escalate_sections(rep)
    assert not any(r.status == RuleStatus.HOLD for r in rep.results)


def test_fails_spread_across_sections_no_hold():
    rep = QCReport(transaction_id="t")
    rep.results += [_fail("A", "subject"), _fail("B", "site"), _fail("C", "signature")]
    _escalate_sections(rep)
    assert not any(r.status == RuleStatus.HOLD for r in rep.results)
