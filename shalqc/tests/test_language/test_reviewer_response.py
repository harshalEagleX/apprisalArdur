"""
Edge-to-edge tests for the reviewer response contract (the two-pane reviewer +
document auto-scroll). Locks the guarantees the frontend depends on:

  * every card carries the checklist description (item_name) + the AMC reject_text
  * evidence rows carry COORDINATES (page + bbox) and there is a primary_location
    → the document can auto-scroll when the reviewer clicks the card
  * every judged item has a STORED LLM interaction, and the card links to it
    (llm_interaction_id) — nothing is lost
  * the whole report validates against the typed OrderQCResponse contract
  * persistence round-trips item_verdicts + llm_interactions (SQLite, no server)
"""

from __future__ import annotations

import json

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.language.packet_v2 import Sources
from app.language.response_model import OrderQCResponse
from app.language.run import build_language_report, judge_items
from app.language.spec import CompiledItem
from app.llm.client import LLMCall, LLMResult


def _fs_with_coords(**vals) -> ExtractedFieldSet:
    fs = ExtractedFieldSet()
    for i, (name, v) in enumerate(vals.items()):
        # bbox is normalized page coords {x, y, w, h} (the real extractor format).
        fs.add(ExtractedField(canonical_name=name, value=v, source=Source.XML,
                              confidence=0.97, page=2,
                              bbox={"x": 0.10, "y": 0.20 + i * 0.01, "w": 0.30, "h": 0.02},
                              location_quality="exact"))
    return fs


class _FakeClient:
    """A judge that returns a canned NOT_SATISFIED with a grounded quote."""
    available = True

    def __init__(self, value_quote: str):
        self._quote = value_quote

    def complete(self, call_type, system, user, max_tokens=3500):
        payload = json.loads(user)
        verdicts = []
        for p in payload["packets"]:
            verdicts.append({
                "item_id": p["item_id"], "status": "NOT_SATISFIED",
                "expected": "Fee Simple", "found": self._quote,
                "reviewer_line": "Property rights show Leasehold; recommend reject or override.",
                "evidence": [{"label": "property_rights", "quote": self._quote}],
                "confidence": 0.95,
            })
        data = {"verdicts": verdicts}
        call = LLMCall(call_type=call_type, provider="together", model="gpt-oss-120b",
                       cached=False, ok=True, ms=42.0)
        return LLMResult(data, call, raw=json.dumps(data, ensure_ascii=False))


def _item() -> CompiledItem:
    return CompiledItem(
        item_id="EQ-62", check_text="Leasehold/Fee Simple — must be provided.",
        reject_text="Property rights not provided.", section="subject",
        item_name="Leasehold/Fee Simple", bound_labels=["property_rights"],
        scope="subject", bound_by="llm", binder_confidence=0.9, judgeable="text",
    )


def _run_one():
    fs = _fs_with_coords(property_rights="Leasehold")
    src = Sources.of(fs)
    results, interactions = judge_items([_item()], src, fs, _FakeClient("Leasehold"))
    report = build_language_report("ORD-1", "EQUITYSOLUTIONS", results, fs, gaps=[],
                                   interactions=interactions)
    return report


def test_card_carries_description_reject_and_coordinates():
    report = _run_one()
    card = report["cards"][0]
    assert card["item_name"] == "Leasehold/Fee Simple"
    assert card["reject_text"] == "Property rights not provided."
    assert card["description"] == card["check_text"]
    # coordinates for the document auto-scroll (normalized {x,y,w,h})
    ev = card["evidence"][0]
    assert ev["page"] == 2 and set(ev["bbox"]) == {"x", "y", "w", "h"}
    assert card["primary_location"]["page"] == 2
    assert card["bound_by"] == "llm" and card["binder_confidence"] == 0.9


def test_every_judged_item_has_a_linked_stored_interaction():
    report = _run_one()
    card = report["cards"][0]
    inters = report["llm_interactions"]
    assert len(inters) == 1
    ids = {i["id"] for i in inters}
    assert card["llm_interaction_id"] in ids
    rec = inters[0]
    assert rec["item_id"] == "EQ-62"
    assert rec["request"] is not None and rec["response"]["status"] == "NOT_SATISFIED"
    assert rec["raw_response"] and "NOT_SATISFIED" in rec["raw_response"]
    assert rec["provider"] == "together" and rec["model"] == "gpt-oss-120b"


def test_report_validates_against_typed_contract():
    report = _run_one()
    model = OrderQCResponse.model_validate(report)   # raises on drift
    assert model.order_id == "ORD-1"
    assert model.cards[0].evidence[0].page == 2
    assert model.llm_interactions[0].raw_response


def test_persistence_round_trip_sqlite(tmp_path, monkeypatch):
    import app.persistence.repo as repo
    # point persistence at a throwaway SQLite file, reset the lazy engine.
    monkeypatch.setattr(repo.settings, "database_url", f"sqlite:///{tmp_path/'qc.db'}", raising=False)
    repo._engine = None
    repo._engine_ready = False
    repo._Session = None

    report = _run_one()
    run_id = repo.save_run("ORD-1", "EQUITYSOLUTIONS", "hash1", "fp1", 0, report)
    assert run_id

    verdicts = repo.get_item_verdicts(run_id)
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["item_id"] == "EQ-62" and v["status"] == "NOT_SATISFIED"
    assert v["item_name"] == "Leasehold/Fee Simple"
    assert v["primary_location"]["page"] == 2
    assert v["evidence"][0]["bbox"]
    assert v["llm_interaction_id"]

    rec = repo.get_llm_interaction(v["llm_interaction_id"])
    assert rec is not None
    assert rec["item_id"] == "EQ-62"
    assert rec["response"]["status"] == "NOT_SATISFIED"
    assert "NOT_SATISFIED" in rec["raw_response"]
