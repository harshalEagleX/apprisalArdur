"""
LLM subsystem tests (Part 10) — SHALqc.md §10 / SHALqc-CORE §4.

Network-free by default: the client's httpx.post is monkeypatched, and the
tier-2 wiring uses a fake client. One opt-in live smoke test hits the real
provider only when SHALQC_LIVE_LLM=1.
"""

import inspect
import io
import os
import tokenize

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


# ── client retry policy + cache (monkeypatched httpx) ───────────────────────
# 2026-07-13: Groq deleted (single-provider Together AI now, governed by
# TogetherPool). Retry policy is error-code only — 429/5xx/transport error
# retries (against the pool, which may hand back a different key); a genuine
# timeout does NOT retry (see app/llm/client.py module docstring for why).

def test_client_retries_429_same_provider(monkeypatch):
    import app.llm.client as clientmod

    # force a known key config regardless of .env
    monkeypatch.setattr(clientmod.settings, "together_keys", ["k1", "k2"], raising=False)
    c = clientmod.LLMClient()   # built AFTER the settings patch so its pool sees k1/k2

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
        # first attempt → 429 (retry trigger), everything after → 200
        if calls["n"] == 1:
            return _Resp(429)
        return _Resp(200)

    monkeypatch.setattr(clientmod.httpx, "post", fake_post)
    monkeypatch.setattr(clientmod, "_RETRY_BACKOFFS_S", (0.0, 0.0))  # no real sleep in tests

    c._redis = None            # disable cache for the retry leg
    c._file_cache_dir = None   # (and the on-disk fallback cache — persists across test runs)
    res = c.complete("test_retry_429", "sys", "user")
    assert res.ok and res.data == {"ok": True}
    assert calls["n"] >= 2                         # retried past the 429
    assert res.call.provider == "together"
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


def test_client_never_retries_on_timeout(monkeypatch):
    """A genuine timeout is a dead call, not a retry trigger — the S-6
    fallback (REVIEW llm_unavailable) is the correct, honest outcome."""
    import httpx as real_httpx
    import app.llm.client as clientmod

    monkeypatch.setattr(clientmod.settings, "together_keys", ["k1"], raising=False)
    c = clientmod.LLMClient()

    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        raise real_httpx.ReadTimeout("simulated timeout")

    monkeypatch.setattr(clientmod.httpx, "post", fake_post)
    c._redis = None
    c._file_cache_dir = None
    res = c.complete("test_no_retry_timeout", "sys", "user")
    assert not res.ok
    assert calls["n"] == 1                          # no retry on timeout
    assert c.telemetry[-1].error.startswith("timeout:")


def test_groq_fully_removed():
    """Regression guard for the 2026-07-13 removal — no stub, no dead code
    path, no config field. Explanatory comments/docstrings that reference why
    Groq was removed are fine (this codebase's own convention, e.g. the
    ocr-service-retired notes) — this checks for FUNCTIONAL remnants only:
    real code tokens (identifiers/strings used as VALUES, not prose), via
    tokenize so comments and docstrings are excluded properly."""
    from app.config import Settings, settings
    import app.llm.client as clientmod

    assert not hasattr(settings, "groq_key")
    assert not any("groq" in f.lower() for f in Settings.__dataclass_fields__)

    source = inspect.getsource(clientmod)
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    live_code_tokens = [
        tok.string for tok in tokens
        if tok.type in (tokenize.NAME, tokenize.STRING) and not _is_docstring_like(tok, source)
    ]
    assert not any("groq" in t.lower() for t in live_code_tokens), \
        "found a live (non-comment/docstring) groq reference in llm/client.py"


def _is_docstring_like(tok, source: str) -> bool:
    """A STRING token that's a module/function/class docstring (a bare string
    expression, not assigned to anything) — tokenize alone can't tell, so
    treat any multi-line triple-quoted string as prose, never a real value."""
    if tok.type != tokenize.STRING:
        return False
    return tok.string.startswith(('"""', "'''"))


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
