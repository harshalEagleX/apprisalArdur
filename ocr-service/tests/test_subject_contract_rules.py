"""
Subject + Contract rule upgrades — unit coverage (no DB / no extraction / no LLM).

Covers the MIRA-spec behaviors added in the subject/contract improvement pass:
token-containment borrower matching, company-name lender matching, the state
address component, tax-year window, census FIPS normalization, occupancy and
special-assessment cascades, contract sale-type / variance / concession
consistency, and the personal-property scan.
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


def _statuses(results):
    return [r.status for r in (results if isinstance(results, list) else [results])]


# ---------------------------------------------------------------------------
# matching.py — new normalizers / token containment
# ---------------------------------------------------------------------------

class TestNameContainment:
    def test_all_tokens_found(self):
        from app.qc.matching import match_name_containment
        assert match_name_containment("Anton Deineko", "DEINEKO, ANTON").verdict == "match"

    def test_appraisal_may_have_extra_parties(self):
        from app.qc.matching import match_name_containment
        mr = match_name_containment("Anton Deineko",
                                    "Deineko, Anton & Domanska, Viktoriia")
        assert mr.verdict == "match"

    def test_missing_coborrower_is_mismatch(self):
        from app.qc.matching import match_name_containment
        mr = match_name_containment("Anton Deineko & Viktoriia Domanska", "Anton Deineko")
        assert mr.verdict == "mismatch"

    def test_suffix_only_difference_is_review(self):
        from app.qc.matching import match_name_containment
        assert match_name_containment("John Smith JR", "John Smith").verdict == "review"

    def test_middle_initial_ignored(self):
        from app.qc.matching import match_name_containment
        assert match_name_containment("Anton M. Deineko", "Anton Deineko").verdict == "match"


class TestCompanyAndState:
    def test_company_designators_dropped(self):
        from app.qc.matching import match_text
        assert match_text("Champions Funding, LLC", "Champions Funding",
                          kind="company").verdict == "match"

    def test_state_name_to_code(self):
        from app.qc.matching import normalize_state
        assert normalize_state("Texas") == "TX"
        assert normalize_state("tx") == "TX"
        assert normalize_state("Atlantis") == ""


# ---------------------------------------------------------------------------
# subject rules
# ---------------------------------------------------------------------------

class TestS1State:
    def test_state_mismatch_fails(self):
        from app.qc.rules.subject import s1_address
        ctx = QCContext("t",
                        appraisal=_rs(property_address="1 Main St", city="Katy",
                                      zip_code="77449", state="TX"),
                        engagement=_rs("engagement_letter", property_address="1 Main St",
                                       city="Katy", zip_code="77449", state="Florida"))
        st = [r for r in s1_address(ctx) if "state" in r.fields_involved]
        assert st and st[0].status == RuleStatus.FAIL

    def test_full_name_matches_code(self):
        from app.qc.rules.subject import s1_address
        ctx = QCContext("t",
                        appraisal=_rs(property_address="1 Main St", city="Katy",
                                      zip_code="77449", state="TX"),
                        engagement=_rs("engagement_letter", property_address="1 Main St",
                                       city="Katy", zip_code="77449", state="Texas"))
        st = [r for r in s1_address(ctx) if "state" in r.fields_involved]
        assert st and st[0].status == RuleStatus.PASS


class TestS2Borrower:
    def test_containment_passes_with_extra_party(self):
        from app.qc.rules.subject import s2_borrower
        ctx = QCContext("t",
                        appraisal=_rs(borrower_name="Deineko, Anton & Domanska, Viktoriia"),
                        engagement=_rs("engagement_letter", borrower_name="Anton Deineko"))
        main = [r for r in s2_borrower(ctx) if "borrower_name" in r.fields_involved]
        assert main[0].status == RuleStatus.PASS

    def test_missing_token_fails(self):
        from app.qc.rules.subject import s2_borrower
        ctx = QCContext("t",
                        appraisal=_rs(borrower_name="Anton Deineko"),
                        engagement=_rs("engagement_letter",
                                       borrower_name="Maria Gonzalez"))
        main = [r for r in s2_borrower(ctx) if "borrower_name" in r.fields_involved]
        assert main[0].status == RuleStatus.FAIL


class TestS4:
    def test_short_legal_description_verifies(self):
        from app.qc.rules.subject import s4_legal
        ctx = QCContext("t", appraisal=_rs(legal_description="LOT 4"))
        assert s4_legal(ctx).status == RuleStatus.VERIFY

    def test_full_legal_description_passes(self):
        from app.qc.rules.subject import s4_legal
        ctx = QCContext("t", appraisal=_rs(
            legal_description="LOT 4 BLK 2 CINCO RANCH SOUTHWEST SEC 30"))
        assert s4_legal(ctx).status == RuleStatus.PASS

    def test_tax_year_within_window_passes(self):
        from app.qc.rules.subject import s4_tax_year
        ctx = QCContext("t", appraisal=_rs(tax_year="2025", effective_date="03/15/2026"))
        assert s4_tax_year(ctx).status == RuleStatus.PASS

    def test_tax_year_stale_fails(self):
        from app.qc.rules.subject import s4_tax_year
        ctx = QCContext("t", appraisal=_rs(tax_year="2021", effective_date="03/15/2026"))
        assert s4_tax_year(ctx).status == RuleStatus.FAIL

    def test_tax_year_future_fails(self):
        from app.qc.rules.subject import s4_tax_year
        ctx = QCContext("t", appraisal=_rs(tax_year="2027", effective_date="03/15/2026"))
        assert s4_tax_year(ctx).status == RuleStatus.FAIL

    def test_taxes_with_decimals_fail(self):
        from app.qc.rules.subject import s4_taxes
        ctx = QCContext("t", appraisal=_rs(real_estate_taxes="8,555.47"))
        assert s4_taxes(ctx).status == RuleStatus.FAIL

    def test_implausible_tax_amount_verifies(self):
        from app.qc.rules.subject import s4_taxes
        ctx = QCContext("t", appraisal=_rs(real_estate_taxes="450000"))
        assert s4_taxes(ctx).status == RuleStatus.VERIFY


class TestS5S6:
    def test_generic_neighborhood_verifies(self):
        from app.qc.rules.subject import s5_neighborhood
        ctx = QCContext("t", appraisal=_rs(neighborhood_name="Residential"))
        assert s5_neighborhood(ctx).status == RuleStatus.VERIFY

    def test_na_neighborhood_fails(self):
        from app.qc.rules.subject import s5_neighborhood
        ctx = QCContext("t", appraisal=_rs(neighborhood_name="N/A"))
        assert s5_neighborhood(ctx).status == RuleStatus.FAIL

    def test_census_fips_normalized(self):
        from app.qc.rules.subject import _normalize_census, s6_census
        assert _normalize_census("48157672100") == "6721.00"
        ctx = QCContext("t", appraisal=_rs(census_tract="48157672100"))
        assert s6_census(ctx).status == RuleStatus.PASS

    def test_census_bad_format_fails(self):
        from app.qc.rules.subject import s6_census
        ctx = QCContext("t", appraisal=_rs(census_tract="malformed"))
        assert s6_census(ctx).status == RuleStatus.FAIL

    def test_map_reference_non_numeric_fails(self):
        from app.qc.rules.subject import s6_mapref
        ctx = QCContext("t", appraisal=_rs(map_reference="N/A"))
        assert s6_mapref(ctx).status == RuleStatus.FAIL


class TestS7S8:
    def test_tenant_without_lease_verifies(self):
        from app.qc.rules.subject import s7_occupancy
        ctx = QCContext("t", appraisal=_rs(occupant_status="Tenant"))
        assert RuleStatus.VERIFY in _statuses(s7_occupancy(ctx))

    def test_owner_occupied_no_cascade(self):
        from app.qc.rules.subject import s7_occupancy
        ctx = QCContext("t", appraisal=_rs(occupant_status="Owner"))
        assert _statuses(s7_occupancy(ctx)) == [RuleStatus.PASS]

    def test_assessment_without_comment_verifies(self):
        from app.qc.rules.subject import s8_assessment
        ctx = QCContext("t", appraisal=_rs(special_assessments="1200"))
        assert s8_assessment(ctx).status == RuleStatus.VERIFY

    def test_zero_assessment_passes(self):
        from app.qc.rules.subject import s8_assessment
        ctx = QCContext("t", appraisal=_rs(special_assessments="0"))
        assert s8_assessment(ctx).status == RuleStatus.PASS


# ---------------------------------------------------------------------------
# contract rules
# ---------------------------------------------------------------------------

def _purchase_ctx(contract_fields=None, **appraisal_fields):
    appraisal_fields.setdefault("assignment_type", "Purchase")
    contract = _rs("sales_contract", **contract_fields) if contract_fields is not None else None
    return QCContext("t", appraisal=_rs(**appraisal_fields), contract=contract)


class TestC1:
    def test_sale_type_in_commentary_passes(self):
        from app.qc.rules.contract import c1_analyze
        ctx = _purchase_ctx(did_analyze_contract="true",
                            contract_analysis_comment="The transaction is an arms length sale.")
        sale = [r for r in c1_analyze(ctx) if "sale_type" in r.fields_involved]
        assert sale[0].status == RuleStatus.PASS

    def test_commentary_without_sale_type_fails(self):
        from app.qc.rules.contract import c1_analyze
        ctx = _purchase_ctx(did_analyze_contract="true",
                            contract_analysis_comment="The contract was reviewed in detail.")
        sale = [r for r in c1_analyze(ctx) if "sale_type" in r.fields_involved]
        assert sale[0].status == RuleStatus.FAIL

    def test_value_variance_over_band_verifies(self):
        from app.qc.rules.contract import c1_analyze
        ctx = _purchase_ctx(did_analyze_contract="true", sale_type="Arms-Length",
                            appraised_value="430000", contract_price="400000")
        var = [r for r in c1_analyze(ctx) if r.template_id == "C-1-variance"]
        assert var and var[0].status == RuleStatus.VERIFY

    def test_value_within_band_quiet(self):
        from app.qc.rules.contract import c1_analyze
        ctx = _purchase_ctx(did_analyze_contract="true", sale_type="Arms-Length",
                            appraised_value="405000", contract_price="400000")
        assert not [r for r in c1_analyze(ctx) if r.template_id == "C-1-variance"]

    def test_refi_populated_contract_fails(self):
        from app.qc.rules.contract import c1_analyze
        ctx = QCContext("t", appraisal=_rs(assignment_type="Refinance",
                                           contract_price="400000"))
        assert c1_analyze(ctx).status == RuleStatus.FAIL


class TestC4:
    def test_no_with_amount_is_contradiction(self):
        from app.qc.rules.contract import c4_concessions
        ctx = _purchase_ctx(contract_fields={},
                            has_financial_assistance="No",
                            financial_assistance_amount="5000")
        assert RuleStatus.FAIL in _statuses(c4_concessions(ctx))

    def test_yes_without_amount_fails(self):
        from app.qc.rules.contract import c4_concessions
        ctx = _purchase_ctx(contract_fields={}, has_financial_assistance="Yes")
        assert RuleStatus.FAIL in _statuses(c4_concessions(ctx))

    def test_amount_matches_contract_passes(self):
        from app.qc.rules.contract import c4_concessions
        ctx = _purchase_ctx(contract_fields={"concessions_amount": "5000"},
                            has_financial_assistance="Yes",
                            financial_assistance_amount="5000",
                            financial_assistance_description="closing costs")
        assert RuleStatus.PASS in _statuses(c4_concessions(ctx))


class TestC5:
    def test_no_items_not_applicable(self):
        from app.qc.rules.contract import c5_personal_property
        ctx = _purchase_ctx(contract_fields={})
        assert c5_personal_property(ctx).status == RuleStatus.NOT_APPLICABLE

    def test_items_without_commentary_verifies(self):
        from app.qc.rules.contract import c5_personal_property
        ctx = _purchase_ctx(contract_fields={"personal_property_items": "refrigerator, washer"})
        assert c5_personal_property(ctx).status == RuleStatus.VERIFY


# ---------------------------------------------------------------------------
# contract_extractor — personal-property scan
# ---------------------------------------------------------------------------

class TestPersonalPropertyScan:
    def test_items_in_context_found(self):
        from app.extraction.contract_extractor import _personal_property
        text = ("12. PERSONAL PROPERTY: the following items shall convey:\n"
                "refrigerator, washer and dryer, and the hot tub on the patio.")
        items = _personal_property(text)
        assert items and "refrigerator" in items and "hot tub" in items

    def test_bare_appliance_mention_ignored(self):
        from app.extraction.contract_extractor import _personal_property
        assert _personal_property("The kitchen includes a refrigerator.") is None


# ---------------------------------------------------------------------------
# review-pass updates: SKIPPED→VERIFY, co-buyer, 1073 gate, C-1 consistency,
# TREC concessions/date/buyers, exact date matching
# ---------------------------------------------------------------------------

class TestSkippedPolicy:
    def test_format_rule_extraction_gap_verifies(self):
        from app.qc.rules.subject import s6_census
        ctx = QCContext("t", appraisal=_rs(other_field="x"))
        assert s6_census(ctx).status == RuleStatus.VERIFY

    def test_tax_year_gap_verifies(self):
        from app.qc.rules.subject import s4_tax_year
        ctx = QCContext("t", appraisal=_rs(other_field="x"))
        assert s4_tax_year(ctx).status == RuleStatus.VERIFY

    def test_missing_engagement_is_not_applicable(self):
        from app.qc.rules.subject import s1_address
        ctx = QCContext("t", appraisal=_rs(property_address="1 Main St"))
        assert all(r.status == RuleStatus.NOT_APPLICABLE for r in s1_address(ctx))

    def test_missing_contract_concessions_verifies(self):
        from app.qc.rules.contract import c4_concessions
        ctx = _purchase_ctx(has_financial_assistance="No")
        assert RuleStatus.VERIFY in _statuses(c4_concessions(ctx))
        assert RuleStatus.SKIPPED not in _statuses(c4_concessions(ctx))


class TestDateMatching:
    def test_close_dates_are_mismatch(self):
        from app.qc.matching import match_date
        assert match_date("04/27/2026", "04/29/2026").verdict == "mismatch"

    def test_same_day_different_format_match(self):
        from app.qc.matching import match_date
        assert match_date("4/27/26", "04/27/2026").verdict == "match"

    def test_unparseable_is_review(self):
        from app.qc.matching import match_date
        assert match_date("April", "04/27/2026").verdict == "review"


class TestContractCoBuyer:
    def test_extra_contract_buyer_verifies(self):
        from app.qc.rules.subject import s2_borrower
        ctx = QCContext(
            "t",
            appraisal=_rs(borrower_name="Anton Deineko"),
            engagement=_rs("engagement_letter", borrower_name="Anton Deineko"),
            contract=_rs("sales_contract",
                         buyer_names="Anton Deineko and Viktoriia Domanska"))
        extra = [r for r in s2_borrower(ctx) if r.template_id == "S-2-contract-buyer"]
        assert extra and extra[0].status == RuleStatus.VERIFY
        assert "Domanska" in extra[0].message

    def test_matching_buyers_quiet(self):
        from app.qc.rules.subject import s2_borrower
        ctx = QCContext(
            "t",
            appraisal=_rs(borrower_name="Anton Deineko"),
            engagement=_rs("engagement_letter", borrower_name="Anton Deineko"),
            contract=_rs("sales_contract", buyer_names="DEINEKO, ANTON"))
        assert not [r for r in s2_borrower(ctx) if r.template_id == "S-2-contract-buyer"]


class TestS9FormGate:
    def test_condo_form_not_applicable(self):
        from app.qc.rules.subject import _is_pud_form
        ctx = QCContext("t", appraisal=_rs(hoa_dues="635"),
                        engagement=_rs("engagement_letter", form_type="Conventional 1073"))
        assert not _is_pud_form(ctx)

    def test_1004_form_applicable(self):
        from app.qc.rules.subject import _is_pud_form
        ctx = QCContext("t", appraisal=_rs(form_type="1004", hoa_dues="635"))
        assert _is_pud_form(ctx)


class TestC1Consistency:
    def test_confirmed_refi_populated_fails(self):
        from app.qc.rules.contract import c1_analyze
        ctx = QCContext("t", appraisal=_rs(assignment_type="Refinance",
                                           contract_price="400000"))
        assert c1_analyze(ctx).status == RuleStatus.FAIL

    def test_low_confidence_refi_verifies(self):
        from app.core.result import ExtractionResult, ExtractionResultSet
        from app.qc.rules.contract import c1_analyze
        rs = ExtractionResultSet(document_path="x", document_type="appraisal_report")
        rs.add(ExtractionResult(canonical_name="assignment_type",
                                document_type="appraisal_report", value="Refinance",
                                extraction_method="test", confidence=0.5, source_page=1))
        rs.add(ExtractionResult(canonical_name="contract_price",
                                document_type="appraisal_report", value="400000",
                                extraction_method="test", confidence=0.9, source_page=1))
        rs.finalize()
        ctx = QCContext("t", appraisal=rs)
        r = c1_analyze(ctx)
        assert r.status == RuleStatus.VERIFY and r.template_id == "C-1-txn-unknown"


class TestTRECExtraction:
    def test_seller_pay_dollar_amount(self):
        from app.extraction.contract_extractor import _trec_concessions
        text = ("12. SETTLEMENT AND OTHER EXPENSES.\n"
                "A.(1)(b) Seller shall also pay an amount not to exceed $ 5,000.00 to be "
                "applied to Buyer's Expenses.")
        assert _trec_concessions(text, "380000") == "5000"

    def test_seller_pay_percentage(self):
        from app.extraction.contract_extractor import _trec_concessions
        text = "Seller shall also pay up to 3 % of the sales price toward expenses"
        assert _trec_concessions(text, "380000") == "11400"

    def test_executed_date_beats_closing_date(self):
        from app.extraction.contract_extractor import _contract_date
        text = ("The Closing Date will be 05/29/2026 or sooner.\n"
                "lots of pages...\n"
                "EXECUTED the 27 day of April 04/27/2026 (EFFECTIVE DATE).")
        assert _contract_date(text) == "04/27/2026"

    def test_trec_parties_clause_buyers(self):
        from app.extraction.contract_extractor import _buyer_names
        text = ("1. PARTIES: The parties to this contract are Lance Sheffield and Holly "
                "Sheffield (Seller) and Anton Deineko and Viktoriia Domanska (Buyer).")
        assert "Viktoriia Domanska" in _buyer_names(text)
