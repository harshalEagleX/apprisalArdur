"""Groq LLM client — the structured-extraction "brain" (OpenAI-compatible API).

Design boundary (P-3): OCR stays non-LLM (the "eyes"); this module turns text
(or, for the vision fallback, an image) into structured JSON. It never performs
OCR. Every call is best-effort and returns None on any failure so the pipeline
degrades gracefully (P-6) — the caller keeps its deterministic result.

Two uses today:
  • text extraction  — read OCR'd grid text into structured fields (gpt-oss-120b,
    a reasoning model, so we force JSON output with a low reasoning effort).
  • vision fallback  — analyse a comp-photo image when Gemini is unavailable
    (llama-4-scout multimodal, separate key/model).
"""

from __future__ import annotations

import base64
import collections
import json
import logging
import os
import re
import threading
import time
from typing import Deque, Dict, List, Optional, Tuple

import requests

from app import config

logger = logging.getLogger(__name__)

# Rolling tokens-per-minute throttle for the extraction model. Shared across
# threads so concurrent QC jobs don't blow the budget. The vision model uses a
# separate, higher limit and is not throttled here.
_tpm_lock = threading.Lock()
_tpm_log: Deque[Tuple[float, int]] = collections.deque()

# ── Distributed TPM throttle (Scaling Phase 2 / QL-2) ──────────────────────────
# The per-process throttle below is correct for ONE process, but each Celery worker
# keeps its own counter — so N workers collectively blow the real Groq account TPM
# (a flood of 429s). A Redis token bucket shares the GROQ_TPM_LIMIT budget across
# every worker. When Redis is unavailable we fall back to the in-process throttle so
# a single process still behaves correctly (graceful degradation, P-6).
_TPM_KEY = "groq:tpm:extraction"
_redis_client = None
_redis_init = False

# Atomic token-bucket step: refill by elapsed time, allow if enough tokens, else
# report how long to wait. KEYS[1]=bucket; ARGV=now(s), rate(tok/s), cap, need.
_TPM_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cap = tonumber(ARGV[3])
local need = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = cap; ts = now end
local delta = now - ts
if delta < 0 then delta = 0 end
tokens = math.min(cap, tokens + delta * rate)
local allow = 0
local wait = 0
if tokens >= need then
  tokens = tokens - need
  allow = 1
else
  wait = (need - tokens) / rate
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, 120000)
return {allow, tostring(wait)}
"""


def _redis():
    """Lazy, cached Redis client shared with the Celery broker. Returns None (once)
    when Redis is not configured/reachable so callers fall back to the local throttle."""
    global _redis_client, _redis_init
    if _redis_init:
        return _redis_client
    _redis_init = True
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        import redis as _redislib
        client = _redislib.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)
        client.ping()
        _redis_client = client
        logger.info("Groq TPM throttle: distributed Redis token bucket active (%s)", url)
    except Exception as exc:
        logger.warning("Groq TPM throttle: Redis unavailable (%s) — using in-process throttle", exc)
        _redis_client = None
    return _redis_client


def _throttle_tpm_redis(est_tokens: int) -> Optional[float]:
    """Distributed throttle. Returns ms slept, or None if Redis is unavailable."""
    client = _redis()
    if client is None:
        return None
    limit = max(1, config.GROQ_TPM_LIMIT)
    need = min(max(1, est_tokens), limit)   # a single call can never need more than the whole budget
    rate = limit / 60.0
    slept_ms = 0.0
    try:
        for _ in range(180):  # safety cap (~ up to a few minutes of waiting)
            allow, wait_s = client.eval(_TPM_LUA, 1, _TPM_KEY, time.time(), rate, limit, need)
            if int(allow) == 1:
                return slept_ms
            sleep_for = min(max(float(wait_s), 0.05), 5.0)
            logger.info("Groq TPM budget reached (distributed %d/min); waiting %.2fs", limit, sleep_for)
            _t = time.perf_counter()
            time.sleep(sleep_for)
            slept_ms += (time.perf_counter() - _t) * 1000.0
        return slept_ms
    except Exception as exc:
        logger.warning("Distributed TPM throttle failed (%s) — falling back to in-process", exc)
        return None


def _throttle_tpm_local(est_tokens: int) -> float:
    """Per-process rolling-60s-window throttle (fallback when Redis is unavailable)."""
    limit = max(1, config.GROQ_TPM_LIMIT)
    slept_ms = 0.0
    with _tpm_lock:
        now = time.time()
        while _tpm_log and now - _tpm_log[0][0] > 60:
            _tpm_log.popleft()
        used = sum(t for _, t in _tpm_log)
        if used + est_tokens > limit and _tpm_log:
            wait = 60 - (now - _tpm_log[0][0]) + 0.5
            if wait > 0:
                logger.info("Groq TPM budget reached (%d/%d); waiting %.1fs", used, limit, wait)
                _t = time.perf_counter()
                time.sleep(min(wait, 60))
                slept_ms = (time.perf_counter() - _t) * 1000.0
            now = time.time()
            while _tpm_log and now - _tpm_log[0][0] > 60:
                _tpm_log.popleft()
        _tpm_log.append((time.time(), est_tokens))
    return slept_ms


def _throttle_tpm(est_tokens: int) -> float:
    """Block until sending `est_tokens` keeps usage under GROQ_TPM_LIMIT, shared
    across all worker processes via a Redis token bucket (Phase 2 / QL-2). Falls back
    to the per-process throttle when Redis is unavailable (P-6). Returns ms slept, so
    the caller attributes pre-wait time to the throttle (not the model)."""
    distributed = _throttle_tpm_redis(est_tokens)
    if distributed is not None:
        return distributed
    return _throttle_tpm_local(est_tokens)


def groq_extraction_available() -> bool:
    """True when LLM extraction is enabled and a text key is configured."""
    return bool(config.LLM_EXTRACTION_ENABLED and config.GROQ_API_KEY)


def groq_vision_available() -> bool:
    """True when a Groq vision key is configured (used as a vision fallback)."""
    return bool(config.GROQ_VISION_API_KEY)


def _extract_json(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def chat_json(
    messages: List[dict],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    max_tokens: int = 2048,
) -> Optional[dict]:
    """Call Groq chat-completions in JSON mode and return the parsed object.

    `reasoning_effort` is sent only when truthy (reasoning models like
    gpt-oss-120b need it; multimodal models like llama-4-scout do not).
    Returns None on any HTTP/parse error — never raises.
    """
    api_key = api_key or config.GROQ_API_KEY
    model = model or config.GROQ_MODEL
    if not api_key:
        return None
    body: Dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    eff = reasoning_effort if reasoning_effort is not None else config.GROQ_REASONING_EFFORT
    if eff:
        body["reasoning_effort"] = eff
    # Telemetry: separate throttle-wait (queue/rate-limit) from inference (model)
    # time so the admin docStats can tell a frequency problem from a size problem.
    est_tokens = 0
    throttle_ms = 0.0
    inference_ms = 0.0
    attempts = 0
    rate_limited = False
    # Throttle only the extraction model (the vision key/model has its own budget).
    if api_key == config.GROQ_API_KEY:
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        # input tokens + a realistic completion estimate (incl. reasoning), not the
        # max_tokens cap — overestimating would make the throttle wait needlessly.
        est_tokens = prompt_chars // 4 + min(max_tokens, 1500)
        throttle_ms += _throttle_tpm(est_tokens)

    def _emit_telemetry(ok: bool):
        try:
            from app.extraction import llm_telemetry
            llm_telemetry.record(llm_telemetry.LLMCall(
                span=llm_telemetry.current_span(), model=model,
                throttle_wait_ms=throttle_ms, inference_ms=inference_ms,
                attempts=attempts, rate_limited=rate_limited, ok=ok,
            ))
        except Exception:
            pass  # telemetry must never affect the LLM path (P-6)

    # Retry transient capacity/rate-limit errors with backoff (free tier is
    # token-per-minute limited); honor Retry-After when the API provides it.
    for attempt in range(3):
        attempts += 1
        try:
            _t = time.perf_counter()
            resp = requests.post(
                f"{config.GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout or config.GROQ_TIMEOUT,
            )
            inference_ms += (time.perf_counter() - _t) * 1000.0
            if resp.status_code in (429, 500, 503) and attempt < 2:
                if resp.status_code == 429:
                    rate_limited = True
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except (TypeError, ValueError):
                    wait = 0.0
                _b = time.perf_counter()
                time.sleep(min(max(wait, 2.0 * (attempt + 1)), 12.0))
                throttle_ms += (time.perf_counter() - _b) * 1000.0
                continue
            # Reasoning models intermittently fail strict JSON validation (the
            # reasoning channel leaks / truncates). Drop response_format and parse
            # the JSON object out of the free-text content on retry.
            if resp.status_code == 400 and "json_validate_failed" in resp.text and attempt < 2:
                body.pop("response_format", None)
                continue
            if resp.status_code != 200:
                logger.warning("Groq %s HTTP %s: %s", model, resp.status_code, resp.text[:200])
                _emit_telemetry(ok=False)
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            result = _extract_json(content)
            _emit_telemetry(ok=result is not None)
            return result
        except Exception as exc:  # never break the pipeline (P-6)
            logger.warning("Groq %s attempt %d failed: %s", model, attempt + 1, exc)
            if attempt < 2:
                _b = time.perf_counter()
                time.sleep(2.0 * (attempt + 1))
                throttle_ms += (time.perf_counter() - _b) * 1000.0
    _emit_telemetry(ok=False)
    return None


def assess_text(text: str, question: str) -> Optional[bool]:
    """Yes/no evaluation of free text by the LLM — the legitimate *evaluative*
    use of the model (NOT structured extraction). Returns True/False, or None
    when the model is unavailable or the answer can't be parsed (caller decides
    the conservative default)."""
    if not groq_extraction_available() or not (text or "").strip():
        return None
    data = chat_json(
        [
            {"role": "system", "content": 'Answer with ONLY a JSON object {"answer": true|false}.'},
            {"role": "user", "content": f"{question}\n\nTEXT:\n{text[:6000]}"},
        ],
        reasoning_effort="low",
        max_tokens=800,
    )
    if not data or "answer" not in data:
        return None
    a = data["answer"]
    if isinstance(a, bool):
        return a
    return str(a).strip().lower() in ("true", "yes", "1")


def vision_chat_json(image_bytes: bytes, prompt: str) -> Optional[dict]:
    """Analyse one image with the Groq vision model, returning parsed JSON.

    Used as the comp-photo fallback when Gemini is down / rate-limited.
    """
    if not groq_vision_available():
        return None
    data_uri = "data:image/png;base64," + base64.b64encode(image_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]
    return chat_json(
        messages,
        api_key=config.GROQ_VISION_API_KEY,
        model=config.GROQ_VISION_MODEL,
        reasoning_effort="",  # llama-4-scout is not a reasoning model
        max_tokens=512,
    )
