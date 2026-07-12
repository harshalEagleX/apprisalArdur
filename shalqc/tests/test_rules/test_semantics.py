"""
Significance resolver tests (sem-1.0.0) — the layer that tells the engine WHY a
blank is blank. Pure/deterministic; no LLM. Proves each resolution branch and
the hard safety rule (unevaluable condition ⇒ never EXPECTED_BLANK).
"""

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.rules import semantics as S
from app.rules.context import QCContext


def _fs(**kw):
    s = ExtractedFieldSet()
    for n, v in kw.items():
        s.add(ExtractedField(canonical_name=n, value=v, raw_value=v, source=Source.XML, confidence=0.97, page=1))
    return s


def _ctx(**appraisal):
    return QCContext(order_id="T", appraisal=_fs(**appraisal))


def test_expected_blank_contract_on_refinance():
    # refi → contract_price required_when purchase is FALSE → EXPECTED_BLANK
    ctx = _ctx(assignment_type="Refinance")
    res, _ = S.resolve("contract_price", ctx)
    assert res == S.EXPECTED_BLANK


def test_required_on_purchase():
    # purchase → contract_price required, xml-sourced + xml present → EXTRACTION_GAP
    ctx = _ctx(assignment_type="Purchase")
    res, _ = S.resolve("contract_price", ctx)
    assert res in (S.EXTRACTION_GAP, S.VERIFY_MISSING)


def test_expected_blank_basement_on_slab():
    ctx = _ctx(foundation_type="Concrete Slab")
    res, _ = S.resolve("basement_area", ctx)
    assert res == S.EXPECTED_BLANK


def test_required_basement_when_foundation_has_basement():
    ctx = _ctx(foundation_type="Full Basement")
    res, _ = S.resolve("basement_area", ctx)
    assert res != S.EXPECTED_BLANK


def test_info_missing():
    res, _ = S.resolve("amc_email", _ctx())
    assert res == S.INFO_MISSING


def test_pdf_sourced_missing_is_reviewer_verify():
    # narrative field, expected_source pdf → VERIFY_MISSING (reviewer), not engine
    res, _ = S.resolve("site_comments", _ctx())
    assert res == S.VERIFY_MISSING


def test_xml_sourced_missing_is_extraction_gap():
    # a material xml-primary field absent while XML present → engine's problem
    res, _ = S.resolve("neighborhood_name", _ctx(assignment_type="Refinance"))
    assert res == S.EXTRACTION_GAP


def test_unevaluable_condition_never_expected_blank():
    # foundation_type not present → basement condition unevaluable → VERIFY_MISSING
    ctx = _ctx()  # no foundation_type
    res, _ = S.resolve("basement_area", ctx)
    assert res == S.VERIFY_MISSING     # safety: never EXPECTED_BLANK on unknown
