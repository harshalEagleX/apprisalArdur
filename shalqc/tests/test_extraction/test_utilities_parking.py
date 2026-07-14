"""Utilities: keep the informative supplier value (string, not boolean) so the
schema gate stops dropping 'Public'/'Septic', plus a companion _present boolean.
Parking: sum the SUBJECT's CAR_STORAGE_LOCATION spaces (never a comp's)."""

import tempfile
from pathlib import Path

from app.extraction.xml_extractor import extract_xml

_XML = """<?xml version="1.0"?>
<VALUATION_RESPONSE>
 <REPORT AppraisalFormType="FNM1004"/>
 <PROPERTY>
  <STRUCTURE>
   <CAR_STORAGE>
    <CAR_STORAGE_LOCATION _Type="Garage" ParkingSpacesCount="2"/>
    <CAR_STORAGE_LOCATION _Type="Carport" ParkingSpacesCount="0"/>
    <CAR_STORAGE_LOCATION _Type="Driveway" ParkingSpacesCount="3"/>
   </CAR_STORAGE>
  </STRUCTURE>
  <SITE>
   <SITE_UTILITY _Type="Water" _PublicIndicator="Y" _NonPublicIndicator="N"/>
   <SITE_UTILITY _Type="SanitarySewer" _PublicIndicator="N" _NonPublicIndicator="Y" _NonPublicDescription="Septic"/>
   <SITE_UTILITY _Type="Gas" _PublicIndicator="N" _NonPublicIndicator="N"/>
  </SITE>
 </PROPERTY>
</VALUATION_RESPONSE>"""


def _extract():
    p = Path(tempfile.mkstemp(suffix=".xml")[1])
    p.write_text(_XML, encoding="utf-8")
    return extract_xml(p)


def test_utility_descriptor_kept():
    fs = _extract()
    assert fs.get("utilities_water").value == "Public"
    assert fs.get("utilities_sewer").value == "Septic"   # a _NonPublicDescription survives


def test_utility_present_boolean():
    fs = _extract()
    assert fs.get("utilities_water_present").value == "Yes"
    assert fs.get("utilities_sewer_present").value == "Yes"
    assert fs.get("utilities_gas_present").value == "No"  # neither public nor non-public


def test_parking_is_sum_of_subject_spaces():
    fs = _extract()
    assert fs.get("parking_space_number").value == "5"    # 2 + 0 + 3
