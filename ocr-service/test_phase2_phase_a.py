import unittest
from types import SimpleNamespace

from app.services.phase2_extraction import (
    Phase2ExtractionEngine,
    build_page_position_map,
)


class Phase2PhaseATest(unittest.TestCase):
    def setUp(self):
        self.engine = Phase2ExtractionEngine()

    def test_extract_rejects_next_label_as_value(self):
        text = "Neighborhood Name\nMap Reference\nSagecreek\n"
        page_index = {1: text}
        page_pos = build_page_position_map(page_index)

        result = self.engine._extract(
            "neighborhood_name",
            text,
            [r"Neighborhood Name[:\s]+([^\n]+)"],
            page_pos,
            0,
        )

        self.assertIsNone(result.value)
        self.assertEqual(result.extraction_method, "not_found")

    def test_lender_window_excludes_later_page_boilerplate(self):
        page_index = {
            1: "Uniform Residential Appraisal Report\nProperty Address 96 Baell Trace Ct SE\n",
            2: "Subject continued\n",
            6: (
                "The intended use is for the Lender/Client and HUD/FHA.\n"
                "Lender/Client to evaluate the property that is the subject of this appraisal for a mortgage\n"
            ),
        }
        full_text = "\n\n".join(page_index[page] for page in sorted(page_index))
        page_pos = build_page_position_map(page_index)
        lender_text, offset = self.engine._text_window_for_pages(full_text, page_pos, 1, 2)

        result = self.engine._extract(
            "lender_name",
            lender_text,
            [
                r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z0-9\s,\.&]+(?:Corporation|Corp|Inc|LLC|LLP|Company|Co\.?|Bank|Mortgage|Credit Union|Funding|Capital|Financial|Home Loans?|Lending|Services?))(?:\s+Address|\s*$|\n)",
                r"Lender/?Client[\s—:-]+([A-Z][A-Za-z0-9\s,\.&]{4,60}?)(?=\s+\d{1,5}\s|\s+Address|\n|$)",
            ],
            page_pos,
            offset,
        )

        self.assertIsNone(result.value)
        self.assertEqual(result.extraction_method, "not_found")

    def test_comparable_missing_boundary_does_not_swallow_document_tail(self):
        text = (
            "Sales Comparison Approach\n"
            "COMPARABLE SALE # 1\n"
            "304 Janet St. Suite E Valdosta, GA 31602\n"
            "Signature of Appraiser\n"
        )
        page_index = {1: text}
        page_pos = build_page_position_map(page_index)

        comps = self.engine._extract_comparables(text, page_pos, 0)

        self.assertEqual(comps, [{}, {}, {}])

    def test_word_box_anchor_fills_label_row_value_from_next_row(self):
        text = "Neighborhood Name\nMap Reference\nSagecreek\n12-3\n"
        page_index = {1: text}
        page_pos = build_page_position_map(page_index)
        self.engine._page_index = page_index
        self.engine._page_positions = page_pos
        self.engine._word_index = {
            1: [
                self._word("Neighborhood", 0.10, 0.10, 0.10, 0.02),
                self._word("Name", 0.21, 0.10, 0.04, 0.02),
                self._word("Map", 0.36, 0.10, 0.04, 0.02),
                self._word("Reference", 0.41, 0.10, 0.09, 0.02),
                self._word("Sagecreek", 0.10, 0.15, 0.10, 0.02),
                self._word("12-3", 0.36, 0.15, 0.05, 0.02),
            ]
        }

        result = self.engine._extract(
            "neighborhood_name",
            text,
            [r"Neighborhood Name[:\s]+([^\n]+)"],
            page_pos,
            0,
            spatial_labels=["Neighborhood Name"],
        )

        self.assertEqual(result.value, "Sagecreek")
        self.assertEqual(result.extraction_method, "word_box_anchor")
        self.assertEqual(result.source_page, 1)
        self.assertEqual(result.bbox_x, 0.1)
        self.assertEqual(result.bbox_y, 0.15)

    def test_lender_spatial_fallback_respects_page_window(self):
        page_index = {
            1: "Lender/Client\nClear2 Mortgage, Inc\n",
            6: "Lender/Client\nBoilerplate Mortgage\n",
        }
        full_text = "\n\n".join(page_index[page] for page in sorted(page_index))
        page_pos = build_page_position_map(page_index)
        self.engine._page_index = page_index
        self.engine._page_positions = page_pos
        self.engine._word_index = {
            1: [
                self._word("Lender/Client", 0.10, 0.10, 0.12, 0.02, page=1),
                self._word("Clear2", 0.10, 0.15, 0.06, 0.02, page=1),
                self._word("Mortgage,", 0.17, 0.15, 0.09, 0.02, page=1),
                self._word("Inc", 0.27, 0.15, 0.04, 0.02, page=1),
            ],
            6: [
                self._word("Lender/Client", 0.10, 0.10, 0.12, 0.02, page=6),
                self._word("Boilerplate", 0.10, 0.15, 0.11, 0.02, page=6),
                self._word("Mortgage", 0.22, 0.15, 0.09, 0.02, page=6),
            ],
        }
        lender_text, offset = self.engine._text_window_for_pages(full_text, page_pos, 1, 2)

        result = self.engine._extract(
            "lender_name",
            lender_text,
            [r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z0-9\s,\.&]+(?:Mortgage|Inc))(?:\s+Address|\s*$|\n)"],
            page_pos,
            offset,
            spatial_labels=["Lender/Client"],
            spatial_page_range=(1, 2),
        )

        self.assertEqual(result.value, "Clear2 Mortgage, Inc")
        self.assertEqual(result.source_page, 1)

    def _word(self, text, x, y, w, h, page=1):
        return SimpleNamespace(
            text=text,
            page=page,
            bbox_x=x,
            bbox_y=y,
            bbox_w=w,
            bbox_h=h,
            confidence=1.0,
        )


if __name__ == "__main__":
    unittest.main()
