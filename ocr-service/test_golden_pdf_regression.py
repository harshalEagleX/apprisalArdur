import shutil
import subprocess
import unittest
from pathlib import Path

from app.services.comparable_extraction import comparable_grid_extractor
from app.services.contract_extraction import hybrid_contract_extractor
from app.services.document_quality import score_text_quality
from app.services.entity_resolution import match_addresses


ROOT = Path(__file__).resolve().parents[1]


PDFS = {
    "contract_8234": ROOT / "uploads/EQSS/xBatch/contract/8234 E Pearson Purchase-agreement.pdf",
    "contract_2307": ROOT / "uploads/EQSS/xBatch/contract/2307 Merrily CONTRACT (1).pdf",
    "contract_96": ROOT / "uploads/EQSS/xBatch/contract/96 baell Tr Ct CONTRACT.pdf",
    "appraisal_8234": ROOT / "uploads/EQSS/xBatch/appraisal/8234 E Pearson.pdf",
    "appraisal_2307": ROOT / "uploads/EQSS/xBatch/appraisal/2307 Merrily Cir N.pdf",
    "appraisal_96": ROOT / "uploads/EQSS/xBatch/appraisal/96 Baell Trace Ct SE.pdf",
}


@unittest.skipUnless(shutil.which("pdftotext"), "pdftotext is required for golden PDF regression tests")
class GoldenPdfRegressionTest(unittest.TestCase):
    maxDiff = None

    def _text(self, key: str) -> str:
        pdf = PDFS[key]
        self.assertTrue(pdf.exists(), f"Missing golden PDF: {pdf}")
        proc = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout

    def test_8234_purchase_agreement_price_date_and_personal_property(self):
        result = hybrid_contract_extractor.extract(self._text("contract_8234"))

        self.assertEqual(result.quality.status, "READABLE")
        self.assertEqual(result.agreement.contract_price, 411000.0)
        self.assertEqual(result.agreement.contract_date, "03/29/2026")
        self.assertIn("Dishwasher", result.agreement.personal_property_items)
        self.assertIn("Refrigerator", result.agreement.personal_property_items)

    def test_2307_purchase_agreement_avoids_closing_date_guess(self):
        result = hybrid_contract_extractor.extract(self._text("contract_2307"))

        self.assertEqual(result.quality.status, "READABLE")
        self.assertEqual(result.agreement.contract_price, 335000.0)
        self.assertIsNone(result.agreement.contract_date)
        self.assertEqual(result.agreement.concessions_amount, 10050.0)
        self.assertIn("Cooktop", result.agreement.personal_property_items)
        self.assertIn("Electric Water Heater", result.agreement.personal_property_items)

    def test_96_image_contract_native_text_is_not_trusted(self):
        text = self._text("contract_96")
        quality = score_text_quality(text, expected_terms=["Buyer", "Seller", "Purchase Price"])
        result = hybrid_contract_extractor.extract(text)

        self.assertNotEqual(quality.status, "READABLE")
        self.assertIsNone(result.agreement.contract_price)
        self.assertIsNone(result.agreement.contract_date)

    def test_96_appraisal_comparable_sale_prices_are_structured(self):
        result = comparable_grid_extractor.extract(self._text("appraisal_96"))
        prices = [comp.sale_price for comp in result.comparables]

        self.assertGreaterEqual(result.confidence, 0.80)
        self.assertEqual(prices[:3], [280000.0, 275000.0, 286000.0])

    def test_all_supplied_appraisals_extract_structured_comparable_prices(self):
        expected_prices = {
            "appraisal_8234": [430000.0, 400000.0, 455000.0],
            "appraisal_2307": [370000.0, 300000.0, 375000.0],
            "appraisal_96": [280000.0, 275000.0, 286000.0],
        }

        for key, expected in expected_prices.items():
            with self.subTest(key=key):
                result = comparable_grid_extractor.extract(self._text(key))
                prices = [comp.sale_price for comp in result.comparables]

                self.assertGreaterEqual(result.confidence, 0.80)
                self.assertEqual(prices[:3], expected)

    def test_directional_address_variants_escalate_to_review_not_pass(self):
        match = match_addresses("96 Baell Trace Ct SE", "96 SE Baell Trace Ct")

        self.assertTrue(match.same_entity)
        self.assertEqual(match.status, "REVIEW")
        self.assertIn("directional_order_differs", match.reasons)


if __name__ == "__main__":
    unittest.main()
