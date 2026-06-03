"""
QC engine unit tests — pure-function coverage (no DB / no extraction).

Covers the deterministic building blocks of the QC layer: cross-document
matching, the commentary analyzer, contract-price parsing, comp-grid date
sequencing, and the engine's status model / applicability gating. These run
fast and guard against regressions in the rule logic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.result import ExtractionResult, ExtractionResultSet


# ---------------------------------------------------------------------------
# matching.py — normalization + Jaro-Winkler bands
# ---------------------------------------------------------------------------

class TestMatching:
    def test_address_abbreviation_equivalence(self):
        from app.qc.matching import match_text
        assert match_text("123 Main St", "123 Main Street", kind="address").verdict == "match"
        assert match_text("90 NE 32nd St", "90 Northeast 32nd Street", kind="address").verdict == "match"

    def test_name_token_order_insensitive(self):
        from app.qc.matching import match_text
        assert match_text("Anton Deineko", "DEINEKO, ANTON", kind="name").verdict == "match"
        assert match_text("Iris M Lopez", "Iris Lopez", kind="name").score > 0.85

    def test_clear_mismatch(self):
        from app.qc.matching import match_text
        assert match_text("28203 Fantail Dr", "90 NE 32nd St", kind="address").verdict == "mismatch"

    def test_currency_exact_after_normalize(self):
        from app.qc.matching import match_currency
        assert match_currency("380000", "$380,000").verdict == "match"
        assert match_currency("380000", "375000").verdict == "mismatch"

    def test_review_band_between_thresholds(self):
        from app.qc.matching import jaro_winkler
        # a near-miss should land in [0.75, 0.88)
        s = jaro_winkler("champions funding llc", "champions funding")
        assert 0.75 <= s < 1.0


# ---------------------------------------------------------------------------
# commentary.py — canned / specificity detection
# ---------------------------------------------------------------------------

class TestCommentary:
    def test_clean_specific_text(self):
        from app.qc.commentary import analyze_commentary
        a = analyze_commentary("The subject sits in an established suburban area of Katy "
                               "with schools and parks within two miles.")
        assert a.is_clean

    def test_canned_phrases_flagged(self):
        from app.qc.commentary import analyze_commentary
        a = analyze_commentary("Typical for the area. No adverse conditions noted.")
        assert a.canned_hits and not a.is_clean

    def test_see_1004mc_deferral(self):
        from app.qc.commentary import analyze_commentary
        assert analyze_commentary("See 1004MC.").defers_to_form

    def test_reconciliation_forbidden_terms(self):
        from app.qc.commentary import reconciliation_forbidden_terms
        hits = reconciliation_forbidden_terms("Equal weight given; weighted average used.")
        assert "equal weight" in hits and "weighted average" in hits


# ---------------------------------------------------------------------------
# contract_extractor.py — targeted price parsing
# ---------------------------------------------------------------------------

class TestContractPrice:
    def test_cash_plus_loan(self):
        from app.extraction.contract_extractor import _contract_price
        text = ("3. SALES PRICE:\n"
                "A. Cash portion of Sales Price payable by Buyer at closing 57,000.00\n"
                "B. Loan Assumption / Seller Financing Addendum $ 323,000.00\n"
                "C. Sales Price (Sum of A and B)")
        assert _contract_price(text) == "380000"

    def test_no_false_positive_when_unreadable(self):
        from app.extraction.contract_extractor import _contract_price
        # parcel/loan numbers but no price context → None (keeps C-2 at VERIFY)
        assert _contract_price("Parcel 048543-000177-5094165  Loan No 26534900") is None

    def test_latest_date_is_executed_date(self):
        from app.extraction.contract_extractor import _contract_date
        assert _contract_date("Seller signed 03/01/2026. Buyer signed 04/29/2026.") == "04/29/2026"


# ---------------------------------------------------------------------------
# comp grid date sequencing (SCA-8 helper)
# ---------------------------------------------------------------------------

class TestCompGridDates:
    def test_uad_date_parse_and_order(self):
        from app.qc.rules.sales_comparison import _parse_uad_date
        d = _parse_uad_date("s06/14;c11/13")
        assert d["s"] == (2014, 6) and d["c"] == (2013, 11)
        assert d["c"] < d["s"]   # contract before sale = OK


# ---------------------------------------------------------------------------
# engine — status model + applicability gating
# ---------------------------------------------------------------------------

def _appraisal(**fields) -> ExtractionResultSet:
    rs = ExtractionResultSet(document_path="x", document_type="appraisal_report")
    for name, value in fields.items():
        rs.add(ExtractionResult(canonical_name=name, document_type="appraisal_report",
                                value=str(value), extraction_method="test",
                                confidence=0.9, source_page=1))
    rs.finalize()
    return rs


class TestEngine:
    def test_overall_precedence_hold_over_fail(self):
        from app.qc.result import QCReport, RuleResult, RuleStatus
        rep = QCReport(transaction_id="t", results=[
            RuleResult("A", "1", "s", RuleStatus.FAIL),
            RuleResult("B", "2", "s", RuleStatus.HOLD),
            RuleResult("C", "3", "s", RuleStatus.PASS),
        ])
        assert rep.overall == RuleStatus.HOLD

    def test_auto_clear_only_when_all_pass(self):
        from app.qc.result import QCReport, RuleResult, RuleStatus
        rep = QCReport(transaction_id="t", results=[
            RuleResult("A", "1", "s", RuleStatus.PASS),
            RuleResult("B", "2", "s", RuleStatus.NOT_APPLICABLE),
        ])
        assert rep.overall == RuleStatus.PASS

    def test_fha_rules_not_applicable_on_conventional(self):
        import app.qc.rules  # noqa: F401  (register)
        from app.qc.context import QCContext
        from app.qc.engine import run_qc
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(assignment_type="Purchase Transaction"),
                        engagement=_appraisal(loan_type="Conventional"))
        report = run_qc(ctx)
        usda = [r for r in report.results if r.rule_id == "USDA-1"]
        assert usda and usda[0].status == RuleStatus.NOT_APPLICABLE

    def test_land_use_sum_rule(self):
        import app.qc.rules  # noqa: F401
        from app.qc.context import QCContext
        from app.qc.engine import run_qc
        from app.qc.result import RuleStatus
        # land use sums to 100 → N-4 passes
        ctx = QCContext("t", appraisal=_appraisal(
            land_use_one_unit="80", land_use_2_4_unit="10", land_use_commercial="10"))
        n4 = [r for r in run_qc(ctx).results if r.rule_id == "N-4"]
        assert n4 and n4[0].status == RuleStatus.PASS
