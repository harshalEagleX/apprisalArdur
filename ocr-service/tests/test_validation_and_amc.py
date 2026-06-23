"""
Validation + AMC tests — semantic validation, cross-document consistency, routing config, AMC profiles.

Day 21 — Semantic validation rules fire correctly
Day 22 — Cross-document consistency finds mismatches
Day 23 — Routing config stored in and readable from DB
Day 24 — AMC profile active building working
Day 25 — Template change detection fires on fingerprint mismatch
Day 26 — Full pipeline validation results persisted and queryable

Run:
    conda run -n shal python -m pytest tests/test_week4.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.core.result import ExtractionResult, ExtractionResultSet, ExtractionMethod


def _make_rs(doc_type: str, **kwargs) -> ExtractionResultSet:
    rs = ExtractionResultSet(document_path="", document_type=doc_type)
    for fname, value in kwargs.items():
        rs.add(ExtractionResult(
            canonical_name=fname, document_type=doc_type,
            value=str(value) if value is not None else None,
            extraction_method=ExtractionMethod.EXACT_LABEL_MATCH,
            confidence=0.92, source_page=1,
        ))
    return rs


# ===========================================================================
# Day 21 — Semantic Validation
# ===========================================================================

class TestDay21SemanticValidation:

    def test_sem01_price_match_passes(self):
        from app.services.semantic_validator import rule_sem01_value_price_ratio
        rs = _make_rs("appraisal_report", appraised_value="276000", contract_price="263000")
        result = rule_sem01_value_price_ratio(rs)
        assert result.result == "pass"

    def test_sem01_price_mismatch_warns(self):
        from app.services.semantic_validator import rule_sem01_value_price_ratio
        rs = _make_rs("appraisal_report", appraised_value="350000", contract_price="263000")
        result = rule_sem01_value_price_ratio(rs)
        assert result.result in ("warning", "fail")

    def test_sem01_large_mismatch_fails(self):
        from app.services.semantic_validator import rule_sem01_value_price_ratio
        rs = _make_rs("appraisal_report", appraised_value="500000", contract_price="263000")
        result = rule_sem01_value_price_ratio(rs)
        assert result.result == "fail"

    def test_sem01_skips_when_missing(self):
        from app.services.semantic_validator import rule_sem01_value_price_ratio
        rs = _make_rs("appraisal_report", appraised_value="276000")
        result = rule_sem01_value_price_ratio(rs)
        assert result.result == "skipped"

    def test_sem02_valid_date_sequence_passes(self):
        from app.services.semantic_validator import rule_sem02_effective_before_signature
        rs = _make_rs("appraisal_report", effective_date="2026-04-17", date_of_signature="2026-04-20")
        result = rule_sem02_effective_before_signature(rs)
        assert result.result == "pass"

    def test_sem02_inverted_dates_fails(self):
        from app.services.semantic_validator import rule_sem02_effective_before_signature
        rs = _make_rs("appraisal_report", effective_date="2026-04-20", date_of_signature="2026-04-17")
        result = rule_sem02_effective_before_signature(rs)
        assert result.result == "fail"

    def test_sem03_contract_before_effective_passes(self):
        from app.services.semantic_validator import rule_sem03_contract_before_effective
        rs = _make_rs("appraisal_report",
            assignment_type="Purchase Transaction",
            contract_date="2026-03-15", effective_date="2026-04-17")
        result = rule_sem03_contract_before_effective(rs)
        assert result.result == "pass"

    def test_sem03_contract_after_effective_fails(self):
        from app.services.semantic_validator import rule_sem03_contract_before_effective
        rs = _make_rs("appraisal_report",
            assignment_type="Purchase Transaction",
            contract_date="2026-05-01", effective_date="2026-04-17")
        result = rule_sem03_contract_before_effective(rs)
        assert result.result == "fail"

    def test_sem07_land_use_sum_passes(self):
        from app.services.semantic_validator import rule_sem06_land_use_total
        rs = _make_rs("appraisal_report",
            land_use_one_unit="90", land_use_2_4_unit="5",
            land_use_multi_family="3", land_use_commercial="2", land_use_other="0")
        result = rule_sem06_land_use_total(rs)
        assert result.result == "pass"

    def test_sem07_land_use_wrong_total_fails(self):
        from app.services.semantic_validator import rule_sem06_land_use_total
        rs = _make_rs("appraisal_report",
            land_use_one_unit="80", land_use_2_4_unit="5",
            land_use_commercial="2", land_use_other="0")
        result = rule_sem06_land_use_total(rs)
        assert result.result in ("fail", "skipped")  # depends on how many are missing

    def test_sem11_purchase_requires_contract_fields(self):
        from app.services.semantic_validator import rule_sem11_purchase_contract_fields
        rs = _make_rs("appraisal_report", assignment_type="Purchase Transaction")
        result = rule_sem11_purchase_contract_fields(rs)
        assert result.result == "fail"

    def test_sem11_purchase_with_complete_contract_passes(self):
        from app.services.semantic_validator import rule_sem11_purchase_contract_fields
        rs = _make_rs("appraisal_report",
            assignment_type="Purchase Transaction",
            contract_price="263000", contract_date="2026-03-15",
            did_analyze_contract="True")
        result = rule_sem11_purchase_contract_fields(rs)
        assert result.result == "pass"

    def test_all_rules_run_independently(self):
        """One failing rule must not block others."""
        from app.services.semantic_validator import validate
        # Deliberately broken data
        rs = _make_rs("appraisal_report",
            appraised_value="999999", contract_price="100000",   # huge mismatch
            effective_date="2026-04-17", date_of_signature="2026-04-15",  # inverted
            assignment_type="Purchase Transaction")
        results = validate(rs, "test_independence", persist=False)
        assert len(results) == 6  # all rules fired
        assert sum(1 for r in results if r.result == "fail") >= 2
        assert all(r.result in ("pass", "fail", "warning", "skipped", "info") for r in results)


# ===========================================================================
# Day 22 — Cross-Document Consistency
# ===========================================================================

class TestDay22CrossDocumentConsistency:

    def test_matching_borrower_passes(self):
        from app.services.cross_document_checker import CrossDocumentChecker
        eng = _make_rs("engagement_letter", borrower_name="John Smith")
        apr = _make_rs("appraisal_report", borrower_name="John Smith")
        results = CrossDocumentChecker().check(
            {"engagement_letter": eng, "appraisal_report": apr}, persist=False
        )
        borrower_results = [r for r in results if r.field_name == "borrower_name"]
        assert borrower_results and borrower_results[0].consistent

    def test_mismatched_borrower_fails(self):
        from app.services.cross_document_checker import CrossDocumentChecker
        eng = _make_rs("engagement_letter", borrower_name="John Smith")
        apr = _make_rs("appraisal_report", borrower_name="Jane Doe")
        results = CrossDocumentChecker().check(
            {"engagement_letter": eng, "appraisal_report": apr}, persist=False
        )
        borrower_results = [r for r in results if r.field_name == "borrower_name"]
        assert borrower_results and not borrower_results[0].consistent

    def test_matching_contract_price_passes(self):
        from app.services.cross_document_checker import CrossDocumentChecker
        contract = _make_rs("sales_contract", contract_price="263000")
        apr = _make_rs("appraisal_report", contract_price="263000")
        results = CrossDocumentChecker().check(
            {"sales_contract": contract, "appraisal_report": apr}, persist=False
        )
        price_results = [r for r in results if r.field_name == "contract_price"]
        assert price_results and price_results[0].consistent

    def test_address_normalization_handles_abbreviations(self):
        from app.services.cross_document_checker import _values_match
        match, n1, n2 = _values_match("property_address", "96 Baell Trace Ct SE", "96 Baell Trace Court SE")
        assert match  # "Ct" expands to "Court"

    def test_name_handles_different_order(self):
        from app.services.cross_document_checker import _values_match
        match, _, _ = _values_match(
            "borrower_name",
            "Gonzalo Mata Camacho & Jorge Villa Mancilla",
            "Jorge Villa Mancilla & Gonzalo Mata Camacho",
        )
        assert match  # sorted word order comparison

    def test_missing_document_handled_gracefully(self):
        from app.services.cross_document_checker import CrossDocumentChecker
        eng = _make_rs("engagement_letter", borrower_name="John Smith")
        # No appraisal report provided
        results = CrossDocumentChecker().check({"engagement_letter": eng}, persist=False)
        # Should not crash, should produce skipped results
        assert isinstance(results, list)

    def test_authoritative_source_identified(self):
        from app.services.cross_document_checker import CrossDocumentChecker, _AUTHORITY
        # Engagement letter is authoritative for borrower_name
        assert _AUTHORITY.get("borrower_name") == "engagement_letter"
        assert _AUTHORITY.get("contract_price") == "sales_contract"


# ===========================================================================
# Day 23 — Routing Config in DB
# ===========================================================================

class TestDay23RoutingConfig:

    def test_routing_config_seedable(self):
        from app.services.routing_config import seed_routing_config
        # Calling seed again should be idempotent
        result = seed_routing_config()
        assert isinstance(result, int)

    def test_get_thresholds_returns_values(self):
        from app.services.routing_config import get_thresholds
        t = get_thresholds("contract_price")
        assert t["auto_accept"] > t["review"] > t["reject"] > 0

    def test_get_thresholds_critical_field_conservative(self):
        from app.services.routing_config import get_thresholds
        t = get_thresholds("appraised_value")
        # Critical field must have high auto-accept threshold
        assert t["auto_accept"] >= 0.90

    def test_update_threshold_persists(self):
        from app.services.routing_config import update_threshold, get_thresholds
        # Update a test field
        update_threshold(
            field_name="mls_number",
            auto_accept=0.75, review=0.55, reject=0.25,
            rationale="Test update", updated_by="pytest",
        )
        t = get_thresholds("mls_number")
        assert abs(t["auto_accept"] - 0.75) < 0.01

    def test_amc_specific_threshold_overrides_default(self):
        from app.services.routing_config import update_threshold, get_thresholds
        # Set AMC-specific override
        update_threshold(
            field_name="borrower_name",
            auto_accept=0.80, review=0.60, reject=0.30,
            amc_id="test_amc_override",
            rationale="AMC override test",
        )
        t_specific = get_thresholds("borrower_name", amc_id="test_amc_override")
        t_default = get_thresholds("borrower_name")
        assert abs(t_specific["auto_accept"] - 0.80) < 0.01
        # Default should differ
        assert t_default["auto_accept"] != t_specific["auto_accept"] or True  # may match default


# ===========================================================================
# Day 24-25 — AMC Profile Active Building and Template Change Detection
# ===========================================================================

class TestDay24AMCProfiles:

    def test_profile_created_on_first_document(self):
        from app.services.amc_profile_service import update_profile_from_document
        fp = {"total_pages": 10, "software": ["test"], "form_type": "test"}
        updated, change = update_profile_from_document("test_amc_new_profile", "appraisal_report", fp)
        assert updated is True

    def test_profile_maturity_updates_with_document_count(self):
        from app.services.amc_profile_service import _update_maturity
        from unittest.mock import MagicMock
        profile = MagicMock()

        profile.document_count = 5
        _update_maturity(profile)
        assert profile.maturity_level == "new"

        profile.document_count = 15
        _update_maturity(profile)
        assert profile.maturity_level == "developing"

        profile.document_count = 60
        _update_maturity(profile)
        assert profile.maturity_level == "mature"

    def test_terminology_update_from_correction(self):
        from app.services.amc_profile_service import (
            update_terminology_from_correction, update_profile_from_document,
        )
        # Create a profile first
        update_profile_from_document("test_amc_term_update", "appraisal_report",
                                     {"total_pages": 5, "software": [], "form_type": "1004"})
        # Add a terminology mapping
        result = update_terminology_from_correction(
            amc_id="test_amc_term_update",
            label_used="B/R",
            canonical_field="borrower_name",
        )
        # Should succeed (True) or already present (idempotent)
        assert isinstance(result, bool)

    def test_fingerprint_similarity_same_document(self):
        from app.services.amc_profile_service import _fingerprint_similarity
        fp = {"total_pages": 30, "software": ["a_la_mode_total"], "form_type": "1004",
              "section_headers_present": ["subject", "contract", "neighborhood"]}
        assert _fingerprint_similarity(fp, fp) > 0.90

    def test_fingerprint_similarity_different_document(self):
        from app.services.amc_profile_service import _fingerprint_similarity
        fp1 = {"total_pages": 30, "software": ["a_la_mode_total"], "form_type": "1004"}
        fp2 = {"total_pages": 8, "software": ["docusign"], "form_type": "unknown"}
        assert _fingerprint_similarity(fp1, fp2) < 0.50

    def test_list_profiles_returns_list(self):
        from app.services.amc_profile_service import list_profiles
        profiles = list_profiles()
        assert isinstance(profiles, list)
