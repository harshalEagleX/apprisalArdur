"""Groq content-hash cache (app.extraction.llm_groq.chat_json).

Verifies the cache that relieves the GROQ_TPM ceiling: an identical deterministic
call must return the stored result WITHOUT a second HTTP request, and different
inputs must miss the cache (no false sharing). Redis is not required — the test
forces the in-process fallback so it runs anywhere.
"""

import importlib
from unittest import mock

import pytest

from app.extraction import llm_groq
from app import config


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    # Force the in-process cache path (no Redis dependency) and start empty.
    monkeypatch.setattr(llm_groq, "_redis", lambda: None)
    llm_groq._local_cache.clear()
    monkeypatch.setattr(config, "GROQ_CACHE_ENABLED", True)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    yield
    llm_groq._local_cache.clear()


def _fake_response(payload='{"answer": 42}'):
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": payload}}]}
    resp.text = payload
    return resp


def test_identical_call_is_served_from_cache_without_second_http():
    msgs = [{"role": "user", "content": "extract the value"}]
    with mock.patch.object(llm_groq.requests, "post", return_value=_fake_response()) as post:
        first = llm_groq.chat_json(msgs, model="m1", reasoning_effort="low", max_tokens=100)
        second = llm_groq.chat_json(msgs, model="m1", reasoning_effort="low", max_tokens=100)
    assert first == {"answer": 42}
    assert second == first
    assert post.call_count == 1, "second identical call must hit the cache, not the model"


def test_different_messages_miss_the_cache():
    with mock.patch.object(llm_groq.requests, "post", return_value=_fake_response()) as post:
        llm_groq.chat_json([{"role": "user", "content": "A"}], model="m1")
        llm_groq.chat_json([{"role": "user", "content": "B"}], model="m1")
    assert post.call_count == 2, "distinct inputs must not share a cache entry"


def test_disabled_flag_bypasses_cache(monkeypatch):
    monkeypatch.setattr(config, "GROQ_CACHE_ENABLED", False)
    msgs = [{"role": "user", "content": "same"}]
    with mock.patch.object(llm_groq.requests, "post", return_value=_fake_response()) as post:
        llm_groq.chat_json(msgs, model="m1")
        llm_groq.chat_json(msgs, model="m1")
    assert post.call_count == 2, "cache disabled → every call hits the model"


def test_failed_result_is_not_cached():
    # A non-JSON / unparseable body returns None and must NOT be cached as a hit.
    with mock.patch.object(llm_groq.requests, "post", return_value=_fake_response("not json")) as post:
        llm_groq.chat_json([{"role": "user", "content": "x"}], model="m1")
        llm_groq.chat_json([{"role": "user", "content": "x"}], model="m1")
    assert post.call_count == 2, "a None result must not be cached"
