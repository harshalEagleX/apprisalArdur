"""
Extraction smoke tests against the ESTX-0007568 fixture (SHALqc.md §18
fixture discipline — a golden-file regression harness is Part 8+ and out of
scope here; these are the §1-3 acceptance checks: does each extractor run,
and does merge.py actually merge XML/PDF/engagement per the documented rules).
"""

from pathlib import Path

import pytest

from app.extraction.engagement import extract_engagement
from app.extraction.merge import run_extraction
from app.extraction.result import Source
from app.extraction.schema import schema_loader
from app.extraction.xml_extractor import extract_xml
from app.pipeline.intake import assemble_order
from tests.conftest import HAVE_FIXTURE_DOCS, requires_fixture_docs

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "ESTX-0007568"
XML_PATH = FIXTURE_DIR / "appraisal" / "7243 Foxtail Meadow Ct.xml"
PDF_PATH = FIXTURE_DIR / "appraisal" / "7243 Foxtail Meadow Ct.pdf"
ENGAGEMENT_PATH = FIXTURE_DIR / "engagement" / "EngagementLetter - 2026-07-09T203634.806.pdf"

pytestmark = requires_fixture_docs


def test_schema_loads():
    assert schema_loader.schema_version == "sch-1.0.0"
    assert len(schema_loader.all_fields()) > 100


def test_xml_extractor_finds_spine_fields():
    fs = extract_xml(XML_PATH)
    assert len(fs.found_fields()) > 300
    for name, expected in (
        ("property_address", "7243 Foxtail Meadow Ct"),
        ("city", "Humble"),
        ("state", "TX"),
        ("zip_code", "77338"),
    ):
        ef = fs.get(name)
        assert ef is not None and ef.found, f"{name} not found"
        assert ef.value == expected
        assert ef.confidence == 0.97
        assert ef.source == Source.XML


def test_engagement_extractor_finds_order_form_fields():
    fs = extract_engagement(ENGAGEMENT_PATH)
    assert fs.get("borrower_name") is not None
    assert fs.get("lender_name") is not None
    for _name, ef in fs:
        assert ef.confidence == 0.92
        assert ef.source == Source.ENGAGEMENT


def test_intake_classifies_the_fixture_folder():
    order = assemble_order(FIXTURE_DIR)
    assert order.status == "OK", order.hold_reason
    assert order.appraisal_pdf == PDF_PATH
    assert order.xml == XML_PATH
    assert order.engagement_letter == ENGAGEMENT_PATH
    # Folder boundary = order boundary (§3.1.4) — the fixture dir name is used
    # as the fallback order_id only because no manifest.json is present.
    assert order.order_id == "ESTX-0007568"


def test_merge_prefers_xml_and_retains_conflicts():
    """SHALqc.md §3.2 step 9: XML wins ties; a materially-disagreeing loser is
    kept as a conflict on the winner, never discarded."""
    fs = run_extraction(appraisal_pdf=PDF_PATH, xml_path=XML_PATH, engagement_letter=ENGAGEMENT_PATH)
    assert len(fs.found_fields()) > 400

    address = fs.get("property_address")
    assert address is not None and address.found
    assert address.source == Source.XML  # XML wins over engagement's "Mdw Ct" spelling
    assert address.confidence == 0.97
    # Engagement's differently-spelled address must survive as a conflict, not
    # be silently dropped (P3).
    assert any(c.source == Source.ENGAGEMENT for c in address.conflicts)


def test_xml_wins_even_against_higher_confidence(  ):
    """XML PRIORITY (user directive): the authoritative MISMO XML wins over any other
    source regardless of confidence; the loser is kept as a conflict, never dropped."""
    from app.extraction.merge import _merge_field
    from app.extraction.result import ExtractedField
    merged = {}
    # a non-XML source lands first with HIGHER confidence than XML's fixed 0.97
    _merge_field(merged, ExtractedField(canonical_name="city", value="Dallas",
                                        source=Source.PDF_DIGITAL, confidence=0.99, page=1))
    _merge_field(merged, ExtractedField(canonical_name="city", value="Humble",
                                        source=Source.XML, confidence=0.97, page=2))
    won = merged["city"]
    assert won.source == Source.XML and won.value == "Humble"      # XML wins anyway
    assert any(c.source == Source.PDF_DIGITAL and c.value == "Dallas" for c in won.conflicts)


def test_merge_never_raises_on_a_missing_document():
    """P6 graceful degradation — a missing engagement letter must not crash
    the merge; the order simply proceeds without engagement-sourced fields."""
    fs = run_extraction(appraisal_pdf=PDF_PATH, xml_path=XML_PATH, engagement_letter=None)
    assert len(fs.found_fields()) > 300
