"""Conformance / market-inventory-list / AMC / UAD mappings — facts present in the
MISMO XML that previously fell to a PDF label-proximity guess or stayed unbound
(REVIEW). Each must land on its canonical field from the SUBJECT scope.

Backs EQ-34 (utilities typical), EQ-49 (additional features), EQ-51 (physical
deficiency), EQ-52 (conforms to neighborhood), EQ-109 (AMC name), EQ-116 (median
list price / DOM / ratio), EQ-136 (UAD version)."""

import tempfile
from pathlib import Path

from app.extraction.xml_extractor import extract_xml

_XML = """<?xml version="1.0"?>
<VALUATION_RESPONSE>
 <REPORT AppraisalFormType="FNM1004"/>
 <PARTIES>
  <MANAGEMENT_COMPANY GSEManagementCompanyName="Equity Solutions USA"/>
 </PARTIES>
 <PROPERTY>
  <_TAX _TotalTaxAmount="1828" _TotalSpecialTaxAmount="0"/>
  <PROPERTY_ANALYSIS _Type="ConformsToNeighborhood" _ExistsIndicator="Y"
       _Comment="Conforms in style and GLA."/>
  <PROPERTY_ANALYSIS _Type="UtilitiesAndOffSiteImprovementsConformToNeighborhood"
       _ExistsIndicator="Y"/>
  <PROPERTY_ANALYSIS _Type="PhysicalDeficiency" _ExistsIndicator="N"
       _Comment="No deficiencies noted."/>
  <PROPERTY_ANALYSIS _Type="AdditionalFeatures" _Comment="Financed solar system."/>
  <PROJECT>
   <_PER_UNIT_FEE _PeriodType="Monthly" _Amount="150"/>
  </PROJECT>
 </PROPERTY>
 <MARKET>
  <MARKET_INVENTORY _Type="MedianListPrice" _MonthRangeType="Last3Months" _Amount="529000"/>
  <MARKET_INVENTORY _Type="MedianListDOM" _MonthRangeType="Last3Months" _Count="56"/>
  <MARKET_INVENTORY _Type="MedianSalesToListRatio" _MonthRangeType="Last3Months" _Rate="100.02"/>
 </MARKET>
 <FORM AppraisalReportContentIdentifier="UAD Version 9/2011"/>
</VALUATION_RESPONSE>"""


def _extract():
    p = Path(tempfile.mkstemp(suffix=".xml")[1])
    p.write_text(_XML, encoding="utf-8")
    return extract_xml(p)


def test_conforms_to_neighborhood_indicator():
    assert _extract().get("conforms_to_neighborhood").value == "Yes"


def test_utilities_typical_indicator():
    assert _extract().get("utilities_typical").value == "Yes"


def test_physical_deficiency_no():
    assert _extract().get("physical_deficiency").value == "No"


def test_additional_features_comment():
    assert _extract().get("additional_features").value == "Financed solar system."


def test_amc_name_from_management_company():
    fs = _extract()
    assert fs.get("management_company").value == "Equity Solutions USA"
    assert fs.get("amc_name").value == "Equity Solutions USA"


def test_special_assessments_zero_is_kept():
    # "0" is a real answer (no special assessment), not a gap.
    assert _extract().get("special_assessments").value == "0"


def test_hoa_dues_nonzero_emitted():
    assert _extract().get("hoa_dues").value == "150"


def test_market_inventory_list_rows():
    fs = _extract()
    assert fs.get("mca_median_list_price_current_3").value == "529000"
    assert fs.get("mca_median_list_dom_current_3").value == "56"
    assert fs.get("mca_median_sale_list_ratio_current_3").value == "100.02"


def test_uad_version():
    assert _extract().get("uad_version").value == "UAD Version 9/2011"
