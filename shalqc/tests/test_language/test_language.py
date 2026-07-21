"""
Acceptance-invariant tests for the language-driven judgment path (final_
shalqccore.md §10). These run fully offline (no live LLM) and lock the structural
guarantees the doctrine promises: no SATISFIED-on-nothing, no ungrounded/low-conf
NOT_SATISFIED, binder can only bind real labels, visual items never call the LLM.
"""

from __future__ import annotations

import pytest

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.language import hints as H
from app.language import label_dictionary as LD
from app.language.packet_v2 import Sources, build_packet
from app.language.spec import CompiledItem
from app.language.verdict_v2 import StatusV2
from app.language.validate_v2 import validate


def _fs(**vals) -> ExtractedFieldSet:
    fs = ExtractedFieldSet()
    for name, v in vals.items():
        fs.add(ExtractedField(canonical_name=name, value=v, source=Source.XML,
                              confidence=0.97, page=3, location_quality="exact"))
    return fs


def _item(**kw) -> CompiledItem:
    base = dict(item_id="XX-1", check_text="the check", bound_labels=[], scope="subject")
    base.update(kw)
    return CompiledItem(**base)


# ── packet builder (§4.1) ─────────────────────────────────────────────────────

def test_absent_labels_are_names_only_not_null_objects():
    fs = _fs(property_address="123 Main St")
    src = Sources.of(fs)
    item = _item(bound_labels=["property_address", "flood_zone_id"], scope="subject")
    p = build_packet(item, src)
    assert "property_address" in p.values
    assert "flood_zone_id" in p.absent_labels           # name only
    assert "flood_zone_id" not in p.values              # never a null object


def test_comp_labels_expand_from_present_comps_only():
    fs = _fs(comp_1_sale_price="250000", comp_2_sale_price="260000",
             comp_1_gla="1800", comp_2_gla="1900")
    src = Sources.of(fs)
    item = _item(bound_labels=["comp_N_gla"], scope="comps")
    p = build_packet(item, src)
    assert set(["comp_1_gla", "comp_2_gla"]) <= set(p.values)
    assert "comp_3_gla" not in p.values and "comp_3_gla" not in p.absent_labels
    cc = next(h for h in p.computed_hints if h["hint"] == "comp_count_present")
    assert cc["value"] == 2                              # S-10: count at any N


# ── hints (§4.1) ──────────────────────────────────────────────────────────────

def test_equal_after_norm_token_subset_1004_vs_1004fha():
    # acceptance #4: 1004 vs 1004 FHA must not read as a mismatch.
    vals = {"form_type": "1004", "engagement.form_type": "1004 FHA"}
    assert H.equal_after_norm(vals, "form_type", "engagement.form_type") is True


# ── validator degrade ladder (§4.4) ───────────────────────────────────────────

def _packet_with(values_present, absent=None, hints=None, check="c", reject="reject me"):
    from app.language.packet_v2 import Packet
    values = {k: {"v": v, "page": 3, "lq": "exact"} for k, v in values_present.items()}
    return Packet(item_id="XX-1", check_text=check, reject_text=reject, values=values,
                  absent_labels=absent or [], computed_hints=hints or [],
                  section_snapshot=None, source_notes={}, scope="subject")


def test_not_satisfied_low_confidence_degrades_to_review():
    pkt = _packet_with({"comp_1_gla": "1800"})
    raw = {"item_id": "XX-1", "status": "NOT_SATISFIED", "expected": "x", "found": "1800",
           "reviewer_line": "expected x found 1800 please reject or override.",
           "evidence": [{"label": "comp_1_gla", "quote": "1800"}], "confidence": 0.3}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.REVIEW
    assert "low_judge_confidence" in jv.guardrails


def test_not_satisfied_ungrounded_quote_degrades_to_review():
    pkt = _packet_with({"comp_1_gla": "1800"})
    raw = {"item_id": "XX-1", "status": "NOT_SATISFIED", "expected": "x", "found": "9999",
           "reviewer_line": "expected x found 9999 please reject or override.",
           "evidence": [{"label": "comp_1_gla", "quote": "NOT ON PAGE"}], "confidence": 0.9}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.REVIEW
    assert "ungrounded" in jv.guardrails


def test_not_satisfied_relying_on_absent_label_capped_at_review():
    pkt = _packet_with({"property_address": "123 Main"}, absent=["flood_zone_id"])
    raw = {"item_id": "XX-1", "status": "NOT_SATISFIED", "expected": "flood zone present",
           "found": "flood_zone_id is missing", "confidence": 0.95,
           "reviewer_line": "flood zone appears missing please reject or override.",
           "evidence": [{"label": "property_address", "quote": "123 Main"}]}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.REVIEW
    assert "absent_data" in jv.guardrails


def test_clean_not_satisfied_survives_with_reject_wording():
    hints = [{"hint": "comp_count_present", "value": 4, "labels": []}]
    pkt = _packet_with({"comp_1_sale_price": "250000"}, hints=hints, reject="only 4 comps")
    raw = {"item_id": "XX-1", "status": "NOT_SATISFIED", "expected": "6 comparables",
           "found": "4 comparables", "confidence": 0.9,
           "reviewer_line": "Expected 6 comparables; found 4. Recommend reject.",
           "evidence": [{"label": "comp_1_sale_price", "quote": "250000"}]}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.NOT_SATISFIED
    assert jv.suggest_reject_wording == "only 4 comps"


def test_reject_wording_dropped_when_not_a_reject():
    pkt = _packet_with({"comp_1_sale_price": "250000"}, reject="reject wording")
    raw = {"item_id": "XX-1", "status": "SATISFIED", "found": "ok", "confidence": 0.9,
           "reviewer_line": "Looks satisfied for this check.", "evidence": []}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.SATISFIED
    assert jv.suggest_reject_wording is None


def test_bad_status_degrades_to_review():
    pkt = _packet_with({"x": "1"})
    raw = {"item_id": "XX-1", "status": "REJECTED", "reviewer_line": "x", "evidence": []}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.REVIEW and "bad_status" in jv.guardrails


def test_judge_unstable_stamps_guardrail(monkeypatch):
    # B3: a self-consistency downgrade carries judge_unstable → durable guardrail on
    # the card even after the reviewer_line is re-synthesized for a REVIEW verdict.
    pkt = _packet_with({"comp_1_gla": "1800"})
    raw = {"item_id": "XX-1", "status": "REVIEW", "expected": "x", "found": "1800",
           "reviewer_line": "Judge verdict was unstable across 3 runs — please verify.",
           "evidence": [{"label": "comp_1_gla", "quote": "1800"}], "confidence": 0.67,
           "judge_unstable": {"samples": ["SATISFIED", "REVIEW", "SATISFIED"],
                              "majority": "SATISFIED"}}
    jv = validate(raw, pkt, _item())
    assert jv.status == StatusV2.REVIEW
    assert any(g.startswith("judge_unstable:") for g in jv.guardrails)
    assert "SATISFIEDx2" in "".join(jv.guardrails)


# ── §4: the LLM reports findings, it never issues the reviewer's decision ──────

def test_directive_reviewer_line_is_neutralized():
    pkt = _packet_with({"comp_1_sale_price": "250000"}, hints=[
        {"hint": "comp_count_present", "value": 4, "labels": []}], reject="only 4 comps")
    raw = {"item_id": "XX-1", "status": "NOT_SATISFIED", "expected": "6 comparables",
           "found": "4 comparables", "confidence": 0.9,
           "reviewer_line": "The appraiser must revise the report and add a comment; recommend reject.",
           "evidence": [{"label": "comp_1_sale_price", "quote": "250000"}]}
    jv = validate(raw, pkt, _item())
    assert "directive_language" in jv.guardrails
    line = jv.reviewer_line.lower()
    for banned in ("revise", "recommend reject", "add a comment", "must"):
        assert banned not in line
    # 2026-07-20 tone contract: the synthesized line asks softly and still
    # carries the expected/found facts — never a bare imperative "verify".
    assert "could you please" in line
    assert "6 comparables" in line and "4 comparables" in line
    # the reject authority still lives in the rule-authored wording, intact
    assert jv.suggest_reject_wording == "only 4 comps"


def test_neutral_finding_line_is_left_alone():
    pkt = _packet_with({"comp_1_sale_price": "250000"})
    raw = {"item_id": "XX-1", "status": "REVIEW", "expected": "6 comps", "found": "4",
           "confidence": 0.5, "reviewer_line": "Expected 6 comparables; found 4. Please verify.",
           "evidence": [{"label": "comp_1_sale_price", "quote": "250000"}]}
    jv = validate(raw, pkt, _item())
    assert "directive_language" not in jv.guardrails
    assert jv.reviewer_line == "Expected 6 comparables; found 4. Please verify."


# ── binder drift guard (§3) ───────────────────────────────────────────────────

def test_binder_binds_only_known_labels():
    from app.language.compiler import _compile_item
    row = {"item_id": "SCA-X", "section": "sales_comparison",
           "check_text": "comp gla must be reported", "reject_text": None,
           "check_type": "same_section",
           "sources": [{"doc": "appraisal", "fields": ["comp_N_gla", "totally_fake_field"]}]}
    item = _compile_item(row, client=None)
    assert "comp_N_gla" in item.bound_labels
    assert all(LD.is_known(l) for l in item.bound_labels)   # fake field dropped


def test_visual_item_compiles_to_constant_never_packeted():
    from app.language.compiler import _compile_item
    from app.language.run import judge_items
    row = {"item_id": "CAT-124", "section": "improvements", "check_type": "cross_modal",
           "check_text": "Subject photos: front, rear, street present", "sources": []}
    item = _compile_item(row, client=None)
    assert item.judgeable == "visual" and item.scope == "visual"
    # judge_items must never build a packet for it (client=None would otherwise
    # fallback); it should be a precompiled visual card.
    res, _, _ = judge_items([item], Sources.of(_fs()), _fs(), client=None)
    jv = res["CAT-124"]
    assert jv.decided_by == "precompiled" and jv.card_group() == "manual_visual"


# ── S-6 / S-9 fallbacks never SATISFIED ───────────────────────────────────────

def test_no_llm_fallback_is_review_never_satisfied():
    from app.language.run import judge_items
    fs = _fs(property_address="123 Main St")
    item = _item(item_id="S-1", bound_labels=["property_address"], scope="subject",
                 judgeable="text")
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["S-1"]
    assert jv.status == StatusV2.REVIEW
    assert jv.status != StatusV2.SATISFIED
    assert "llm_unavailable" in jv.guardrails
    assert "property_address" in jv.values           # packet attached for eyeball


# ── AnnexB Part 2: cross-section conditionals ─────────────────────────────────

def test_compiler_does_not_autogenerate_conditional_blocks():
    # 2026-07-14: the compiler no longer hallucinates a condition/consequence graph
    # from an "if … then …" sentence. The trigger stays in check_text (which the
    # judge reads); a machine-readable gate is authored by hand in an override, not
    # generated. This deletes the entire "condition label absent → CANNOT_EVALUATE"
    # noise class at its source.
    from app.language.compiler import _compile_item
    row = {"item_id": "IMP-12", "section": "improvements", "check_type": "same_section",
           "check_text": ("If the actual age of the property exceeds 30 years, the "
                          "improvement section must describe updates and the effective "
                          "age must be supported."),
           "sources": []}
    item = _compile_item(row, client=None)
    assert item.conditional is None


def test_conditional_packet_carries_condition_block_and_derived_age():
    fs = _fs(year_built="1942", condition_comments="kitchen and bath fully remodeled 2020",
             effective_age="25")
    item = _item(item_id="IMP-12", bound_labels=[], scope="cross_section",
                 conditional={"condition_labels": ["year_built"],
                              "consequence_labels": ["condition_comments", "effective_age"]})
    p = build_packet(item, Sources.of(fs))
    assert p.conditional and "year_built" in p.conditional["condition_labels"]
    age_hint = next(h for h in p.computed_hints if h["hint"] == "derived_age_from_year_built")
    assert age_hint["value"] == __import__("datetime").date.today().year - 1942


# ── P3(a): deterministic trigger gate — condition absent → NA, no LLM call ─────

def test_trigger_not_fired_gates_to_not_applicable_without_llm():
    from app.language.run import judge_items
    # condition label (fha_case_number) is ABSENT → the trigger provably did not
    # fire → deterministic NOT_APPLICABLE, never sent to the (None) client.
    fs = _fs(property_address="123 Main St")
    item = _item(item_id="C-1", check_text="If FHA, the case number must appear.",
                 bound_labels=[], scope="cross_section",
                 conditional={"condition_labels": ["fha_case_number"],
                              "consequence_labels": ["property_address"]})
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["C-1"]
    assert jv.status == StatusV2.NOT_APPLICABLE
    assert jv.decided_by == "precompiled:trigger_gate"
    assert "trigger_not_fired" in jv.guardrails


def test_contract_section_is_not_applicable_on_a_refinance():
    from app.language.run import judge_items
    # A contract-section check has no sale contract to evaluate on a refinance →
    # deterministic NOT_APPLICABLE, never sent to the (None) client.
    fs = _fs(transaction_type="Refinance", property_address="123 Main St")
    item = _item(item_id="EQ-15", check_text="Contract Price & Date of Contract",
                 section="contract", bound_labels=["contract_price", "contract_date"])
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["EQ-15"]
    assert jv.status == StatusV2.NOT_APPLICABLE
    assert jv.decided_by == "precompiled:transaction_gate"
    assert "refinance_no_contract" in jv.guardrails


def test_contract_section_still_judged_on_a_purchase():
    from app.language.run import judge_items
    # Same check on a PURCHASE is NOT gated (client=None → llm_unavailable REVIEW,
    # proving it was not deterministically N/A'd).
    fs = _fs(transaction_type="Purchase", contract_price="500000")
    item = _item(item_id="EQ-15", check_text="Contract Price & Date of Contract",
                 section="contract", bound_labels=["contract_price", "contract_date"])
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    assert res["EQ-15"].status != StatusV2.NOT_APPLICABLE


def test_non_contract_section_never_transaction_gated_on_refinance():
    from app.language.run import judge_items
    # A SUBJECT-section check must still be evaluated on a refinance.
    fs = _fs(transaction_type="Refinance", borrower_name="Jane Doe")
    item = _item(item_id="EQ-1", check_text="Owner of public record",
                 section="subject", bound_labels=["borrower_name"])
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    assert res["EQ-1"].status != StatusV2.NOT_APPLICABLE


def test_trigger_fired_when_condition_present_is_left_to_judge():
    from app.language.run import judge_items
    # condition label present with a real value → NOT gated; with client=None it
    # falls back to llm_unavailable REVIEW (proves it was NOT deterministically NA'd).
    fs = _fs(fha_case_number="123-4567890", property_address="123 Main St")
    item = _item(item_id="C-2", check_text="If FHA, the case number must appear.",
                 bound_labels=[], scope="cross_section",
                 conditional={"condition_labels": ["fha_case_number"],
                              "consequence_labels": ["property_address"]})
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["C-2"]
    assert jv.status == StatusV2.REVIEW
    assert jv.decided_by != "precompiled:trigger_gate"


# ── P3(b) / F9: listing comps carry no settlement date — hint exempts them ─────

def test_listing_comp_hint_flags_active_pending_listings():
    h = H.compute_hints(
        {"comp_1_sale_price": "500000", "comp_1_listing_status": "Settled Sale",
         "comp_2_sale_price": "0", "comp_2_listing_status": "Active Listing",
         "comp_3_sale_price": "0", "comp_3_sale_type": "Pending"},
        ["comp_1_sale_price", "comp_2_sale_price", "comp_3_sale_price"])
    flagged = next((x for x in h if x["hint"].startswith("listing_comps")), None)
    assert flagged is not None
    assert flagged["value"] == [2, 3]        # comp 1 settled, comps 2 & 3 are listings


def test_no_listing_hint_when_all_settled():
    h = H.compute_hints(
        {"comp_1_sale_price": "500000", "comp_1_listing_status": "Settled Sale"},
        ["comp_1_sale_price"])
    assert not any(x["hint"].startswith("listing_comps") for x in h)


def test_listing_hint_uad_date_grammar_contract_only_is_exempt():
    # 445 Sparrow (F9): comp 6 "c06/26" is contract-only (no settlement "s") →
    # not settled → exempt; comp 7 "Active"; comps 1-5 settled ("s..;c..").
    vals = {f"comp_{i}_sale_price": "1" for i in range(1, 8)}
    vals.update({
        "comp_1_sale_date": "s06/26;c05/26", "comp_2_sale_date": "s05/26;c02/26",
        "comp_3_sale_date": "s06/26;c04/26", "comp_4_sale_date": "s01/26;c11/25",
        "comp_5_sale_date": "s09/25;c08/25", "comp_6_sale_date": "c06/26",
        "comp_7_sale_date": "Active",
    })
    h = H.compute_hints(vals, list(vals))
    flagged = next((x for x in h if x["hint"].startswith("listing_comps")), None)
    assert flagged is not None
    assert flagged["value"] == [6, 7]        # only the not-settled comps


# ── P8 / F11: $(000) neighborhood price scaling ───────────────────────────────

def test_price_scale_000_hint_fires_on_thousands_vs_dollars():
    h = H.compute_hints(
        {"price_low": "250", "price_high": "1450",
         "comp_1_sale_price": "1260000", "comp_2_sale_price": "980000"},
        ["price_low", "price_high", "comp_1_sale_price", "comp_2_sale_price"])
    scale = next((x for x in h if x["hint"].startswith("price_scale_000")), None)
    assert scale is not None
    assert scale["value"]["price_high"] == 1450000.0
    assert scale["value"]["price_low"] == 250000.0


def test_price_scale_000_does_not_fire_when_already_dollars():
    h = H.compute_hints(
        {"price_low": "250000", "price_high": "1450000", "comp_1_sale_price": "1260000"},
        ["price_low", "price_high", "comp_1_sale_price"])
    assert not any(x["hint"].startswith("price_scale_000") for x in h)


# ── AnnexB Part 3 Stage A: narrative pointer guard ────────────────────────────

def test_narrative_classify():
    from app.language import narrative as NAR
    assert NAR.classify("See attached addenda for details") == "pointer"
    assert NAR.classify("RATHNASEKARA 7243 Foxtail Meadow") == "header_grab"
    assert NAR.classify("x" * 200) == "prose"
    assert NAR.classify("") == "empty"


def test_narrative_pointer_becomes_a3_review_not_judged():
    from app.language.run import judge_items
    fs = _fs(neighborhood_boundaries="See attached addenda")
    item = _item(item_id="N-1", check_text="Neighborhood description must be specific",
                 bound_labels=["neighborhood_boundaries"], scope="narrative")
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["N-1"]
    assert jv.status == StatusV2.REVIEW
    assert "narrative_pointer" in jv.guardrails
    assert jv.decided_by == "precompiled:a3"


def test_real_narrative_prose_is_not_flagged_a3():
    from app.language.run import judge_items
    fs = _fs(neighborhood_boundaries="The subject neighborhood is bounded by " + "x" * 120)
    item = _item(item_id="N-2", check_text="Neighborhood description must be specific",
                 bound_labels=["neighborhood_boundaries"], scope="narrative")
    res, _, _ = judge_items([item], Sources.of(fs), fs, client=None)
    jv = res["N-2"]
    # real prose → not an A-3 card; with no LLM it is the normal S-6 fallback.
    assert "narrative_pointer" not in jv.guardrails
    assert "llm_unavailable" in jv.guardrails


# ── native checklist (Excel-derived "new way") ────────────────────────────────

def test_native_checklist_loads_and_compiles():
    from app.language.compiler import checklist_for, load_checklist, _compile_item
    path = checklist_for("EQUITYSOLUTIONS")
    if not path.name.startswith("checklist_"):
        pytest.skip("native checklist not generated")
    rows = load_checklist(path)
    assert rows and all(r["check_text"] for r in rows)
    assert any(r["reject_text"] for r in rows)          # verbatim AMC reject wording
    # a native row compiles to a CompiledItem bound to real labels only.
    it = _compile_item(rows[0], client=None)
    assert all(LD.is_known(l) for l in it.bound_labels)


def test_native_reject_wording_flows_to_not_satisfied_card():
    # a native item's reject_text becomes the editable draft on a NOT_SATISFIED.
    item = _item(item_id="EQ-C", check_text="zip must match order form",
                 bound_labels=["zip_code"], reject_text="Zip code does not match order form.")
    from app.language.packet_v2 import Packet
    pkt = Packet(item_id="EQ-C", check_text=item.check_text, reject_text=item.reject_text,
                 values={"zip_code": {"v": "77338", "page": 1, "lq": "exact"},
                         "engagement.zip_code": {"v": "78701", "page": 1, "lq": "exact"}},
                 absent_labels=[], computed_hints=[], section_snapshot=None,
                 source_notes={}, scope="subject")
    raw = {"item_id": "EQ-C", "status": "NOT_SATISFIED", "expected": "match", "found": "77338 vs 78701",
           "confidence": 0.9, "reviewer_line": "Zip 77338 does not match order form 78701. Recommend reject.",
           "evidence": [{"label": "zip_code", "quote": "77338"}]}
    jv = validate(raw, pkt, item)
    assert jv.status == StatusV2.NOT_SATISFIED
    assert jv.suggest_reject_wording == "Zip code does not match order form."


def test_empty_packet_is_forced_review():
    from app.language.run import judge_items
    # a check bound to a comp attribute with NO comps present, subject scope so no
    # snapshot → empty packet (S-9).
    item = _item(item_id="E-1", bound_labels=["comp_N_gla"], scope="comps")
    res, _, _ = judge_items([item], Sources.of(_fs()), _fs(), client=None)
    jv = res["E-1"]
    assert jv.status == StatusV2.REVIEW
    assert "empty_packet" in jv.guardrails
