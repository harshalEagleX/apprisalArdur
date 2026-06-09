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


def _throttle_tpm(est_tokens: int) -> None:
    """Block until sending `est_tokens` keeps the last-60s usage under the limit.
    This turns a would-be 429 into an orderly wait — a multi-page grid is then
    processed in steps within the budget."""
    limit = max(1, config.GROQ_TPM_LIMIT)
    with _tpm_lock:
        now = time.time()
        while _tpm_log and now - _tpm_log[0][0] > 60:
            _tpm_log.popleft()
        used = sum(t for _, t in _tpm_log)
        if used + est_tokens > limit and _tpm_log:
            wait = 60 - (now - _tpm_log[0][0]) + 0.5
            if wait > 0:
                logger.info("Groq TPM budget reached (%d/%d); waiting %.1fs", used, limit, wait)
                time.sleep(min(wait, 60))
            now = time.time()
            while _tpm_log and now - _tpm_log[0][0] > 60:
                _tpm_log.popleft()
        _tpm_log.append((time.time(), est_tokens))


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
    # Throttle only the extraction model (the vision key/model has its own budget).
    if api_key == config.GROQ_API_KEY:
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        # input tokens + a realistic completion estimate (incl. reasoning), not the
        # max_tokens cap — overestimating would make the throttle wait needlessly.
        _throttle_tpm(prompt_chars // 4 + min(max_tokens, 1500))
    # Retry transient capacity/rate-limit errors with backoff (free tier is
    # token-per-minute limited); honor Retry-After when the API provides it.
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{config.GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout or config.GROQ_TIMEOUT,
            )
            if resp.status_code in (429, 500, 503) and attempt < 2:
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except (TypeError, ValueError):
                    wait = 0.0
                time.sleep(min(max(wait, 2.0 * (attempt + 1)), 12.0))
                continue
            # Reasoning models intermittently fail strict JSON validation (the
            # reasoning channel leaks / truncates). Drop response_format and parse
            # the JSON object out of the free-text content on retry.
            if resp.status_code == 400 and "json_validate_failed" in resp.text and attempt < 2:
                body.pop("response_format", None)
                continue
            if resp.status_code != 200:
                logger.warning("Groq %s HTTP %s: %s", model, resp.status_code, resp.text[:200])
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            return _extract_json(content)
        except Exception as exc:  # never break the pipeline (P-6)
            logger.warning("Groq %s attempt %d failed: %s", model, attempt + 1, exc)
            if attempt < 2:
                time.sleep(2.0 * (attempt + 1))
    return None


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
