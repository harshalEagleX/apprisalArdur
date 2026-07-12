"""
LLM subsystem tests (Part 10) — SHALqc.md §10 / SHALqc-CORE §4.

Network-free by default: the client's httpx.post is monkeypatched, and the
tier-2 wiring uses a fake client. One opt-in live smoke test hits the real
provider only when SHALQC_LIVE_LLM=1.
"""

import os

import pytest

import app.rules  # register rules
from app.llm import validate
from app.llm.grounding import is_grounded
from app.llm.judge import classify_narrative
from app.rules.context import QCContext
from app.rules.engine import run_rules
from app.rules.verdict import Status
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source


# ── grounding ───────────────────────────────────────────────────────────────

def test_grounding_verbatim_whitespace_insensitive():
    page = "The subject sits in the  Foxtail   Meadow subdivision, a stable market."
    assert is_grounded("Foxtail Meadow subdivision", page)   # collapsed whitespace matches
    assert not is_grounded("Elmwood Heights", page)          # not present → ungrounded
    assert not is_grounded("", page)


# ── validator ───────────────────────────────────────────────────────────────

def test_validator_status_vocab_excludes_hold():
    assert validate.status_in_vocabulary("FAIL")
    assert not validate.status_in_vocabulary("HOLD")   # HOLD is intake/profile only


def test_validator_reason_plain_quality_gate():
    assert validate.reason_plain_ok("Address does not match the order form.")
    assert not validate.reason_plain_ok("short")               # < 8 chars
    assert not validate.reason_plain_ok("**bold** markdown here")  # markdown banned


def test_validator_numeric_recheck_tolerance():
    assert validate.numeric_claim_ok(17.2, 17.25)      # within 0.5%
    assert not validate.numeric_claim_ok(17.2, 25.0)   # off → fails


# ── judge (fake client) ─────────────────────────────────────────────────────

class _FakeClient:
    available = True

    def __init__(self, reply):
        self._reply = reply

    def classify(self, system, user):
        return self._reply


def test_judge_maps_class_and_grounds_quote():
    text = "Values are stable; typical marketing time is 30-60 days in this established subdivision."
    c = classify_narrative(
        _FakeClient({"class": "specific", "quote": "typical marketing time is 30-60 days"}),
        question="specific or canned?", allowed_classes=["specific", "canned"], text=text,
    )
    assert c.klass == "specific" and c.grounded is True


def test_judge_drops_ungrounded_quote():
    c = classify_narrative(
        _FakeClient({"class": "specific", "quote": "a quote that is not in the text"}),
        question="q", allowed_classes=["specific", "canned"], text="real narrative text",
    )
    assert c.klass == "specific" and c.grounded is False   # quote dropped


def test_judge_rejects_out_of_vocab_class():
    c = classify_narrative(
        _FakeClient({"class": "made_up", "quote": "x"}),
        question="q", allowed_classes=["specific", "canned"], text="text",
    )
    assert c is None


def test_judge_none_when_no_client():
    assert classify_narrative(None, "q", ["a", "b"], "t") is None


# ── tier-2 rule wiring ──────────────────────────────────────────────────────

def _ctx_with_narrative(client):
    fs = ExtractedFieldSet()
    fs.add(ExtractedField(canonical_name="neighborhood_description",
                          value="Values are stable; marketing time 30-60 days in this established area.",
                          raw_value="x", source=Source.PDF_DIGITAL, confidence=0.9, page=2))
    return QCContext(order_id="T", appraisal=fs, llm_client=client)


def _n_canned(verdicts):
    return next(v for v in verdicts if v.rule_id == "N-CANNED")


def test_tier2_runs_body_and_passes_on_specific():
    client = _FakeClient({"class": "specific", "quote": "marketing time 30-60 days"})
    ctx = _ctx_with_narrative(client)
    v = _n_canned(run_rules(ctx, llm_client=client))
    assert v.status == Status.PASS


def test_tier2_verifies_on_canned():
    client = _FakeClient({"class": "canned", "quote": "Values are stable"})
    ctx = _ctx_with_narrative(client)
    v = _n_canned(run_rules(ctx, llm_client=client))
    assert v.status == Status.VERIFY   # tier-2 ceiling, never FAIL


def test_tier2_degrades_without_client():
    ctx = _ctx_with_narrative(None)
    v = _n_canned(run_rules(ctx, llm_client=None))
    assert v.status == Status.VERIFY
    assert v.degraded_reason == "llm_unavailable"


# ── client failover + cache (monkeypatched httpx) ───────────────────────────

def test_client_failover_and_cache(monkeypatch):
    import app.llm.client as clientmod

    # force a known key config regardless of .env
    monkeypatch.setattr(clientmod.settings, "together_keys", ["k1", "k2"], raising=False)
    monkeypatch.setattr(clientmod.settings, "groq_key", "gkey", raising=False)

    calls = {"n": 0}

    class _Resp:
        def __init__(self, status, content='{"ok": true}'):
            self.status_code = status
            self._content = content
            self.text = content

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        # first Together key → 429 (failover trigger), everything after → 200
        if calls["n"] == 1:
            return _Resp(429)
        return _Resp(200)

    monkeypatch.setattr(clientmod.httpx, "post", fake_post)

    c = clientmod.LLMClient()
    c._redis = None   # disable cache for the failover leg
    res = c.complete("test", "sys", "user")
    assert res.ok and res.data == {"ok": True}
    assert calls["n"] >= 2                         # failed over past the 429
    assert c.telemetry[-1].ok and c.telemetry[-1].cached is False

    # now prove the cache path emits cached=True telemetry
    class _MemRedis:
        def __init__(self): self.store = {}
        def get(self, k): return self.store.get(k)
        def setex(self, k, ttl, v): self.store[k] = v
    c._redis = _MemRedis()
    c.complete("test2", "sys", "user")             # miss → stores
    before = calls["n"]
    r2 = c.complete("test2", "sys", "user")        # hit → no new http call
    assert r2.ok and r2.call.cached is True
    assert calls["n"] == before                    # no extra provider call on hit


# ── opt-in live smoke ───────────────────────────────────────────────────────

@pytest.mark.skipif(os.environ.get("SHALQC_LIVE_LLM") != "1",
                    reason="live LLM smoke — set SHALQC_LIVE_LLM=1 to run")
def test_live_llm_smoke():
    from app.llm.client import get_client
    c = get_client()
    assert c is not None
    data = classify_narrative(
        c, question="Is this specific or canned?", allowed_classes=["specific", "canned"],
        text="The neighborhood is stable with typical marketing times of 30 to 60 days.",
    )
    assert data is not None and data.klass in ("specific", "canned")
