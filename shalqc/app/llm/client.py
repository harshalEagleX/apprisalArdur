"""
llm.client (lcl-2.0.0) — the LLM subsystem, single-provider (Together AI).

2026-07-13: Groq deleted entirely (was a failover-on-429/5xx/timeout second
provider). Its account tier's tokens-per-minute ceiling was far tighter than
Together's own, so routing a Together slowdown to Groq just traded one
failure mode for a worse-constrained one — confirmed directly from Groq's own
error text (`tokens per minute (TPM): Limit 8000, Requested 15949`) once
narrative packets started carrying real prose instead of empty/garbage
values. Replaced with TogetherPool: a per-key token-bucket + in-flight
governor that stops SENDING what a key's budget can't take, rather than
reacting to a 429 after the fact.

Retry policy (error-code only, never on timeout):
  * 429 / 5xx / a connection-level transport error → retry, up to 2 times,
    backoff 2s then 8s, against a (likely) different pool key.
  * A genuine timeout means the call is dead — no retry. The caller's S-6
    fallback (REVIEW `llm_unavailable`, packet attached) is the correct,
    honest outcome; a second attempt at the same slow thing is not a fix.

Other pieces unchanged from lcl-1.0.0:
  * Redis content-hash cache (file-cache fallback) — key = sha256(call_type +
    model + prompt_version + payload), TTL from settings.
  * telemetry — every call (hit or miss) appends an LLMCall record.
  * temperature=0, JSON-only contract, one in-call retry on invalid JSON
    (a repair nudge appended to the SAME call, distinct from the provider-
    level retry above), then a typed failure the caller degrades on (P6).

Provides `complete()` plus the two protocol methods the rest of the system
already expects: `ask()` (GapfillClient protocol) and `classify()` (tier-2
judge). With no key configured the client is still constructed but
`available` is False; callers pass it as None-equivalent so the engine
degrades tier-2/3 rules to VERIFY `llm_unavailable` (SHALqc-CORE §4.0).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.llm.together_pool import TogetherPool, estimate_tokens

__version__ = "lcl-2.0.0"

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
# gpt-oss-120b is a reasoning model — reasoning_effort=high (or provider-default
# on some routes) burns 2-3x the tokens/latency on invisible chain-of-thought
# before the JSON answer (measured: default ~15s/5KB reply, high ~40s/16KB
# reply, for the exact same tiny judge packet). The judge's job is a
# structured classification against an explicit rubric, not open-ended
# reasoning — pin it low so most of every call's time goes into the answer,
# not the thinking. 2026-07-13 perf investigation.
_REASONING_EFFORT = "low"
_RETRY_BACKOFFS_S = (2.0, 8.0)   # error-code retries only — see module docstring
_POOL_ACQUIRE_TIMEOUT_S = 20.0

# When Redis is not configured, responses are cached to this directory so every
# LLM reply is persisted on disk (permanent — survives process exit) and re-runs
# are instant cache hits. Override with SHALQC_LLM_CACHE_DIR.
_FILE_CACHE_DIR = os.environ.get(
    "SHALQC_LLM_CACHE_DIR",
    str(Path(__file__).resolve().parents[2] / "llm_cache"),
)


@dataclass
class LLMCall:
    """Telemetry for one call — cache hits included (cached=True)."""
    call_type: str
    provider: str
    model: str
    cached: bool = False
    ok: bool = True
    ms: float = 0.0
    error: Optional[str] = None
    retries: int = 0


class LLMResult:
    def __init__(self, data: Optional[dict], call: LLMCall, raw: Optional[str] = None):
        self.data = data
        self.call = call
        # the raw model text (before JSON parsing) — kept so every exchange can be
        # persisted verbatim for the reviewer/replay (llm_interactions audit).
        self.raw = raw

    @property
    def ok(self) -> bool:
        return self.data is not None and self.call.ok


def _is_reasoning_model(model: str) -> bool:
    """Models that accept the `reasoning_effort` param. gpt-oss is the reasoning
    model in use; qwq/o1-style also qualify. Non-reasoning models (gemma, plain
    Qwen instruct, llama) must NOT receive it or Together returns 400."""
    m = model.lower()
    return "gpt-oss" in m or "qwq" in m or "o1" in m or "deepseek-r1" in m


def _is_retryable(err: str) -> bool:
    """429 / 5xx / connection-level transport error → retryable. A genuine
    timeout (the call was sent and never came back in time) is deliberately
    NOT retryable — see module docstring."""
    return err.startswith("http_429") or err.startswith("http_5") or err.startswith("transport:")


class LLMClient:
    def __init__(self) -> None:
        self._together_keys = list(settings.together_keys)
        self._pool = TogetherPool(
            self._together_keys,
            tpm_budget_per_key=settings.together_tpm_budget_per_key,
            max_inflight_per_key=settings.together_max_inflight_per_key,
        )
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
        return bool(self._together_keys)

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
                 max_tokens: int = 1024, reasoning_effort: Optional[str] = None) -> LLMResult:
        """One JSON-mode chat completion, governed by TogetherPool. Returns an
        LLMResult whose .data is the parsed JSON reply (or None on failure).
        `reasoning_effort` overrides the module default (low) — callers that
        batch by kind (judge_v2's fact/cross_doc/narrative classes) can tune
        it per class once the replay harness (tools/replay_harness.py) has
        proven a lower effort doesn't flip any verdict."""
        payload_sig = f"{system}\n{user}"
        model = settings.together_model
        cache_key = self._cache_key(call_type, model, payload_sig)

        cached = self._cache_get(cache_key)
        if cached is not None:
            call = LLMCall(call_type=call_type, provider="cache", model=model, cached=True, ok=True)
            self.telemetry.append(call)
            return LLMResult(cached, call, raw=json.dumps(cached, ensure_ascii=False))

        if not self._together_keys:
            call = LLMCall(call_type=call_type, provider="none", model=model, ok=False,
                           error="no_provider_configured")
            self.telemetry.append(call)
            return LLMResult(None, call)

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        estimated = estimate_tokens(system, user, max_tokens)

        last_err = "pool_exhausted"
        retries = 0
        while True:
            key = self._pool.acquire(estimated, timeout=_POOL_ACQUIRE_TIMEOUT_S)
            if key is None:
                last_err = "pool_exhausted"
                break
            try:
                data, err, ms, raw = self._one_call(key, model, messages, max_tokens, reasoning_effort)
            finally:
                self._pool.release(key)
            if data is not None:
                call = LLMCall(call_type=call_type, provider="together", model=model,
                               ok=True, ms=ms, retries=retries)
                self.telemetry.append(call)
                self._cache_put(cache_key, data,
                                meta={"call_type": call_type, "model": model,
                                      "system": system, "user": user})
                return LLMResult(data, call, raw=raw)
            last_err = err
            logger.warning("LLM %s failed: %s (retries=%d)", call_type, err, retries)
            if not _is_retryable(err) or retries >= len(_RETRY_BACKOFFS_S):
                break
            time.sleep(_RETRY_BACKOFFS_S[retries])
            retries += 1

        call = LLMCall(call_type=call_type, provider="none", model=model, ok=False,
                       error=last_err, retries=retries)
        self.telemetry.append(call)
        return LLMResult(None, call)

    def _one_call(self, key: str, model: str, messages: List[dict], max_tokens: int,
                  reasoning_effort: Optional[str] = None):
        body = {
            "model": model, "messages": messages, "temperature": 0,
            "max_tokens": max_tokens, "response_format": {"type": "json_object"},
        }
        # reasoning_effort is a reasoning-model-only param — Together 400s if it's
        # sent to a non-reasoning model (gemma/Qwen/…). Only attach it for models
        # that accept it, so the same code path can A/B different models.
        if _is_reasoning_model(model):
            body["reasoning_effort"] = reasoning_effort or _REASONING_EFFORT
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        url = settings.together_base_url
        t0 = time.perf_counter()
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=settings.together_timeout_s)
        except httpx.TimeoutException as exc:
            # deliberately NOT prefixed "transport:" — _is_retryable must never
            # retry this (module docstring: a timeout means the call is dead).
            return None, f"timeout:{exc}", (time.perf_counter() - t0) * 1000, None
        except Exception as exc:
            return None, f"transport:{exc}", (time.perf_counter() - t0) * 1000, None
        ms = (time.perf_counter() - t0) * 1000
        if resp.status_code == 429 or resp.status_code >= 500:
            return None, f"http_{resp.status_code}", ms, None   # retry trigger
        if resp.status_code != 200:
            return None, f"http_{resp.status_code}:{resp.text[:200]}", ms, None
        try:
            choice = resp.json()["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason", "")
        except Exception as exc:
            return None, f"bad_envelope:{exc}", ms, None
        data = _parse_json(content)
        if data is None:
            # finish_reason distinguishes the two failure modes that both surface
            # as invalid JSON: "length" = the reply was TRUNCATED (max_tokens too
            # small for the batch, esp. with reasoning overhead) → the fix is more
            # tokens / smaller batch, NOT a repair nudge; anything else = the model
            # actually emitted non-JSON. 2026-07-13 judge JSON-failure investigation.
            if finish == "length":
                logger.warning("LLM truncated (finish_reason=length): content len=%d, max_tokens=%d",
                               len(content or ""), max_tokens)
            # one in-call repair retry (SHALqc-CORE §4.0) — distinct from the
            # provider-level retry in complete(); same key, same slot.
            retry_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": "Your reply was not valid JSON. Reply again with JSON only."},
            ]
            body["messages"] = retry_messages
            try:
                resp2 = httpx.post(url, json=body, headers=headers, timeout=settings.together_timeout_s)
                content = resp2.json()["choices"][0]["message"]["content"]
                data = _parse_json(content)
            except Exception:
                data = None
        if data is None:
            reason = "truncated_length" if finish == "length" else "invalid_json_after_retry"
            return None, reason, ms, content
        return data, None, ms, content

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
