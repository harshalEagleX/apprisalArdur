"""Regression tests for signature-page rules.

SIG-CO (checklist 97 & 98) — the appraiser's company NAME and ADDRESS must be
present in the signature block. Both present → two PASS rows; a missing field →
VERIFY (not FAIL: the address is read positionally from the PDF and can be
missed, so we ask a human rather than hard-reject a value we may not have read).
"""
from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc.context import QCContext
from app.qc.result import RuleResult, RuleStatus
from app.qc.rules.signature import sig_company


def _ctx(**fields) -> QCContext:
    rs = ExtractionResultSet(document_path="t.pdf", document_type="appraisal_report")
    for name, val in fields.items():
        rs.add(ExtractionResult(
            canonical_name=name, document_type="appraisal_report",
            value=val, confidence=0.9, extraction_method="xml_parser", source_page=12))
    return QCContext(transaction_id="t", appraisal=rs)


def _by_num(out):
    return {r.checklist_num: r.status for r in out if isinstance(r, RuleResult)}


def test_sig_co_all_present_pass():
    out = sig_company(_ctx(appraiser_company_name="MCA Inc.",
                           appraiser_company_address="10219 Silver Leaf Lane, Tomball, TX 77375",
                           appraiser_phone="(281) 205-7010"))
    assert _by_num(out) == {"97": RuleStatus.PASS, "98": RuleStatus.PASS, "99": RuleStatus.PASS}


def test_sig_co_missing_address_verifies_only_address():
    out = sig_company(_ctx(appraiser_company_name="MCA Inc.", appraiser_phone="(281) 205-7010"))
    st = _by_num(out)
    assert st["97"] == RuleStatus.PASS          # name present
    assert st["98"] == RuleStatus.VERIFY         # address absent → VERIFY, not FAIL
    assert st["99"] == RuleStatus.PASS          # phone present


def test_sig_co_all_missing_verifies_each():
    out = sig_company(_ctx())
    assert _by_num(out) == {"97": RuleStatus.VERIFY, "98": RuleStatus.VERIFY, "99": RuleStatus.VERIFY}
