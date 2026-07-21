"""Phase 1: version-namespaced field registry + form-aware N/A gate.

The registry (not the LLM) decides applicability — a check whose field(s) do not
exist on the detected form auto-N/As. The gate is FAIL-SAFE: unknown form, no
labels, or any label not positively-absent → NOT gated (never a guessed N/A)."""

from __future__ import annotations

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.language.packet_v2 import Sources
from app.language.run import _form_not_applicable, judge_items
from app.language.spec import CompiledItem
from app.language.verdict_v2 import StatusV2
from app.registry import registry


def _fs(**vals) -> ExtractedFieldSet:
    fs = ExtractedFieldSet()
    for name, v in vals.items():
        fs.add(ExtractedField(canonical_name=name, value=v, source=Source.XML,
                              confidence=0.97, page=1))
    return fs


def _item(item_id="X", labels=None, scope="subject"):
    return CompiledItem(item_id=item_id, check_text="the check",
                        bound_labels=labels or [], scope=scope)


# ── registry loader ───────────────────────────────────────────────────────────

def test_registry_records_absent_field_positively():
    assert registry.known_form("1004") is True
    assert registry.is_absent_on_form("unit_number", "1004") is True


def test_registry_is_fail_safe_on_unknowns():
    assert registry.is_absent_on_form("borrower_name", "1004") is False   # present field
    assert registry.is_absent_on_form("unit_number", "9999") is False     # unknown form
    assert registry.known_form("") is False
    assert registry.is_absent_on_form("", "1004") is False


# ── form-aware gate predicate ─────────────────────────────────────────────────

def test_gate_fires_when_all_labels_absent_on_form():
    src = Sources.of(_fs(form_type="1004", unit_number=""))
    assert _form_not_applicable(_item(labels=["unit_number"]), src) is True


def test_gate_does_not_fire_when_a_label_exists_on_form():
    src = Sources.of(_fs(form_type="1004"))
    # borrower_name exists on a 1004 → not all labels absent → do not N/A
    assert _form_not_applicable(_item(labels=["unit_number", "borrower_name"]), src) is False


def test_gate_does_not_fire_on_unknown_form_or_no_labels():
    assert _form_not_applicable(_item(labels=["unit_number"]),
                                Sources.of(_fs(form_type="9999"))) is False   # unknown form
    assert _form_not_applicable(_item(labels=["unit_number"]),
                                Sources.of(_fs())) is False                    # no form_type
    assert _form_not_applicable(_item(labels=[]),
                                Sources.of(_fs(form_type="1004"))) is False    # no labels


# ── end-to-end: the gate emits a deterministic N/A, never touches the LLM ──────

def test_form_absent_check_is_not_applicable_without_llm():
    fs = _fs(form_type="1004", borrower_name="Jane Doe")
    item = _item(item_id="U-1", labels=["unit_number"])
    res, _inter, _t = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["U-1"]
    assert jv.status == StatusV2.NOT_APPLICABLE
    assert jv.decided_by == "precompiled:form_gate"
    assert "field_absent_on_form" in jv.guardrails


def test_1073_condo_has_no_grid_site_line():
    # A 1073 condo sales grid has no Site line → comp_N_site_size is absent on it,
    # so EQ-63 (site size in SF/acres) is N/A on a condo but still runs on a 1004.
    assert registry.is_absent_on_form("comp_N_site_size", "1073") is True
    assert registry.is_absent_on_form("comp_N_site_size", "1004") is False
    item = _item(item_id="EQ-63", labels=["comp_N_site_size"], scope="comps")
    fs = _fs(form_type="1073")
    res, _i, _t = judge_items([item], Sources.of(fs), fs, client=None)
    assert res["EQ-63"].status == StatusV2.NOT_APPLICABLE
    assert res["EQ-63"].decided_by == "precompiled:form_gate"
