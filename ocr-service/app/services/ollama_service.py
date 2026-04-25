"""
Ollama Service — local LLM inference for appraisal QC commentary analysis.

Model: llama3:8b-instruct-q4_0  (fast on CPU/M1, ~5 GB RAM)

Setup (one-time):
    ollama pull llama3:8b-instruct-q4_0

All calls are synchronous (this service runs inside a threadpool in FastAPI).
Temperature is fixed at 0 for deterministic QC decisions.
"""

import json
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3:8b-instruct-q4_0"
OLLAMA_TIMEOUT = 60.0  # seconds — 8b q4 on M1 is fast but give headroom


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_ollama_available() -> bool:
    """Return True if ollama is running AND the target model is loaded."""
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        if r.status_code != 200:
            return False
        models = [m.get("name", "") for m in r.json().get("models", [])]
        return any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core call
# ---------------------------------------------------------------------------

def _generate(prompt: str, system: str = "", max_tokens: int = 256) -> Optional[str]:
    """
    POST to /api/generate (non-streaming).
    Returns the model response string, or None on failure.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": max_tokens,
            "top_k": 1,
        },
    }
    try:
        r = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except httpx.TimeoutException:
        logger.warning("Ollama request timed out (model=%s)", OLLAMA_MODEL)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Ollama HTTP error: %s", e)
        return None
    except Exception as e:
        logger.warning("Ollama call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Task 1: Canned commentary detection (N-6, N-7 rules)
# ---------------------------------------------------------------------------

CANNED_SYSTEM = (
    "You are an appraisal quality control expert. "
    "Your only job: decide if the commentary below is CANNED (generic boilerplate, "
    "copy-pasted template, could apply to any property) or SPECIFIC "
    "(contains property-specific details: addresses, dollar amounts, MLS numbers, "
    "dates, names, or analytical reasoning tied to this property). "
    "Reply with exactly one word: CANNED or SPECIFIC. No explanation."
)


def classify_commentary(text: str) -> Optional[bool]:
    """
    Classify commentary as canned or specific using llama3.

    Returns:
        True  = canned (generic)
        False = specific (good)
        None  = ollama unavailable or inconclusive
    """
    if not text or len(text.strip()) < 20:
        return None

    prompt = f'Commentary to classify:\n"""\n{text[:800]}\n"""'
    response = _generate(prompt, system=CANNED_SYSTEM, max_tokens=10)
    if not response:
        return None

    upper = response.strip().upper()
    if "CANNED" in upper:
        return True
    if "SPECIFIC" in upper:
        return False
    return None


# ---------------------------------------------------------------------------
# Task 2: Market conditions commentary quality (Rule N-7)
# ---------------------------------------------------------------------------

MARKET_SYSTEM = (
    "You are an appraisal QC reviewer. Evaluate the market conditions commentary. "
    "Respond ONLY with valid JSON (no markdown, no prose) using exactly these keys: "
    '{"has_analysis": true/false, "is_see_1004mc": true/false, "summary": "<20 words>"}'
    "\n"
    "has_analysis=true means the text contains actual market data or reasoning. "
    "is_see_1004mc=true means the text just redirects to the 1004MC addendum without adding content."
)


def analyze_market_conditions(text: str) -> dict:
    """
    Evaluate market conditions commentary quality.

    Returns dict: {has_analysis, is_see_1004mc, summary}
    """
    fallback = {
        "has_analysis": None,
        "is_see_1004mc": "see 1004mc" in text.lower() if text else None,
        "summary": None,
    }

    if not text or len(text.strip()) < 10:
        return fallback

    prompt = f'Market conditions commentary:\n"""\n{text[:800]}\n"""'
    response = _generate(prompt, system=MARKET_SYSTEM, max_tokens=128)
    if not response:
        return fallback

    # Extract JSON block (model may add backtick fences)
    json_match = re.search(r"\{.*\}", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: keyword parse
    return {
        "has_analysis": "true" in response.lower(),
        "is_see_1004mc": "see 1004mc" in text.lower(),
        "summary": response[:100],
    }


# ---------------------------------------------------------------------------
# Task 3: Neighborhood description specificity (Rule N-6)
# ---------------------------------------------------------------------------

NBR_SYSTEM = (
    "You are an appraisal QC reviewer. "
    "Does the neighborhood description below mention specific streets, landmarks, "
    "nearby amenities, employers, schools, or other location-specific details? "
    "Reply with exactly one word: YES or NO."
)


def is_neighborhood_description_specific(text: str) -> Optional[bool]:
    """
    Check if neighborhood description is specific to the area.

    Returns True = specific, False = generic, None = unavailable.
    """
    if not text or len(text.strip()) < 15:
        return None

    prompt = f'Neighborhood description:\n"""\n{text[:600]}\n"""'
    response = _generate(prompt, system=NBR_SYSTEM, max_tokens=5)
    if not response:
        return None

    upper = response.strip().upper()
    if "YES" in upper:
        return True
    if "NO" in upper:
        return False
    return None
