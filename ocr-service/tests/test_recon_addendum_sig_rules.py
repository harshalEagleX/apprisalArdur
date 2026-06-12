"""
Reconciliation / Cost / Income / Addendum / Signature / FHA rule upgrades —
unit coverage for the MIRA-spec batch: R-1 range, R-1b weight keywords, R-2b
bias advisory, CA-3 arithmetic + depreciation baseline, IA-1 rent match, MF-1
gate, ADD-5/8/9 content checks, SIG-D gap, DOC-1 expiry, SIG-SUP, FHA-5,
USDA-1 per-field.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc.context import QCContext
from app.qc.result import RuleStatus


def _rs(doc_type="appraisal_report", **fields) -> ExtractionResultSet:
    rs = ExtractionResultSet(document_path="x", document_type=doc_type)
    for name, value in fields.items():
        rs.add(ExtractionResult(canonical_name=name, document_type=doc_type,
                                value=str(value), extraction_method="test",
                                confidence=0.9, source_page=1))
    rs.finalize()
    return rs


def _list(results):
    return results if isinstance(results, list) else [results]


def _by_template(results, template_id):
    return [r for r in _list(results) if r.template_id == template_id]


class TestR1:
    def test_final_within_multi_approach_range(self):
        from app.qc.rules.reconciliation import r1_value_match
        ctx = QCContext("t", appraisal=_rs(indicated_value_sca="380000",
                                           indicated_value_cost_approach="395000",
                                           appraised_value="385000"))
        assert _list(r1_value_match(ctx))[0].status == RuleStatus.PASS

    def test_final_outside_multi_approach_range(self):
        from app.qc.rules.reconciliation import r1_value_match
        ctx = QCContext("t", appraisal=_rs(indicated_value_sca="380000",
                                           indicated_value_cost_approach="395000",
                                           appraised_value="420000"))
        assert _by_template(r1_value_match(ctx), "R-1-range")

    def test_sca_only_exact_match_kept(self):
        from app.qc.rules.reconciliation import r1_value_match
        ctx = QCContext("t", appraisal=_rs(indicated_value_sca="381000",
                                           appraised_value="381000"))
        assert _list(r1_value_match(ctx))[0].status == RuleStatus.PASS


class TestR1bR2b:
    def test_weight_keywords_pass(self):
        from app.qc.rules.reconciliation import r1b_weight
        ctx = QCContext("t", appraisal=_rs(
            final_reconciliation_comment="The sales comparison approach was given the most "
                                         "weight as it best reflects current market behavior."))
        assert r1b_weight(ctx).status == RuleStatus.PASS

    def test_bias_flag_when_value_equals_price(self):
        from app.qc.rules.reconciliation import r2b_bias
        ctx = QCContext("t", appraisal=_rs(assignment_type="Purchase",
                                           appraised_value="380000",
                                           contract_price="380000"))
        r = r2b_bias(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "R-2-bias"

    def test_no_bias_flag_when_different(self):
        from app.qc.rules.reconciliation import r2b_bias
        ctx = QCContext("t", appraisal=_rs(assignment_type="Purchase",
                                           appraised_value="385000",
                                           contract_price="380000"))
        assert r2b_bias(ctx).status == RuleStatus.PASS


class TestCA3:
    def test_arithmetic_holds(self):
        from app.qc.rules.reconciliation import ca3_arithmetic
        ctx = QCContext("t", appraisal=_rs(site_value_estimate="80000",
                                           depreciated_cost_improvements="310000",
                                           indicated_value_cost_approach="390000",
                                           cost_new_improvements="340000"))
        assert RuleStatus.PASS in [r.status for r in ca3_arithmetic(ctx)]

    def test_arithmetic_breaks_fails(self):
        from app.qc.rules.reconciliation import ca3_arithmetic
        ctx = QCContext("t", appraisal=_rs(site_value_estimate="80000",
                                           depreciated_cost_improvements="310000",
                                           indicated_value_cost_approach="420000",
                                           cost_new_improvements="340000"))
        hits = _by_template(ca3_arithmetic(ctx), "CA-3-arith")
        assert hits and hits[0].status == RuleStatus.FAIL

    def test_depreciation_far_from_age_life_verifies(self):
        from app.qc.rules.reconciliation import ca3_arithmetic
        # eff age 10 / REL 50 → expected ~16.7%; stated 50% → flag
        ctx = QCContext("t", appraisal=_rs(cost_new_improvements="340000",
                                           total_depreciation="170000",
                                           effective_age="10",
                                           remaining_economic_life="50"))
        assert _by_template(ca3_arithmetic(ctx), "CA-3-depr")


class TestIA1MF1:
    def test_rent_mismatch_fails(self):
        from app.qc.rules.reconciliation import ia1_rent_match
        ctx = QCContext("t", appraisal=_rs(income_approach_monthly_rent="2500",
                                           indicated_monthly_market_rent="2800"))
        assert ia1_rent_match(ctx).status == RuleStatus.FAIL

    def test_rent_within_tolerance_passes(self):
        from app.qc.rules.reconciliation import ia1_rent_match
        ctx = QCContext("t", appraisal=_rs(income_approach_monthly_rent="2500",
                                           indicated_monthly_market_rent="2503"))
        assert ia1_rent_match(ctx).status == RuleStatus.PASS

    def test_not_developed_is_na(self):
        from app.qc.rules.reconciliation import ia1_rent_match
        ctx = QCContext("t", appraisal=_rs(other="x"))
        assert ia1_rent_match(ctx).status == RuleStatus.NOT_APPLICABLE

    def test_multi_unit_without_income_verifies(self):
        from app.qc.rules.reconciliation import _is_multi_unit, mf1_income_required
        ctx = QCContext("t", appraisal=_rs(units_count="3"))
        assert _is_multi_unit(ctx)
        assert mf1_income_required(ctx).status == RuleStatus.VERIFY


class TestAddendum:
    def test_mca_partial_fields_verify(self):
        from app.qc.rules.addendum import add5_mca_fields
        ctx = QCContext("t", appraisal=_rs(mca_total_sales_current_3="12"))
        r = add5_mca_fields(ctx)
        assert r.status == RuleStatus.VERIFY and "Absorption" in r.message

    def test_uspap_specific_exposure_passes(self):
        from app.qc.rules.addendum import add9_uspap
        ctx = QCContext("t", appraisal=_rs(appraisal_report_type="Appraisal Report",
                                           reasonable_exposure_time="30-90 days"))
        assert all(r.status == RuleStatus.PASS for r in add9_uspap(ctx))

    def test_uspap_vague_exposure_verifies(self):
        from app.qc.rules.addendum import add9_uspap
        ctx = QCContext("t", appraisal=_rs(appraisal_report_type="Appraisal Report",
                                           reasonable_exposure_time="typical for the market"))
        assert _by_template(add9_uspap(ctx), "ADD-9-exposure")

    def test_selection_why_keywords_pass(self):
        from app.qc.rules.addendum import add2_selection
        ctx = QCContext("t", appraisal=_rs(
            sales_comparison_summary="The comparables were selected because they are the most "
                                     "similar to the subject and share the same buyer pool."))
        assert add2_selection(ctx).status == RuleStatus.PASS


class TestSignature:
    def test_signature_long_after_effective_verifies(self):
        from app.qc.rules.signature import sig_date_sequence
        ctx = QCContext("t", appraisal=_rs(date_of_signature="06/01/2026",
                                           effective_date="03/15/2026"))
        r = sig_date_sequence(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "SIG-1-gap"

    def test_signature_normal_gap_passes(self):
        from app.qc.rules.signature import sig_date_sequence
        ctx = QCContext("t", appraisal=_rs(date_of_signature="03/20/2026",
                                           effective_date="03/15/2026"))
        assert sig_date_sequence(ctx).status == RuleStatus.PASS

    def test_expired_license_fails(self):
        from app.qc.rules.signature import doc1_license_current
        ctx = QCContext("t", appraisal=_rs(appraiser_cert_expiration_date="01/31/2026",
                                           date_of_signature="03/20/2026"))
        assert doc1_license_current(ctx).status == RuleStatus.FAIL

    def test_current_license_passes(self):
        from app.qc.rules.signature import doc1_license_current
        ctx = QCContext("t", appraisal=_rs(appraiser_cert_expiration_date="12/31/2026",
                                           date_of_signature="03/20/2026"))
        assert doc1_license_current(ctx).status == RuleStatus.PASS

    def test_supervisor_without_inspect_mark_verifies(self):
        from app.qc.rules.signature import sig_supervisor
        ctx = QCContext("t", appraisal=_rs(supervisory_appraiser_name="Jane Doe"))
        assert sig_supervisor(ctx).status == RuleStatus.VERIFY


class TestFHAUSDA:
    def test_fha5_old_primary_comp_fails(self):
        from app.qc.rules.fha_usda import fha5_comp_dates
        ctx = QCContext("t", appraisal=_rs(effective_date="03/15/2026",
                                           comp_1_sale_date="s03/24",
                                           comp_2_sale_date="s01/26"))
        results = fha5_comp_dates(ctx)
        by_field = {r.fields_involved[0]: r.status for r in results}
        assert by_field["comp_1_sale_date"] == RuleStatus.FAIL
        assert by_field["comp_2_sale_date"] == RuleStatus.PASS

    def test_usda_partial_cost_names_fields(self):
        from app.qc.rules.fha_usda import usda1_cost
        ctx = QCContext("t", appraisal=_rs(site_value_estimate="80000",
                                           cost_new_improvements="340000"))
        r = usda1_cost(ctx)
        assert r.status == RuleStatus.FAIL and "Depreciation" in r.message


class TestAdd9Collapse:
    def test_fully_unextracted_uspap_single_verify(self):
        from app.qc.rules.addendum import add9_uspap
        ctx = QCContext("t", appraisal=_rs(other="x"))
        r = add9_uspap(ctx)
        assert not isinstance(r, list) and r.status == RuleStatus.VERIFY
