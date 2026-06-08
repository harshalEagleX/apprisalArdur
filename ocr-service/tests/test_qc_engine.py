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


# ---------------------------------------------------------------------------
# SCA adjustment-percentage rules (SCA-GROSS + SCA-NET printed-% path)
# ---------------------------------------------------------------------------

class TestSCAAdjustmentPct:
    def test_pct_helper(self):
        from app.qc.rules.sales_comparison import _pct
        assert _pct("38.6") == 38.6
        assert _pct("14.1 %") == 14.1
        assert _pct(None) is None
        assert _pct("n/a") is None

    def test_gross_over_25_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_gross_adjustment
        from app.qc.result import RuleStatus
        # comp 1 gross 38.6% (> 25 cap) → VERIFY naming comp 1; comps 2/3 within cap.
        ctx = QCContext("t", appraisal=_appraisal(
            comp_1_sale_price="1700000", comp_1_gross_adj_pct="38.6",
            comp_2_sale_price="1700000", comp_2_gross_adj_pct="14.1",
            comp_3_sale_price="1700000", comp_3_gross_adj_pct="17.3"))
        r = sca_gross_adjustment(ctx)
        assert r.status == RuleStatus.VERIFY and "1" in r.message

    def test_gross_all_within_cap_pass(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_gross_adjustment
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            comp_1_sale_price="500000", comp_1_gross_adj_pct="12.0",
            comp_2_sale_price="500000", comp_2_gross_adj_pct="9.5"))
        assert sca_gross_adjustment(ctx).status == RuleStatus.PASS

    def test_gross_skipped_when_unextracted(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_gross_adjustment
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(comp_1_sale_price="500000"))
        assert sca_gross_adjustment(ctx).status == RuleStatus.SKIPPED

    def test_net_prefers_printed_pct(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_net_adjustment
        from app.qc.result import RuleStatus
        # printed net 34.2% (> 15 cap) drives VERIFY even though the dollar net is tiny.
        ctx = QCContext("t", appraisal=_appraisal(
            comp_1_sale_price="1700000", comp_1_net_adjustment="1000", comp_1_net_adj_pct="34.2"))
        r = sca_net_adjustment(ctx)
        assert r.status == RuleStatus.VERIFY and "1" in r.message


# ---------------------------------------------------------------------------
# SCA prior-sale rules (SCA-PSH subject + SCA-FLIP comp resale)
# ---------------------------------------------------------------------------

class TestSCAPriorSale:
    def test_full_date_parse(self):
        from app.qc.rules.sales_comparison import _parse_full_date
        assert _parse_full_date("02/09/2026") == (2026, 2)
        assert _parse_full_date("10/8/24") == (2024, 10)
        assert _parse_full_date("") is None

    def test_subject_prior_within_window_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_subject_prior_sale
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            effective_date="2026-03-15", subject_grid_prior_sale_date="02/09/2026"))
        r = sca_subject_prior_sale(ctx)
        assert r.status == RuleStatus.VERIFY and "1" in r.message  # 1 month

    def test_subject_prior_outside_window_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_subject_prior_sale
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            effective_date="2026-03-15", subject_grid_prior_sale_date="01/01/2020"))
        assert sca_subject_prior_sale(ctx).status == RuleStatus.PASS

    def test_subject_no_prior_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_subject_prior_sale
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(effective_date="2026-03-15"))
        assert sca_subject_prior_sale(ctx).status == RuleStatus.PASS

    def test_subject_prior_skipped_without_effective_date(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_subject_prior_sale
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(subject_grid_prior_sale_date="02/09/2026"))
        assert sca_subject_prior_sale(ctx).status == RuleStatus.SKIPPED

    def test_comp_resale_within_window_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_comp_resale
        from app.qc.result import RuleStatus
        # comp sold s06/25 and had a prior sale 02/2024 → ~16 months → flip flag.
        ctx = QCContext("t", appraisal=_appraisal(
            comp_1_sale_price="400000", comp_1_sale_date="s06/25;c05/25",
            comp_1_prior_sale_date="02/15/2024"))
        rs = sca_comp_resale(ctx)
        assert any(r.status == RuleStatus.VERIFY for r in rs)

    def test_comp_no_resale_one_pass(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca_comp_resale
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(comp_1_sale_price="400000"))
        rs = sca_comp_resale(ctx)
        assert len(rs) == 1 and rs[0].status == RuleStatus.PASS


# ---------------------------------------------------------------------------
# SCA-25 new construction + SCA-26 GLA bracketing
# ---------------------------------------------------------------------------

class TestSCANewConstAndGLA:
    def test_new_construction_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca25_new_construction
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(year_built="2025", effective_date="2026-03-15"))
        assert sca25_new_construction(ctx).status == RuleStatus.VERIFY

    def test_established_not_applicable(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca25_new_construction
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(year_built="1990", effective_date="2026-03-15",
                                                  condition_rating="C3"))
        assert sca25_new_construction(ctx).status == RuleStatus.NOT_APPLICABLE

    def test_gla_bracketed_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca26_gla_bracket
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            gla="2000", comp_1_sale_price="1", comp_1_gla="1800",
            comp_2_sale_price="1", comp_2_gla="2200"))
        assert sca26_gla_bracket(ctx).status == RuleStatus.PASS

    def test_gla_outside_range_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca26_gla_bracket
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            gla="2600", comp_1_sale_price="1", comp_1_gla="1800",
            comp_2_sale_price="1", comp_2_gla="2200"))
        r = sca26_gla_bracket(ctx)
        assert r.status == RuleStatus.VERIFY and "2600" in r.message


# ---------------------------------------------------------------------------
# Vision client + photo rules (SCA-27 / SCA-16V) — pseudo-field driven (P-3)
# ---------------------------------------------------------------------------

class TestVisionClient:
    def test_unavailable_when_disabled(self, monkeypatch):
        # VISION_ENABLED off → no analyzer, no crash, no cost (regardless of keys).
        from app import config
        from app.vision import analyzer_available, get_photo_analyzer
        monkeypatch.setattr(config, "VISION_ENABLED", False)
        assert analyzer_available() is False
        assert get_photo_analyzer() is None

    def test_gemini_backend_selected_when_keyed(self, monkeypatch):
        from app import config
        from app.vision import analyzer_available, get_photo_analyzer
        monkeypatch.setattr(config, "VISION_ENABLED", True)
        monkeypatch.setattr(config, "VISION_BACKEND", "gemini")
        monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
        assert analyzer_available() is True
        a = get_photo_analyzer()
        assert a is not None and a.backend == "gemini"

    def test_gemini_signal_parse(self):
        from app.vision.analyzer import _parse_signals
        s = _parse_signals('{"is_building": true, "mls_watermark": false, '
                            '"distress": false, "condition": "C3"}')
        assert s.building and s.condition == "C3"
        assert s.mls_text is False and s.distress is False

    def test_gemini_signal_parse_unknown_condition(self):
        from app.vision.analyzer import _parse_signals
        s = _parse_signals('{"is_building": true, "distress": true, "condition": "unknown"}')
        assert s.building and s.distress and s.condition is None

    def test_annotation_helpers(self):
        from app.vision import VisionAnnotation
        a = VisionAnnotation(labels=[("House", 0.97), ("Roof", 0.8)], text="MLS #123", objects=["Building"])
        assert a.has_label("house", min_score=0.9)
        assert a.any_label_contains("roof")
        assert not a.any_label_contains("pool")


class TestSCAPhotoRules:
    def _appr(self, **f):
        return _appraisal(**f)

    def test_sca27_no_pages_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca27_comp_photos
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(comp_photo_pages="0"))
        assert sca27_comp_photos(ctx).status == RuleStatus.VERIFY

    def test_sca27_defers_when_vision_off(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca27_comp_photos
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(comp_photo_pages="2", vision_enabled="False"))
        r = sca27_comp_photos(ctx)
        assert r.status == RuleStatus.VERIFY and "2" in r.message

    def test_sca27_passes_with_building_conventional(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca27_comp_photos
        from app.qc.result import RuleStatus
        ctx = QCContext("t",
                        appraisal=self._appr(comp_photo_pages="2", vision_enabled="True",
                                             comp_photo_building="True", comp_photo_mls_text="True"),
                        engagement=_appraisal(loan_type="Conventional"))
        assert sca27_comp_photos(ctx).status == RuleStatus.PASS

    def test_sca27_fha_mls_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca27_comp_photos
        from app.qc.result import RuleStatus
        ctx = QCContext("t",
                        appraisal=self._appr(comp_photo_pages="2", vision_enabled="True",
                                             comp_photo_building="True", comp_photo_mls_text="True"),
                        engagement=_appraisal(loan_type="FHA"))
        assert sca27_comp_photos(ctx).status == RuleStatus.VERIFY

    def test_sca16v_skipped_when_vision_off(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16v_photo_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(vision_enabled="False"))
        assert sca16v_photo_condition(ctx).status == RuleStatus.SKIPPED

    def test_sca16v_distress_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16v_photo_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(vision_enabled="True", comp_photo_distress="True"))
        assert sca16v_photo_condition(ctx).status == RuleStatus.VERIFY

    def test_sca27_defers_on_vision_error(self):
        # A transient vision outage must DEFER (VERIFY), never assert "not a building".
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca27_comp_photos
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(comp_photo_pages="2", vision_enabled="True",
                                                  comp_photo_vision_error="True"))
        assert sca27_comp_photos(ctx).status == RuleStatus.VERIFY

    def test_sca16v_condition_conflict_verifies(self):
        # Photos look C5 but every rated condition is C3 (>=2 grades worse) -> VERIFY.
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16v_photo_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(
            vision_enabled="True", comp_photo_distress="False", comp_photo_condition="C5",
            comp_1_sale_price="1", comp_1_condition_rating="C3", condition_rating="C3"))
        r = sca16v_photo_condition(ctx)
        assert r.status == RuleStatus.VERIFY and "C5" in r.message

    def test_sca16v_condition_consistent_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16v_photo_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(
            vision_enabled="True", comp_photo_distress="False", comp_photo_condition="C3",
            comp_1_sale_price="1", comp_1_condition_rating="C3"))
        assert sca16v_photo_condition(ctx).status == RuleStatus.PASS

    def test_sca16v_skipped_on_vision_error(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16v_photo_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=self._appr(vision_enabled="True", comp_photo_vision_error="True"))
        assert sca16v_photo_condition(ctx).status == RuleStatus.SKIPPED


# ---------------------------------------------------------------------------
# Batch 8 — strengthened SCA rules (zero-adj consistency, specificity, listing, basement)
# ---------------------------------------------------------------------------

class TestSCAStrengthened:
    def test_condition_same_grade_with_adjustment_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            condition_rating="C3", comp_1_sale_price="1",
            comp_1_condition_rating="C3", comp_1_condition_rating_adjustment="5000"))
        assert sca16_condition(ctx)[0].status == RuleStatus.VERIFY

    def test_condition_diff_grade_no_adjustment_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            condition_rating="C3", comp_1_sale_price="1", comp_1_condition_rating="C5"))
        assert sca16_condition(ctx)[0].status == RuleStatus.VERIFY

    def test_condition_consistent_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca16_condition
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            condition_rating="C3", comp_1_sale_price="1", comp_1_condition_rating="C3"))
        assert sca16_condition(ctx)[0].status == RuleStatus.PASS

    def test_quality_diff_with_adjustment_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca14_quality
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(
            quality_rating="Q3", comp_1_sale_price="1",
            comp_1_quality_rating="Q4", comp_1_quality_rating_adjustment="207500"))
        assert sca14_quality(ctx)[0].status == RuleStatus.PASS

    def test_verification_vague_verifies_specific_passes(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca6_verification
        from app.qc.result import RuleStatus
        vague = QCContext("t", appraisal=_appraisal(comp_1_sale_price="1",
                                                    comp_1_verification_source="Public Records"))
        spec = QCContext("t", appraisal=_appraisal(comp_1_sale_price="1",
                                                   comp_1_verification_source="Lake County Assessor"))
        assert sca6_verification(vague)[0].status == RuleStatus.VERIFY
        assert sca6_verification(spec)[0].status == RuleStatus.PASS

    def test_listing_without_adjustment_verifies(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca23_listing_adjustment
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(comp_1_sale_price="1", comp_1_sale_date="Active"))
        assert sca23_listing_adjustment(ctx)[0].status == RuleStatus.VERIFY

    def test_no_listings_not_applicable(self):
        from app.qc.context import QCContext
        from app.qc.rules.sales_comparison import sca23_listing_adjustment
        from app.qc.result import RuleStatus
        ctx = QCContext("t", appraisal=_appraisal(comp_1_sale_price="1", comp_1_sale_date="s06/25;c05/25"))
        assert sca23_listing_adjustment(ctx).status == RuleStatus.NOT_APPLICABLE
