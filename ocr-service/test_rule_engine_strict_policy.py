import unittest

from app.models.appraisal import AppraisalReport, EngagementLetter, ValidationContext
from app.rule_engine.engine import RuleEngine
from app.rule_engine.smart_identifier import RuleResult, RuleStatus
from app.rules.contract_rules import validate_contract_price_date
from app.rules.improvement_rules import validate_security_bars
from app.rules.photo_rules import validate_obsolescence_photos
from app.rules.sales_comparison_rules import (
    validate_comparable_photos,
    validate_new_construction,
    validate_unique_design,
)
from app.rules.signature_rules import validate_supervisory_appraiser


class StrictRulePolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = RuleEngine()
        self.context = ValidationContext(report=AppraisalReport(), raw_text="dummy")

    def test_text_only_sca_pass_is_escalated_to_review(self):
        result = RuleResult(
            rule_id="SCA-4",
            rule_name="Proximity",
            status=RuleStatus.PASS,
            message="Comparable proximity evidence found in OCR text.",
            evidence=["OCR text contained proximity words"],
        )

        self.engine._enforce_pass_evidence_contract(self.context, "SCA-4", result)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("weak text/image evidence", result.message)

    def test_structured_sca_pass_remains_pass(self):
        result = RuleResult(
            rule_id="SCA-2",
            rule_name="Comparables Required",
            status=RuleStatus.PASS,
            message="3 sales and 2 listings provided.",
            details={"structured_validation": True},
            compared_fields=["comparables_count_sales", "comparables_count_listings"],
            compared_values={"sales": 3, "listings": 2},
            comparison_method="minimum_comparable_count_check",
        )

        self.engine._enforce_pass_evidence_contract(self.context, "SCA-2", result)

        self.assertEqual(result.status, RuleStatus.PASS)

    def test_absence_of_unique_design_trigger_is_review_not_pass(self):
        result = validate_unique_design(self.context)

        self.assertEqual(result.status, RuleStatus.REVIEW)

    def test_new_construction_requires_structured_non_applicability(self):
        missing_result = validate_new_construction(self.context)
        self.assertEqual(missing_result.status, RuleStatus.REVIEW)

        self.context.report.improvements.year_built = 1998
        self.context.report.improvements.condition_rating = "C3"
        structured_result = validate_new_construction(self.context)
        self.assertEqual(structured_result.status, RuleStatus.NOT_APPLICABLE)
        self.assertEqual(structured_result.details.get("structured_validation"), True)

    def test_conventional_comparable_photos_do_not_auto_pass(self):
        result = validate_comparable_photos(self.context)

        self.assertEqual(result.status, RuleStatus.REVIEW)

    def test_no_obsolescence_trigger_is_review_without_structured_condition(self):
        result = validate_obsolescence_photos(self.context)

        self.assertEqual(result.status, RuleStatus.REVIEW)

    def test_no_security_bar_trigger_is_review_not_pass(self):
        result = validate_security_bars(self.context)

        self.assertEqual(result.status, RuleStatus.REVIEW)

    def test_supervisory_appraiser_absence_is_not_applicable_not_pass(self):
        result = validate_supervisory_appraiser(self.context)

        self.assertEqual(result.status, RuleStatus.NOT_APPLICABLE)

    def test_refinance_contract_price_date_is_not_applicable_not_pass(self):
        context = ValidationContext(
            report=AppraisalReport(),
            engagement_letter=EngagementLetter(assignment_type="Refinance"),
        )

        result = validate_contract_price_date(context)

        self.assertEqual(result.status, RuleStatus.NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main()
