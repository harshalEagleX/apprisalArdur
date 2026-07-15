"""
SHALqc-CORE tests — the judge doctrine (§0/§4), contract cap (§11), AcroForm
(§10), template/vendor (§9). Network-free (fake judge client).
"""

import app.rules as R
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.rules.verdict import Evidence, Status, Verdict, contract_cap


def _fs(**kw):
    s = ExtractedFieldSet()
    for n, (v, c) in kw.items():
        s.add(ExtractedField(canonical_name=n, value=v, raw_value=v, source=Source.XML, confidence=c, page=1))
    return s


class _FakeJudge:
    available = True

    def __init__(self, reply):
        self._reply = reply
        self.telemetry = []

    def complete(self, call_type, system, user, max_tokens=1024, reasoning_effort=None):
        class _R:
            def __init__(s, d):
                s.data = d; s.ok = True; s.call = type("C", (), {"cached": False})()
        return _R(self._reply)

    def classify(self, *a, **k):
        return None


def _s1_ctx():
    return QCContext(order_id="T",
                     appraisal=_fs(property_address=("123 Main St", 0.97)),
                     engagement=_fs(property_address=("999 Other Rd", 0.95)))


def _s1_spec():
    return [s for s in R.all_rules() if s.rule_id == "S-1"]


# ── §0/§4.2/DoD#6: verdicts traced to the C2 judge ──────────────────────────

def test_c2_grounded_fail_accepted_and_traced():
    reply = {"verdicts": [{"rule_id": "S-1", "status": "FAIL",
             "reason_plain": "The report address 123 Main St differs from the order form.",
             "evidence_quotes": [{"quote": "123 Main St", "from": "appraisal.property_address"}],
             "fields_used": ["property_address"], "confidence": 0.9, "message_key": "S-1.address_mismatch"}]}
    vs = run_rules(_s1_ctx(), rules=_s1_spec(), llm_client=_FakeJudge(reply), judge_mode=True)
    v = next(v for v in vs if v.rule_id == "S-1")
    assert v.status == Status.FAIL
    assert v.judged_by == "C2:judge_v1"           # DoD #6 traceability
    assert v.reason_plain.startswith("The report address")


def test_c2_ungrounded_fail_degraded_by_guardrail():
    reply = {"verdicts": [{"rule_id": "S-1", "status": "FAIL", "reason_plain": "addresses differ",
             "evidence_quotes": [{"quote": "THIS TEXT IS NOWHERE", "from": "appraisal.property_address"}],
             "fields_used": ["property_address"], "confidence": 0.9, "message_key": "S-1.address_mismatch"}]}
    vs = run_rules(_s1_ctx(), rules=_s1_spec(), llm_client=_FakeJudge(reply), judge_mode=True)
    v = next(v for v in vs if v.rule_id == "S-1")
    assert v.status == Status.VERIFY
    assert "ungrounded" in (v.degraded_reason or "")


def test_deterministic_path_unchanged_without_judge_mode():
    vs = run_rules(_s1_ctx(), rules=_s1_spec(), llm_client=None, judge_mode=False)
    v = next(v for v in vs if v.rule_id == "S-1")
    assert v.judged_by == ""                       # deterministic, not LLM


# ── §11 contract cap (DoD #12: contract-backed rule incapable of FAIL) ──────

def test_contract_backed_fail_capped_to_verify():
    v = Verdict(rule_id="C-2", status=Status.FAIL, evidence=[
        Evidence(field="contract_price", value="450000", source="contract", document="contract"),
    ])
    contract_cap([v])
    assert v.status == Status.VERIFY
    assert "contract_uncorroborated" in v.degraded_reason


def test_contract_fail_survives_if_appraisal_corroborates():
    v = Verdict(rule_id="C-2", status=Status.FAIL, evidence=[
        Evidence(field="contract_price", value="450000", source="contract", document="contract"),
        Evidence(field="contract_price", value="450000", source="xml", document="appraisal"),
    ])
    contract_cap([v])
    assert v.status == Status.FAIL                  # corroborated → stays FAIL


# ── §10 AcroForm alias + §9 vendor detect ───────────────────────────────────

def test_acroform_alias_maps_widget_to_canonical():
    from app.extraction.acroform import _canonical
    assert _canonical("PropertyAddress") == "property_address"
    assert _canonical("BorrowerName") == "borrower_name"
    assert _canonical("SomethingUnmapped") is None   # never guessed


def test_template_map_and_vendor_loader():
    from app.extraction import template_positions as T
    assert T.version().startswith("tpl-")
    assert T.acroform_aliases().get("propertyaddress") == "property_address"
    assert T.field_anchor("property_address")["page"] == 1


def test_acroform_fillable_pdf_yields_exact(tmp_path):
    # DoD #11: an AcroForm (fillable) PDF yields widget-sourced fields at
    # location_quality exact (widget rect IS the bbox).
    import fitz
    from app.extraction.acroform import extract_acroform
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    w = fitz.Widget()
    w.field_name = "PropertyAddress"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_value = "123 Demo St"
    w.rect = fitz.Rect(100, 100, 300, 120)
    page.add_widget(w)
    p = tmp_path / "acro.pdf"
    doc.save(str(p)); doc.close()

    fs = extract_acroform(str(p))
    ef = fs.get("property_address")
    assert ef is not None and ef.value == "123 Demo St"
    assert ef.location_quality == "exact" and ef.bbox is not None and ef.confidence == 0.95


def test_field_ownership_declared():
    # CORE §1: every field declares primary_source + secondary_source.
    from app.extraction.schema import schema_loader as S
    for f in S.all_fields():
        assert f.primary_source in ("xml", "pdf", "engagement", "contract")
        assert f.secondary_source in ("xml", "pdf", "engagement", "contract")
    assert S.get_field("neighborhood_description").primary_source == "pdf"   # narrative → PDF
    assert S.get_field("appraised_value").primary_source == "xml"            # structured → XML
