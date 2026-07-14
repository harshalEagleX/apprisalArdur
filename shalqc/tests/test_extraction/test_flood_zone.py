"""Flood-zone extraction: the zone code must be stored LITERALLY ('X' is a
minimal-risk zone, not a boolean/flag), and ST-8 needs zone + map number + map
date all present even outside an SFHA. The map number/date were previously
dropped; the GSE extension copy is the fallback."""

import tempfile
from pathlib import Path

from app.extraction.xml_extractor import extract_xml

_XML = """<?xml version="1.0"?>
<VALUATION_RESPONSE>
 <REPORT AppraisalFormType="FNM1004"/>
 <PROPERTY>
  <SITE _ZoningComplianceType="Legal">
   <FLOOD_ZONE NFIPFloodZoneIdentifier="X" NFIPMapIdentifier="06061C0758H"
               NFIPMapPanelDate="2018-11-02" SpecialFloodHazardAreaIndicator="N">
    <FLOOD_ZONE_EXTENSION><FLOOD_ZONE_EXTENSION_SECTION>
     <FLOOD_ZONE_EXTENSION_SECTION_DATA>
      <FLOOD_ZONE_INFORMATION GSEFEMASpecialFloodHazardAreaIndicator="N"
        GSENFIPFloodZoneIdentifier="X" GSEFEMAFloodMapIdentifier="06061C0758H"/>
     </FLOOD_ZONE_EXTENSION_SECTION_DATA>
    </FLOOD_ZONE_EXTENSION_SECTION></FLOOD_ZONE_EXTENSION>
   </FLOOD_ZONE>
  </SITE>
 </PROPERTY>
</VALUATION_RESPONSE>"""


def _extract(xml_text):
    p = Path(tempfile.mkstemp(suffix=".xml")[1])
    p.write_text(xml_text, encoding="utf-8")
    return extract_xml(p)


def test_zone_x_is_literal_not_boolean():
    fs = _extract(_XML)
    assert fs.get("fema_flood_zone").value == "X"           # zone code, kept literal
    assert fs.get("fema_flood_hazard").value == "N"         # the SFHA flag, separate


def test_map_number_and_date_extracted():
    fs = _extract(_XML)
    assert fs.get("fema_map_number").value == "06061C0758H"
    assert fs.get("fema_map_date").value == "2018-11-02"


def test_map_number_falls_back_to_gse_extension():
    # primary NFIPMapIdentifier absent → use the UAD GSE extension copy
    xml = _XML.replace('NFIPMapIdentifier="06061C0758H"', "")
    fs = _extract(xml)
    assert fs.get("fema_map_number").value == "06061C0758H"
