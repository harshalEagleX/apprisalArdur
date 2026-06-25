"""LLM client — structured-extraction "brain" (OpenAI-compatible API).

Provider priority:
  1. Together AI (primary) — two API keys used in round-robin for async batching.
     Each key has its own Redis TPM token bucket so both keys run simultaneously.
  2. Groq (fallback) — used when Together is unconfigured or exhausts all retries.

Design boundary (P-3): OCR stays non-LLM (the "eyes"); this module turns text
(or, for the vision fallback, an image) into structured JSON. It never performs
OCR. Every call is best-effort and returns None on any failure so the pipeline
degrades gracefully (P-6) — the caller keeps its deterministic result.

Two uses today:
  • text extraction  — read OCR'd grid text into structured fields.
  • vision fallback  — analyse a comp-photo image when Gemini is unavailable
    (llama-4-scout multimodal via Groq, separate key/model).
"""

from __future__ import annotations

import base64
import collections
import hashlib
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

# ── TPM token-bucket Redis keys ─────────────────────────────────────────────────
# Each key slot gets its own bucket so the two Together keys run concurrently.
_GROQ_TPM_KEY = "groq:tpm:extraction"
_TOGETHER_TPM_KEY_1 = "together:tpm:key1"
_TOGETHER_TPM_KEY_2 = "together:tpm:key2"

# Per-process in-process throttle fallback (single deque shared by all buckets —
# only used when Redis is unavailable, so one process at a time is fine).
_tpm_lock = threading.Lock()
_tpm_log: Deque[Tuple[float, int]] = collections.deque()

# ── Together AI key rotation ────────────────────────────────────────────────────
_together_key_idx = 0
_together_key_lock = threading.Lock()

# ── Distributed TPM throttle (Scaling Phase 2 / QL-2) ──────────────────────────
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

_redis_client = None
_redis_init = False


def _redis():
    """Lazy, cached Redis client. Returns None when Redis is not reachable."""
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
        logger.info("LLM TPM throttle: distributed Redis token bucket active (%s)", url)
    except Exception as exc:
        logger.warning("LLM TPM throttle: Redis unavailable (%s) — using in-process throttle", exc)
        _redis_client = None
    return _redis_client


def _throttle_tpm_redis(est_tokens: int, tpm_key: str, limit: int) -> Optional[float]:
    """Distributed throttle for a named token bucket. Returns ms slept, or None if Redis unavailable."""
    client = _redis()
    if client is None:
        return None
    limit = max(1, limit)
    need = min(max(1, est_tokens), limit)
    rate = limit / 60.0
    slept_ms = 0.0
    try:
        for _ in range(180):
            allow, wait_s = client.eval(_TPM_LUA, 1, tpm_key, time.time(), rate, limit, need)
            if int(allow) == 1:
                return slept_ms
            sleep_for = min(max(float(wait_s), 0.05), 5.0)
            logger.info("LLM TPM budget reached (bucket=%s, %d/min); waiting %.2fs", tpm_key, limit, sleep_for)
            _t = time.perf_counter()
            time.sleep(sleep_for)
            slept_ms += (time.perf_counter() - _t) * 1000.0
        return slept_ms
    except Exception as exc:
        logger.warning("Distributed TPM throttle failed (%s) — falling back to in-process", exc)
        return None


def _throttle_tpm_local(est_tokens: int, limit: int) -> float:
    """Per-process rolling-60s-window throttle (fallback when Redis is unavailable)."""
    limit = max(1, limit)
    slept_ms = 0.0
    with _tpm_lock:
        now = time.time()
        while _tpm_log and now - _tpm_log[0][0] > 60:
            _tpm_log.popleft()
        used = sum(t for _, t in _tpm_log)
        if used + est_tokens > limit and _tpm_log:
            wait = 60 - (now - _tpm_log[0][0]) + 0.5
            if wait > 0:
                logger.info("LLM TPM budget reached (%d/%d); waiting %.1fs", used, limit, wait)
                _t = time.perf_counter()
                time.sleep(min(wait, 60))
                slept_ms = (time.perf_counter() - _t) * 1000.0
            now = time.time()
            while _tpm_log and now - _tpm_log[0][0] > 60:
                _tpm_log.popleft()
        _tpm_log.append((time.time(), est_tokens))
    return slept_ms


def _throttle_tpm(est_tokens: int, *, tpm_key: str, limit: int) -> float:
    """Block until sending `est_tokens` keeps usage under `limit` in the named bucket.
    Shared across worker processes via Redis; falls back to per-process throttle (P-6)."""
    distributed = _throttle_tpm_redis(est_tokens, tpm_key, limit)
    if distributed is not None:
        return distributed
    return _throttle_tpm_local(est_tokens, limit)


# ── Together AI helpers ─────────────────────────────────────────────────────────

# Retryable HTTP status codes per Together AI error documentation.
# 524 = Cloudflare timeout, 529 = server error — both transient.
_TOGETHER_RETRYABLE = frozenset({429, 500, 503, 504, 524, 529})


def together_extraction_available() -> bool:
    """True when Together AI is enabled and at least one key is configured."""
    return bool(
        config.LLM_EXTRACTION_ENABLED
        and (config.TOGETHER_API_KEY_1 or config.TOGETHER_API_KEY_2)
    )


def _next_together_slot() -> Tuple[str, str]:
    """Round-robin across configured Together key slots.
    Returns (api_key, tpm_redis_key); empty strings when no keys are configured."""
    global _together_key_idx
    slots = []
    if config.TOGETHER_API_KEY_1:
        slots.append((config.TOGETHER_API_KEY_1, _TOGETHER_TPM_KEY_1))
    if config.TOGETHER_API_KEY_2:
        slots.append((config.TOGETHER_API_KEY_2, _TOGETHER_TPM_KEY_2))
    if not slots:
        return ("", "")
    with _together_key_lock:
        idx = _together_key_idx % len(slots)
        _together_key_idx += 1
    return slots[idx]


# ── Groq helpers ────────────────────────────────────────────────────────────────

def groq_extraction_available() -> bool:
    """True when LLM extraction is enabled and a Groq text key is configured."""
    return bool(config.LLM_EXTRACTION_ENABLED and config.GROQ_API_KEY)


def groq_vision_available() -> bool:
    """True when a Groq vision key is configured (used as a vision fallback)."""
    return bool(config.GROQ_VISION_API_KEY)


# ── JSON parsing ────────────────────────────────────────────────────────────────

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


# ── Content-hash response cache ─────────────────────────────────────────────────
# temperature=0 → deterministic → safe to cache. Relieves the TPM ceiling: an
# identical call (same model + messages + params) returns the stored result for
# zero tokens. Redis-backed (shared across Celery workers); bounded in-process
# dict is the fallback when Redis is unavailable (P-6).
_CACHE_VERSION = "1"
_CACHE_PREFIX = "llm:cache:"
_local_cache: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
_LOCAL_CACHE_MAX = 512


def _cache_key(model: str, messages: List[dict], eff, max_tokens: int) -> str:
    canonical = json.dumps(
        {"v": _CACHE_VERSION, "model": model, "messages": messages,
         "eff": eff or "", "max_tokens": max_tokens},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return _CACHE_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[dict]:
    client = _redis()
    if client is not None:
        try:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("LLM cache get failed (%s) — continuing uncached", exc)
    val = _local_cache.get(key)
    if val is not None:
        _local_cache.move_to_end(key)
    return val


def _cache_set(key: str, value: dict) -> None:
    client = _redis()
    if client is not None:
        try:
            client.set(key, json.dumps(value), ex=max(1, config.GROQ_CACHE_TTL_SECONDS))
            return
        except Exception as exc:
            logger.debug("LLM cache set failed (%s) — using in-process cache", exc)
    _local_cache[key] = value
    _local_cache.move_to_end(key)
    while len(_local_cache) > _LOCAL_CACHE_MAX:
        _local_cache.popitem(last=False)


# ── Telemetry ───────────────────────────────────────────────────────────────────

def _emit_telemetry(
    model: str,
    throttle_ms: float,
    inference_ms: float,
    attempts: int,
    rate_limited: bool,
    ok: bool,
) -> None:
    try:
        from app.extraction import llm_telemetry
        llm_telemetry.record(llm_telemetry.LLMCall(
            span=llm_telemetry.current_span(), model=model,
            throttle_wait_ms=throttle_ms, inference_ms=inference_ms,
            attempts=attempts, rate_limited=rate_limited, ok=ok,
        ))
    except Exception:
        pass  # telemetry must never affect the LLM path (P-6)


# ── HTTP helpers ────────────────────────────────────────────────────────────────

def _http_post(base_url: str, api_key: str, body: dict, timeout: int) -> requests.Response:
    return requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )


# ── Provider call implementations ───────────────────────────────────────────────

def _try_together(
    messages: List[dict],
    *,
    model: str,
    timeout: int,
    reasoning_effort: str,
    max_tokens: int,
) -> Optional[dict]:
    """Call Together AI with two-key round-robin and retry on transient errors.
    Together is the PRIMARY provider and runs at FULL POWER — no TPM throttle is
    applied. If Together fails (network error, 429, 5xx after retries), the caller
    falls back to Groq automatically. Groq is NEVER used while Together is healthy.
    Returns parsed JSON or None (caller falls back to Groq)."""
    api_key, tpm_key = _next_together_slot()
    if not api_key:
        return None

    body: Dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    # Together AI runs at full power — no client-side TPM throttle.
    # The TPM bucket exists only to track usage for telemetry, not to block calls.
    # Rate limits are handled by Together's own API (429 → retry with backoff → Groq fallback).
    throttle_ms = 0.0  # no throttle on Together

    inference_ms = 0.0
    attempts = 0
    rate_limited = False

    for attempt in range(3):
        attempts += 1
        try:
            _t = time.perf_counter()
            resp = _http_post(config.TOGETHER_BASE_URL, api_key, body, timeout)
            inference_ms += (time.perf_counter() - _t) * 1000.0

            if resp.status_code in _TOGETHER_RETRYABLE and attempt < 2:
                if resp.status_code == 429:
                    rate_limited = True
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except (TypeError, ValueError):
                    wait = 0.0
                backoff = min(max(wait, 2.0 * (attempt + 1)), 15.0)
                _b = time.perf_counter()
                time.sleep(backoff)
                throttle_ms += (time.perf_counter() - _b) * 1000.0
                continue

            # Together reasoning models can also leak JSON validation errors
            if resp.status_code == 400 and "json_validate_failed" in resp.text and attempt < 2:
                body.pop("response_format", None)
                continue

            if resp.status_code != 200:
                logger.warning("Together %s HTTP %s: %s", model, resp.status_code, resp.text[:200])
                _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=False)
                return None

            content = resp.json()["choices"][0]["message"]["content"]
            result = _extract_json(content)
            _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=result is not None)
            return result

        except Exception as exc:
            logger.warning("Together %s attempt %d failed: %s", model, attempt + 1, exc)
            if attempt < 2:
                _b = time.perf_counter()
                time.sleep(2.0 * (attempt + 1))
                throttle_ms += (time.perf_counter() - _b) * 1000.0

    _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=False)
    return None


def _try_groq(
    messages: List[dict],
    *,
    api_key: str,
    model: str,
    timeout: int,
    reasoning_effort: str,
    max_tokens: int,
    apply_throttle: bool = True,
) -> Optional[dict]:
    """Call Groq with retry on transient errors. Returns parsed JSON or None."""
    if not api_key:
        return None

    body: Dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    throttle_ms = 0.0
    if apply_throttle and api_key == config.GROQ_API_KEY:
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        est_tokens = prompt_chars // 4 + min(max_tokens, 1500)
        throttle_ms = _throttle_tpm(est_tokens, tpm_key=_GROQ_TPM_KEY, limit=config.GROQ_TPM_LIMIT)

    inference_ms = 0.0
    attempts = 0
    rate_limited = False

    for attempt in range(3):
        attempts += 1
        try:
            _t = time.perf_counter()
            resp = _http_post(config.GROQ_BASE_URL, api_key, body, timeout)
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

            if resp.status_code == 400 and "json_validate_failed" in resp.text and attempt < 2:
                body.pop("response_format", None)
                continue

            if resp.status_code != 200:
                logger.warning("Groq %s HTTP %s: %s", model, resp.status_code, resp.text[:200])
                _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=False)
                return None

            content = resp.json()["choices"][0]["message"]["content"]
            result = _extract_json(content)
            _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=result is not None)
            return result

        except Exception as exc:
            logger.warning("Groq %s attempt %d failed: %s", model, attempt + 1, exc)
            if attempt < 2:
                _b = time.perf_counter()
                time.sleep(2.0 * (attempt + 1))
                throttle_ms += (time.perf_counter() - _b) * 1000.0

    _emit_telemetry(model, throttle_ms, inference_ms, attempts, rate_limited, ok=False)
    return None


# ── Public API ──────────────────────────────────────────────────────────────────

def chat_json(
    messages: List[dict],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    max_tokens: int = 2048,
) -> Optional[dict]:
    """Call the LLM in JSON mode and return the parsed object.

    Provider order: Together AI (primary) → Groq (fallback).
    Explicit `api_key` bypasses Together entirely — used for Groq vision calls.
    `reasoning_effort` is sent only when truthy (reasoning models need it;
    multimodal models like llama-4-scout do not).
    Returns None on all failures — never raises.
    """
    eff = reasoning_effort if reasoning_effort is not None else config.GROQ_REASONING_EFFORT

    # Vision / explicit-key calls are always routed to Groq directly.
    if api_key is not None:
        return _try_groq(
            messages,
            api_key=api_key,
            model=model or config.GROQ_MODEL,
            timeout=timeout or config.GROQ_TIMEOUT,
            reasoning_effort=eff,
            max_tokens=max_tokens,
            apply_throttle=False,
        )

    together_model = model or config.TOGETHER_MODEL
    groq_model = model or config.GROQ_MODEL

    # Content-hash cache: an identical call returns the stored result for zero tokens.
    cache_key = None
    if config.GROQ_CACHE_ENABLED:
        cache_model = together_model if together_extraction_available() else groq_model
        cache_key = _cache_key(cache_model, messages, eff, max_tokens)
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("LLM cache hit (%s) — 0 tokens", cache_model)
            return cached

    # ── 1. Together AI — PRIMARY, runs at full power, no client-side throttle ────
    # Groq is NEVER called while Together is healthy and returning results.
    # Groq fallback only activates when Together fails: network error, 429 rate-limit
    # exhausted after retries, 5xx server error, or Together key not configured.
    if together_extraction_available():
        result = _try_together(
            messages,
            model=together_model,
            timeout=timeout or config.TOGETHER_TIMEOUT,
            reasoning_effort=eff,
            max_tokens=max_tokens,
        )
        if result is not None:
            if cache_key:
                _cache_set(cache_key, result)
            return result
        # Together failed (exhausted retries) → activate Groq fallback
        logger.warning(
            "Together AI failed after all retries (rate-limit, network error, or service down). "
            "Activating Groq fallback — Groq TPM throttle applies (%d/min).",
            config.GROQ_TPM_LIMIT,
        )

    # ── 2. Groq — FALLBACK only when Together is down/exhausted/unconfigured ─────
    # Groq has a 6000 TPM throttle to stay within free-tier limits.
    # This path should rarely activate in normal operation.
    if groq_extraction_available():
        result = _try_groq(
            messages,
            api_key=config.GROQ_API_KEY,
            model=groq_model,
            timeout=timeout or config.GROQ_TIMEOUT,
            reasoning_effort=eff,
            max_tokens=max_tokens,
            apply_throttle=True,    # always throttle Groq — it's the rate-limited fallback
        )
        if result is not None and cache_key:
            _cache_set(cache_key, result)
        return result

    logger.error("Both Together AI and Groq unavailable — LLM extraction skipped for this call.")
    return None


def assess_text(text: str, question: str) -> Optional[bool]:
    """Yes/no evaluation of free text by the LLM — the legitimate *evaluative*
    use of the model (NOT structured extraction). Returns True/False, or None
    when no provider is available or the answer can't be parsed."""
    if not (together_extraction_available() or groq_extraction_available()):
        return None
    if not (text or "").strip():
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
    Always routes to Groq (llama-4-scout multimodal) — Together is text-only here.
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
