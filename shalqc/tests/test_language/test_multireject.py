"""Multi-reject model (2026-07-17): a check carries per-trigger fail branches.
The judge returns which branch fired; the validator emits that branch's reject
wording, honoring the hold / never_reject policy flags."""

from __future__ import annotations

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.language.packet_v2 import Sources, build_packet
from app.language.spec import CompiledItem, derive_severity
from app.language.validate_v2 import validate
from app.language.verdict_v2 import StatusV2


def _fs(**vals):
    fs = ExtractedFieldSet()
    for n, v in vals.items():
        fs.add(ExtractedField(canonical_name=n, value=v, source=Source.XML, confidence=0.9, page=1))
    return fs


def _item(**kw):
    base = dict(item_id="EQ-D", check_text="Borrower name", bound_labels=["borrower_name"],
                scope="subject")
    base.update(kw)
    return CompiledItem(**base)


BRANCHES = [
    {"trigger": "report borrower != order borrower", "reject_text": "Please correct borrower name to match order: {order_borrower}."},
    {"trigger": "co-borrower on order, absent on report", "reject_text": "Please add co-borrower name as {order_co_borrower}."},
]


# ── model ─────────────────────────────────────────────────────────────────────

def test_reject_branches_make_item_rejectable():
    assert derive_severity(None, "plain check", BRANCHES) == "rejectable"
    assert _item(reject_branches=BRANCHES).severity == "rejectable"


def test_packet_carries_reject_branches_with_ids():
    pkt = build_packet(_item(reject_branches=BRANCHES), Sources.of(_fs(borrower_name="Jane Doe")))
    js = pkt.to_json()
    assert "reject_branches" in js
    assert [b["branch_id"] for b in js["reject_branches"]] == [0, 1]
    assert js["reject_branches"][0]["trigger"].startswith("report borrower")


# ── validator: fired branch → reject wording ──────────────────────────────────

def _pkt(item, **vals):
    return build_packet(item, Sources.of(_fs(**vals)))


def test_fired_branch_wording_is_emitted_and_recorded():
    item = _item(reject_branches=BRANCHES)
    pkt = _pkt(item, borrower_name="Jane Doe")
    raw = {"item_id": "EQ-D", "status": "NOT_SATISFIED", "expected": "match order",
           "found": "borrower_name = Jane Doe", "confidence": 0.9,
           "fired_branch": 0,
           "suggest_reject_wording": "Please correct borrower name to match order: John Smith.",
           "evidence": [{"label": "borrower_name", "quote": "Jane Doe"}]}
    jv = validate(raw, pkt, item)
    assert jv.status == StatusV2.NOT_SATISFIED
    assert jv.suggest_reject_wording == "Please correct borrower name to match order: John Smith."
    assert "branch:0" in jv.guardrails


def test_never_reject_caps_at_review():
    item = _item(item_id="EQ-94", reject_branches=[], never_reject=True)
    pkt = _pkt(item, borrower_name="x")
    raw = {"item_id": "EQ-94", "status": "NOT_SATISFIED", "found": "blank",
           "confidence": 0.9, "evidence": [{"label": "borrower_name", "quote": "x"}]}
    jv = validate(raw, pkt, item)
    assert jv.status == StatusV2.REVIEW
    assert jv.suggest_reject_wording is None
    assert "never_reject" in jv.guardrails


def test_hold_escalates_without_reject_wording():
    item = _item(item_id="EQ-31", reject_branches=[
        {"trigger": "H&BU = No", "reject_text": "n/a"}], hold=True)
    pkt = _pkt(item, borrower_name="x")
    raw = {"item_id": "EQ-31", "status": "NOT_SATISFIED", "found": "H&BU No",
           "confidence": 0.9, "fired_branch": 0,
           "suggest_reject_wording": "should not surface",
           "evidence": [{"label": "borrower_name", "quote": "x"}]}
    jv = validate(raw, pkt, item)
    assert jv.status == StatusV2.NOT_SATISFIED          # still actionable
    assert jv.suggest_reject_wording is None            # escalate, no appraiser reject
    assert "hold_escalate" in jv.guardrails
