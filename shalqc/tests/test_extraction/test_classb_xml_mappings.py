"""Class-B XML mappings: facts that live in the MISMO XML but weren't being read
into their canonical fields. Each must land on the SUBJECT (not a comp) and, for
enums, canonicalize to the schema value."""

import tempfile
from pathlib import Path

from app.extraction.xml_extractor import extract_xml

_XML = """<?xml version="1.0"?>
<VALUATION_RESPONSE>
 <REPORT AppraisalFormType="FNM1004"/>
 <PROPERTY>
  <SALES_CONTRACT _Amount="500000" SellerIsOwnerIndicator="Y">
   <SALES_CONTRACT_EXTENSION><SALES_CONTRACT_EXTENSION_SECTION>
    <SALES_CONTRACT_EXTENSION_SECTION_DATA>
     <SALES_TRANSACTION GSESaleType="ArmsLengthSale"/>
    </SALES_CONTRACT_EXTENSION_SECTION_DATA>
   </SALES_CONTRACT_EXTENSION_SECTION></SALES_CONTRACT_EXTENSION>
  </SALES_CONTRACT>
  <PROJECT _CommonElementsDescription="Foxwood Meadows HOA - pool and park">
   <_PER_UNIT_FEE _PeriodType="Annually"/>
  </PROJECT>
 </PROPERTY>
 <VALUATION_METHODS>
  <SALES_COMPARISON>
   <RESEARCH ComparableSalesResearchedCount="40" ComparableListingsResearchedCount="12"/>
  </SALES_COMPARISON>
 </VALUATION_METHODS>
</VALUATION_RESPONSE>"""


def _extract():
    p = Path(tempfile.mkstemp(suffix=".xml")[1])
    p.write_text(_XML, encoding="utf-8")
    return extract_xml(p)


def test_comparable_count():
    assert _extract().get("comparable_count").value == "40"


def test_seller_is_owner():
    assert _extract().get("is_seller_owner_of_record").value == "Y"


def test_subject_sale_type():
    # from SALES_TRANSACTION (subject), not a COMPARISON_DETAIL comp copy
    assert _extract().get("sale_type").value == "ArmsLengthSale"


def test_project_hoa_fields():
    fs = _extract()
    assert fs.get("hoa_period").value == "Annually"
    assert fs.get("common_elements_description").value.startswith("Foxwood Meadows")
