import unittest

from app.models.appraisal import AppraisalReport, EngagementLetter, ValidationContext
from app.rule_engine.smart_identifier import RuleStatus
from app.rules.addendum_rules import validate_uspap_addendum
from app.rules.fha_rules import validate_fha_economic_life, validate_fha_mpr
from app.rules.neighborhood_rules import validate_housing_price_range
from app.rules.signature_rules import validate_appraiser_info, validate_supervisory_appraiser
from app.rules.site_rules import validate_flood_hazard, validate_site_area, validate_utilities


class ChecklistClauseCoverageTests(unittest.TestCase):
    def context(self, raw_text=""):
        return ValidationContext(report=AppraisalReport(), raw_text=raw_text)

    def test_n3_requires_age_and_predominant_values(self):
        ctx = self.context()
        ctx.report.neighborhood.price_low = 100000
        ctx.report.neighborhood.price_high = 200000

        result = validate_housing_price_range(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("Age Low", result.message)
        self.assertIn("Predominant Price", result.message)

    def test_n3_fails_reversed_age_range(self):
        ctx = self.context()
        ctx.report.neighborhood.price_low = 100000
        ctx.report.neighborhood.price_high = 200000
        ctx.report.neighborhood.predominant_price = 150000
        ctx.report.neighborhood.age_low = 30
        ctx.report.neighborhood.age_high = 10
        ctx.report.neighborhood.predominant_age = 20

        result = validate_housing_price_range(ctx)

        self.assertEqual(result.status, RuleStatus.FAIL)

    def test_st2_requires_area_unit(self):
        ctx = self.context()
        ctx.report.site.area = 10000

        result = validate_site_area(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("without a unit", result.message)

    def test_st7_private_well_or_street_requires_commentary(self):
        ctx = self.context("Electricity Water Sewer private well private street")
        ctx.report.site.utilities_electricity = True
        ctx.report.site.utilities_water = True

        result = validate_utilities(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("Private well/septic/street", result.message)

    def test_st8_flood_zone_requires_map_details(self):
        ctx = self.context("FEMA Flood Zone AE")
        ctx.report.site.fema_flood_hazard = True
        ctx.report.site.fema_flood_zone = "AE"

        result = validate_flood_hazard(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("map date", result.message)

    def test_add9_prior_service_certification_requires_commentary_review(self):
        ctx = self.context(
            "USPAP Appraisal Report Exposure Time 30 days "
            "I HAVE performed services regarding the subject property within the prior three years."
        )

        result = validate_uspap_addendum(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("prior-service", result.message)

    def test_fha_site_condo_requires_1073_form(self):
        ctx = self.context("FHA Case Number 123-4567890 site condo")
        ctx.engagement_letter = EngagementLetter(loan_type="FHA")
        ctx.report.form_type = "1004"

        result = validate_fha_mpr(ctx)

        self.assertEqual(result.status, RuleStatus.FAIL)
        self.assertIn("1073", result.message)

    def test_fha_economic_life_evidence_is_review_not_pass(self):
        ctx = self.context("FHA Case Number 123-4567890 remaining economic life 25 years")
        ctx.engagement_letter = EngagementLetter(loan_type="FHA")

        result = validate_fha_economic_life(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)

    def test_sig2_requires_phone_email_expiration(self):
        ctx = self.context("Appraiser Name Jane Doe Company Name Example State Certification # GA12345")

        result = validate_appraiser_info(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("Phone", result.message)
        self.assertIn("Email", result.message)
        self.assertIn("Expiration Date", result.message)

    def test_sig3_supervisor_requires_inspection_checkbox_review(self):
        ctx = self.context("Supervisory Appraiser Name John Smith Company Name Example")

        result = validate_supervisory_appraiser(ctx)

        self.assertEqual(result.status, RuleStatus.REVIEW)
        self.assertIn("Did/Did Not Inspect", result.message)


if __name__ == "__main__":
    unittest.main()
