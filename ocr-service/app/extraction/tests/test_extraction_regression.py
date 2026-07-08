"""
Extraction regression tests — pin the three document extractors (appraisal PDF,
supporting MISMO XML, engagement letter) against hand-verified ground truth.

Two layers:

  1. Always-on unit tests for field_validators — fast, dependency-free. These are
     the guard against the two regressions found on 2026-07-08:
       * a duplicate-paste that put a SyntaxError in field_validators and crashed
         the ENTIRE PDF extraction path (run_full_extraction imports it);
       * validators that suppressed CORRECT values (site_area "12197 sf" read as
         non-numeric; comp net_adjustment sign dropped for MISMO magnitude+indicator
         encoding). The cardinal rule of this module is "never suppress a correct
         value" — these tests hold that line.

  2. Golden fixture tests over ocr-service/exttestfile/ — skipped automatically
     when the fixtures are not checked out (CI without the sample corpus). They
     assert field-count floors and specific verified values, and — most important —
     that running every validator over the authoritative XML sets suppresses NOTHING.

The contract file is never read (policy): only apprisal/*.pdf|xml and
engagement/EngagementLetter.pdf are exercised.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.extraction import field_validators as fv

# ── Fixtures location ────────────────────────────────────────────────────────
_TESTFILES = Path(__file__).resolve().parents[3] / "exttestfile"
_CASES = ["ESMI-0048528", "ESMI-0048541", "ESMI-0048569", "ESNV-0000872"]

# Hand-verified ground truth (445 Sparrow Way is the SCA-14 audit subject).
_XML_MIN_FIELDS = 250
_ENG_MIN_FIELDS = 12
_XML_EFFECTIVE_DATE = {
    "ESMI-0048528": "2026-07-06",
    "ESMI-0048541": "2026-07-06",
    "ESMI-0048569": "2026-07-06",
    "ESNV-0000872": "2026-07-07",
}


@dataclass
class _StubResult:
    """Minimal stand-in for ExtractionResult so validator unit tests need no pipeline."""
    value: str
    canonical_name: str = "x"

    @property
    def found(self) -> bool:
        return self.value not in (None, "", "None")


def _stub_set(pairs: dict) -> dict:
    return {k: _StubResult(str(v), k) for k, v in pairs.items()}


# ════════════════════════════════════════════════════════════════════════════
# 1. Always-on unit tests — field_validators integrity
# ════════════════════════════════════════════════════════════════════════════

def test_field_validators_module_imports_and_registers_comp_guards():
    """Guards against the SyntaxError-corruption class: the module must import and
    have the comp-grid guards registered for the subject row + all 9 comps."""
    assert callable(fv.validate_results)
    for pfx in ["subject_grid", "comp_1", "comp_9"]:
        assert f"{pfx}_quality_rating" in fv._FIELD_VALIDATORS
        assert f"{pfx}_condition_rating" in fv._FIELD_VALIDATORS
        assert f"{pfx}_age" in fv._FIELD_VALIDATORS
    for i in (1, 9):
        assert f"comp_{i}_net_adjustment" in fv._FIELD_VALIDATORS


def test_comp_quality_condition_shape_gates():
    assert fv._valid_comp_quality("Q3", {}) is True
    assert fv._valid_comp_quality("q6", {}) is True          # case-insensitive
    assert fv._valid_comp_quality("+8000", {}) is False      # adjustment bled in
    assert fv._valid_comp_quality("3ga1gd6dw", {}) is False  # garage code bled in
    assert fv._valid_comp_condition("C3", {}) is True
    assert fv._valid_comp_condition("Q3", {}) is False       # wrong code family


def test_comp_age_range_gate():
    assert fv._valid_comp_age("47", {}) is True
    assert fv._valid_comp_age("0", {}) is True
    assert fv._valid_comp_age("999", {}) is False
    assert fv._valid_comp_age("abc", {}) is False


def test_comp_net_adjustment_is_sign_aware():
    val = fv._FIELD_VALIDATORS["comp_5_net_adjustment"]
    # MISMO magnitude ("25000") + negative indicator → signed -25000 == adj-sale.
    m_neg = _stub_set({"comp_5_sale_price": 640000, "comp_5_adjusted_sale_price": 615000,
                       "comp_5_net_adj_positive": "N"})
    assert val("25000", m_neg) is True
    # Same numbers but indicator says positive → identity broken → rejected.
    m_pos = _stub_set({"comp_5_sale_price": 640000, "comp_5_adjusted_sale_price": 615000,
                       "comp_5_net_adj_positive": "Y"})
    assert val("25000", m_pos) is False
    # Literal signed value ("-48800") needs no indicator.
    m_signed = _stub_set({"comp_5_sale_price": 1260000, "comp_5_adjusted_sale_price": 1211200})
    assert val("-48800", m_signed) is True
    # Sign unknowable (no minus, no indicator) → skip, never false-flag.
    m_unknown = _stub_set({"comp_5_sale_price": 100000, "comp_5_adjusted_sale_price": 90000})
    assert val("10000", m_unknown) is True
    # Missing siblings → skip.
    assert val("-7050", {}) is True


def test_site_area_accepts_inline_unit():
    """The MISMO XML carries the unit inline; a correct value must not be suppressed."""
    assert fv._valid_site_area("12197 sf", {}) is True
    assert fv._valid_site_area("42253 sf", {}) is True
    assert fv._valid_site_area("5.00 ac", {}) is True
    assert fv._valid_site_area("0.34 acres", {}) is True
    assert fv._valid_site_area("not-a-number", {}) is False


# ════════════════════════════════════════════════════════════════════════════
# 2. Golden fixture tests — skipped when the sample corpus is absent
# ════════════════════════════════════════════════════════════════════════════

pytestmark_fixtures = pytest.mark.skipif(
    not _TESTFILES.exists(), reason="exttestfile sample corpus not checked out"
)


def _appraisal_xml(case: str):
    d = _TESTFILES / case / "apprisal"
    xmls = list(d.glob("*.xml")) + list(d.glob("*.XML"))
    return xmls[0] if xmls else None


def _engagement_pdf(case: str):
    d = _TESTFILES / case / "engagement"
    pdfs = [p for p in d.glob("*.pdf") if "engagement" in p.name.lower()] if d.exists() else []
    return pdfs[0] if pdfs else None


@pytestmark_fixtures
@pytest.mark.parametrize("case", _CASES)
def test_xml_extraction_field_floor_and_effective_date(case):
    from app.extraction.xml_extractor import extract_xml
    xml = _appraisal_xml(case)
    assert xml is not None, f"{case}: missing appraisal XML"
    rs = extract_xml(xml)
    found = {n: r.value for n, r in rs if r.found}
    assert len(found) >= _XML_MIN_FIELDS, f"{case}: only {len(found)} XML fields"
    assert found.get("effective_date") == _XML_EFFECTIVE_DATE[case]


@pytestmark_fixtures
def test_445_sparrow_comp_grid_golden():
    """The SCA-14 subject: XML must yield the hand-verified comp-1 grid values."""
    from app.extraction.xml_extractor import extract_xml
    rs = extract_xml(_appraisal_xml("ESNV-0000872"))
    f = {n: r.value for n, r in rs if r.found}
    assert f.get("comp_1_quality_rating") == "Q3"      # better than subject Q4
    assert f.get("subject_grid_quality_rating") == "Q4"
    assert f.get("comp_1_condition_rating") == "C3"
    assert f.get("comp_1_age") == "47"
    assert "Laura Brantley" in f.get("borrower_name", "")
    assert "Eric Brantley" in f.get("borrower_name", "")


@pytestmark_fixtures
@pytest.mark.parametrize("case", _CASES)
def test_engagement_extraction_field_floor(case):
    from app.extraction.engagement_extractor import extract_engagement
    eng = _engagement_pdf(case)
    assert eng is not None, f"{case}: missing engagement letter"
    rs = extract_engagement(eng, "engagement_letter")
    found = {n: r.value for n, r in rs if r.found}
    assert len(found) >= _ENG_MIN_FIELDS, f"{case}: only {len(found)} engagement fields"
    assert found.get("borrower_name")            # borrower is load-bearing for cross-doc QC


@pytestmark_fixtures
@pytest.mark.parametrize("case", _CASES)
def test_validators_suppress_nothing_on_authoritative_xml(case):
    """The data-integrity invariant: no field validator may suppress a value the
    authoritative MISMO XML produced. This is the regression guard for the whole
    module — any future validator that starts eating correct XML data fails here."""
    from app.extraction.xml_extractor import extract_xml
    rs = extract_xml(_appraisal_xml(case))
    merged = {n: r for n, r in rs if r.found}
    suppressed = fv.validate_results(merged)
    assert suppressed == 0, (
        f"{case}: {suppressed} authoritative XML value(s) wrongly suppressed"
    )
