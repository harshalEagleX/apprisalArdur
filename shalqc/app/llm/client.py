"""
llm.client (lcl-1.0.0) — SHALqc.md §10 LLM subsystem.

One OpenAI-compatible chat client with:
  * 2-key failover — Together AI key-1/key-2 round-robin (primary), Groq on
    429 / 5xx / timeout (SHALqc.md §10 two-key failover).
  * Redis content-hash cache — key = sha256(call_type + model + prompt_version +
    payload), TTL from settings (72h per §17 PII). A cache HIT still emits an
    LLMCall{cached: true} so usage counts stay honest (§10).
  * telemetry — every call (hit or miss) appends an LLMCall record the report
    can aggregate.
  * temperature=0, JSON-only contract, one retry on invalid JSON, then a typed
    failure the caller degrades on (never a crash — P6).

Provides `complete()` (raw structured call) plus the two protocol methods the
rest of the system already expects:
  * `ask(section, fields, page_text)` — the GapfillClient protocol
    (extraction/llm_gapfill.py C1), and
  * `classify(system, user, ...)` — used by the tier-2 judge (llm/judge.py).

With NO keys configured the client is still constructed but `available` is
False; callers pass it as None-equivalent so the engine degrades tier-2/3 rules
to VERIFY `llm_unavailable` rather than calling out (SHALqc-CORE §4.0).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

__version__ = "lcl-1.0.0"

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
PROMPT_VERSION = "v1"

# When Redis is not configured, responses are cached to this directory so every
# LLM reply is persisted on disk (permanent — survives process exit) and re-runs
# are instant cache hits. Override with SHALQC_LLM_CACHE_DIR.
_FILE_CACHE_DIR = os.environ.get(
    "SHALQC_LLM_CACHE_DIR",
    str(Path(__file__).resolve().parents[2] / "llm_cache"),
)


@dataclass
class LLMCall:
    """Telemetry for one call — cache hits included (cached=True), per §10."""
    call_type: str
    provider: str
    model: str
    cached: bool = False
    ok: bool = True
    ms: float = 0.0
    error: Optional[str] = None


class LLMResult:
    def __init__(self, data: Optional[dict], call: LLMCall):
        self.data = data
        self.call = call

    @property
    def ok(self) -> bool:
        return self.data is not None and self.call.ok


class LLMClient:
    def __init__(self) -> None:
        self._together_keys = list(settings.together_keys)
        self._together_idx = 0
        self._idx_lock = threading.Lock()
        self._groq_key = settings.groq_key
        self.telemetry: List[LLMCall] = []
        self._redis = self._init_redis()
        # File cache is the fallback whenever Redis is not active — it makes LLM
        # responses persist on disk instead of vanishing when the run ends.
        self._file_cache_dir = None
        if self._redis is None:
            try:
                Path(_FILE_CACHE_DIR).mkdir(parents=True, exist_ok=True)
                self._file_cache_dir = _FILE_CACHE_DIR
                logger.info("LLM cache: file cache active (%s)", _FILE_CACHE_DIR)
            except Exception as exc:
                logger.warning("LLM cache: file cache unavailable (%s)", exc)

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self._together_keys or self._groq_key)

    def _init_redis(self):
        url = settings.redis_llm_cache_url
        if not url:
            return None
        try:
            import redis
            c = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)
            c.ping()
            logger.info("LLM cache: Redis active (%s)", url)
            return c
        except Exception as exc:
            logger.warning("LLM cache: Redis unavailable (%s) — cache disabled", exc)
            return None

    # ------------------------------------------------------------------
    def _next_together_key(self) -> Optional[str]:
        if not self._together_keys:
            return None
        with self._idx_lock:
            key = self._together_keys[self._together_idx % len(self._together_keys)]
            self._together_idx += 1
        return key

    def _cache_key(self, call_type: str, model: str, payload: str) -> str:
        h = hashlib.sha256(f"{call_type}|{model}|{PROMPT_VERSION}|{payload}".encode("utf-8")).hexdigest()
        return f"shalqc:llm:{h}"

    def _file_cache_path(self, key: str) -> str:
        # key already looks like "shalqc:llm:<hash>"; use the hash as filename.
        return os.path.join(self._file_cache_dir, key.split(":")[-1] + ".json")

    def _cache_get(self, key: str) -> Optional[dict]:
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                return None
        if self._file_cache_dir is not None:
            try:
                p = self._file_cache_path(key)
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as fh:
                        return json.load(fh)["response"]
            except Exception:
                return None
        return None

    def _cache_put(self, key: str, data: dict, meta: Optional[dict] = None) -> None:
        if self._redis is not None:
            try:
                self._redis.setex(key, settings.llm_cache_ttl_hours * 3600, json.dumps(data))
            except Exception:
                pass
            return
        if self._file_cache_dir is not None:
            try:
                record = {"saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "response": data}
                if meta:
                    record.update(meta)
                with open(self._file_cache_path(key), "w", encoding="utf-8") as fh:
                    json.dump(record, fh, indent=2)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def complete(self, call_type: str, system: str, user: str,
                 max_tokens: int = 1024) -> LLMResult:
        """One JSON-mode chat completion with cache + failover. Returns an
        LLMResult whose .data is the parsed JSON reply (or None on failure)."""
        payload_sig = f"{system}\n{user}"
        model = settings.together_model if self._together_keys else settings.groq_model
        cache_key = self._cache_key(call_type, model, payload_sig)

        cached = self._cache_get(cache_key)
        if cached is not None:
            call = LLMCall(call_type=call_type, provider="cache", model=model, cached=True, ok=True)
            self.telemetry.append(call)
            return LLMResult(cached, call)

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        # provider order: each Together key, then Groq
        attempts: List[tuple] = []
        for _ in range(len(self._together_keys)):
            key = self._next_together_key()
            if key:
                attempts.append(("together", settings.together_base_url, key, settings.together_model))
        if self._groq_key:
            attempts.append(("groq", settings.groq_base_url, self._groq_key, settings.groq_model))

        last_err = "no_provider_configured"
        for provider, url, key, model in attempts:
            data, err, ms = self._one_call(url, key, model, messages, max_tokens)
            if data is not None:
                call = LLMCall(call_type=call_type, provider=provider, model=model, ok=True, ms=ms)
                self.telemetry.append(call)
                self._cache_put(cache_key, data,
                                meta={"call_type": call_type, "model": model,
                                      "system": system, "user": user})
                return LLMResult(data, call)
            last_err = err
            logger.warning("LLM %s failed on %s: %s", call_type, provider, err)

        call = LLMCall(call_type=call_type, provider="none", model=model, ok=False, error=last_err)
        self.telemetry.append(call)
        return LLMResult(None, call)

    def _one_call(self, url: str, key: str, model: str, messages: List[dict],
                  max_tokens: int):
        body = {
            "model": model, "messages": messages, "temperature": 0,
            "max_tokens": max_tokens, "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        t0 = time.perf_counter()
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=_TIMEOUT)
        except Exception as exc:
            return None, f"transport:{exc}", (time.perf_counter() - t0) * 1000
        ms = (time.perf_counter() - t0) * 1000
        if resp.status_code in (429,) or resp.status_code >= 500:
            return None, f"http_{resp.status_code}", ms   # failover trigger
        if resp.status_code != 200:
            return None, f"http_{resp.status_code}:{resp.text[:120]}", ms
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            return None, f"bad_envelope:{exc}", ms
        data = _parse_json(content)
        if data is None:
            # one retry with a repair nudge appended (SHALqc-CORE §4.0)
            retry_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": "Your reply was not valid JSON. Reply again with JSON only."},
            ]
            body["messages"] = retry_messages
            try:
                resp2 = httpx.post(url, json=body, headers=headers, timeout=_TIMEOUT)
                content2 = resp2.json()["choices"][0]["message"]["content"]
                data = _parse_json(content2)
            except Exception:
                data = None
        if data is None:
            return None, "invalid_json_after_retry", ms
        return data, None, ms

    # ------------------------------------------------------------------
    # GapfillClient protocol (extraction/llm_gapfill.py C1)
    # ------------------------------------------------------------------
    def ask(self, section: str, fields: List[str], page_text: str) -> Dict[str, Optional[str]]:
        system = ("Return the VERBATIM text of each requested field from the page text. "
                  "If a field is not present, return null. Never compose, summarize, or fix text. "
                  'Reply JSON only: {"fields": {"<field_id>": "<verbatim or null>"}}.')
        user = json.dumps({"section": section, "fields": fields, "page_text": page_text[:6000]})
        result = self.complete("gapfill", system, user)
        if not result.ok:
            return {}
        out = (result.data or {}).get("fields", {})
        return {k: (v if v else None) for k, v in out.items()} if isinstance(out, dict) else {}

    # ------------------------------------------------------------------
    # tier-2 classification (llm/judge.py)
    # ------------------------------------------------------------------
    def classify(self, system: str, user: str) -> Optional[dict]:
        result = self.complete("classify", system, user)
        return result.data if result.ok else None


# Singleton — None-safe: callers test `.available` and pass None-equivalent.
_client: Optional[LLMClient] = None


def get_client() -> Optional[LLMClient]:
    """Return the shared client, or None when no keys are configured so callers
    degrade tier-2/3 rules to VERIFY (SHALqc-CORE §4.0)."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client if _client.available else None


def _parse_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    # tolerate ```json fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        # salvage the outermost {...}
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                obj = json.loads(text[start:end + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
        return None
