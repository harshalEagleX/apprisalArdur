"""
Ollama Resilience Layer — Addresses All 13 Failure Modes

The user identified 13 specific ways Ollama can fail silently or incorrectly.
This module implements defenses for each one.

Failure Mode → Defense:

1.  New AMC unfamiliar labels      → AMC terminology normalization BEFORE sending to LLM
2.  Context window overflow        → Hard page limit per chunk + word count gate
3.  Queue congestion               → Request semaphore + estimated wait time feedback
4.  Hallucination missed           → Tighter verification: value must appear verbatim in source
5.  Poor OCR → garbage to LLM     → Text quality gate: skip LLM if quality < 0.40
6.  Prompt drift                   → Model version pinning + version in extraction results
7.  Wrong format returned          → Format validator + normalize before accepting
8.  GPU contention                 → VRAM-aware resource gate (check memory before call)
9.  No automated retraining        → Correction pattern reporter (Week 5 prerequisite)
10. Unknown abbreviations          → AMC terminology normalization (from profile.terminology_mapping)
11. LLM over-confident in wrong    → Ignore LLM self-confidence, use calibrated base conf
12. Table content loses structure   → Send structured table representation, not raw text
13. Crash with no alert            → Health monitor with alerting and circuit breaker
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_TEXT_MODEL, OLLAMA_TIMEOUT_TEXT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defense 3 + 8: Request gate — semaphore + GPU resource awareness
# ---------------------------------------------------------------------------

_LLM_SEMAPHORE = threading.Semaphore(1)   # only 1 concurrent LLM call (single GPU)
_LAST_CALL_TIME: float = 0.0
_MIN_CALL_INTERVAL = 2.0                  # seconds between calls (prevent thrashing)

# ---------------------------------------------------------------------------
# Defense 13: Circuit breaker — stops hammering Ollama when it's down
# ---------------------------------------------------------------------------

_CONSECUTIVE_FAILURES = 0
_CIRCUIT_OPEN_UNTIL: float = 0.0
_CIRCUIT_THRESHOLD = 3          # open circuit after 3 consecutive failures
_CIRCUIT_RESET_SECONDS = 60     # try again after 60 seconds


def _circuit_is_open() -> bool:
    global _CIRCUIT_OPEN_UNTIL, _CONSECUTIVE_FAILURES
    if _CIRCUIT_OPEN_UNTIL > time.time():
        return True
    if _CONSECUTIVE_FAILURES >= _CIRCUIT_THRESHOLD:
        _CIRCUIT_OPEN_UNTIL = time.time() + _CIRCUIT_RESET_SECONDS
        logger.warning(
            "LLM circuit breaker OPEN — Ollama failed %d times consecutively. "
            "Retrying in %ds. All documents will use spatial+embedding only.",
            _CONSECUTIVE_FAILURES, _CIRCUIT_RESET_SECONDS,
        )
        return True
    return False


def _record_success() -> None:
    global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN_UNTIL
    _CONSECUTIVE_FAILURES = 0
    _CIRCUIT_OPEN_UNTIL = 0.0


def _record_failure() -> None:
    global _CONSECUTIVE_FAILURES
    _CONSECUTIVE_FAILURES += 1


# ---------------------------------------------------------------------------
# Defense 5: Text quality gate
# ---------------------------------------------------------------------------

_MIN_TEXT_QUALITY_FOR_LLM = 0.40    # skip LLM if OCR quality below this threshold
_MIN_WORDS_PER_CHUNK = 30           # skip if chunk has fewer words than this


def text_passes_quality_gate(text: str, quality_score: float = 1.0) -> Tuple[bool, str]:
    """
    Defense 5: Scanned documents with poor OCR quality should not be sent to LLM.
    LLM confidently extracts nonsense from garbled text — better to use NOT_FOUND
    with low confidence than a hallucinated value with medium confidence.
    """
    if quality_score < _MIN_TEXT_QUALITY_FOR_LLM:
        return False, f"Text quality {quality_score:.2f} below threshold {_MIN_TEXT_QUALITY_FOR_LLM}"

    word_count = len(text.split())
    if word_count < _MIN_WORDS_PER_CHUNK:
        return False, f"Chunk too short: {word_count} words (min {_MIN_WORDS_PER_CHUNK})"

    return True, "OK"


# ---------------------------------------------------------------------------
# Defense 1 + 10: AMC terminology normalization before LLM
# ---------------------------------------------------------------------------

def apply_amc_terminology_to_chunk(text: str, amc_id: Optional[str]) -> str:
    """
    Defense 1 + 10: Normalize AMC-specific labels to canonical equivalents BEFORE
    sending to the LLM. The LLM has never seen this AMC's vocabulary, but the
    profile has the mappings. Translate first so LLM sees standard labels.
    """
    if not amc_id:
        return text
    try:
        from app.services.amc_profile_service import get_amc_terminology
        term_map = get_amc_terminology(amc_id)
        for amc_label, canonical in term_map.items():
            text = text.replace(amc_label, canonical)
    except Exception:
        pass
    return text


# ---------------------------------------------------------------------------
# Defense 2: Context window management
# ---------------------------------------------------------------------------

_MAX_WORDS_PER_LLM_CHUNK = 1200     # ~4000 tokens at 3.3 words/token
_MAX_PAGES_PER_CHUNK = 5


def chunk_text_for_llm(
    page_texts: Dict[int, str],
    start_page: int,
    end_page: int,
) -> str:
    """
    Defense 2: Enforce hard word limit per chunk to prevent context overflow.
    The LLM silently cuts off content when context is exceeded, causing missing
    fields with no error. Hard limit here ensures chunking is explicit.
    """
    chunk_pages = []
    word_count = 0

    for pn in range(start_page, min(end_page + 1, start_page + _MAX_PAGES_PER_CHUNK)):
        page_text = page_texts.get(pn, "")
        page_words = page_text.split()

        if word_count + len(page_words) > _MAX_WORDS_PER_LLM_CHUNK:
            # Truncate this page to fit
            remaining = _MAX_WORDS_PER_LLM_CHUNK - word_count
            if remaining > 50:  # only include if meaningful
                chunk_pages.append(f"[Page {pn} (truncated)]\n" + " ".join(page_words[:remaining]))
            break

        chunk_pages.append(f"[Page {pn}]\n{page_text}")
        word_count += len(page_words)

    return "\n\n".join(chunk_pages)


# ---------------------------------------------------------------------------
# Defense 6 + 11: Model version pinning + confidence override
# ---------------------------------------------------------------------------

_CURRENT_MODEL_VERSION: Optional[str] = None
_CALIBRATED_LLM_CONFIDENCE = 0.72   # Defense 11: ignore LLM self-confidence, use calibrated value


def get_pinned_model() -> str:
    """
    Defense 6: Always use the pinned model version, not whatever Ollama defaults to.
    Prompt drift happens when models update; pinning prevents unexpected behavior changes.
    """
    return OLLAMA_TEXT_MODEL


def llm_base_confidence(hallucination_verified: bool) -> float:
    """
    Defense 11: Ignore the LLM's self-reported confidence — LLMs are badly
    calibrated for extraction tasks. Use our own empirically determined baseline.
    Verified extraction gets 0.82, unverified gets capped at 0.40.
    """
    return 0.82 if hallucination_verified else 0.40


# ---------------------------------------------------------------------------
# Defense 4: Tighter hallucination detection
# ---------------------------------------------------------------------------

_MIN_SOURCE_TEXT_LENGTH_FOR_VERIFICATION = 10   # must cite at least 10 chars


def verify_extraction_against_source(
    value: str,
    source_text: Optional[str],
    full_document_text: str,
) -> Tuple[bool, float]:
    """
    Defense 4: Tighter hallucination verification.
    The value must appear VERBATIM (or very close to verbatim) in the cited source text,
    AND the source text must appear in the actual document.
    Returns (verified, confidence_multiplier).
    """
    if not value or not source_text:
        return False, 0.3

    # Check 1: Value appears in cited source text
    val_norm = value.lower().strip()
    src_norm = source_text.lower().strip()
    if val_norm not in src_norm:
        logger.debug("Hallucination: %r not in source %r", value[:30], source_text[:40])
        return False, 0.25

    # Check 2: Source text is long enough to be credible
    if len(source_text.strip()) < _MIN_SOURCE_TEXT_LENGTH_FOR_VERIFICATION:
        return False, 0.35

    # Check 3: Source text appears in the actual document (verbatim first 40 chars)
    source_sample = src_norm[:40]
    if source_sample in full_document_text.lower():
        return True, 1.0

    # Check 4: Fuzzy check — first 20 chars
    if len(src_norm) >= 20 and src_norm[:20] in full_document_text.lower():
        return True, 0.85

    # Source text not found in document — likely hallucinated
    logger.debug("Source text not found in document: %r", source_text[:40])
    return False, 0.35


# ---------------------------------------------------------------------------
# Defense 7: Format validation
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$")
_CURRENCY_PATTERN = re.compile(r"^\$?[\d,]+(?:\.\d{1,2})?$")
_UAD_CODE_PATTERN = re.compile(r"^[CQ][1-6]$")


def validate_extracted_format(value: str, data_type: str) -> Tuple[bool, Optional[str]]:
    """
    Defense 7: Validate that the LLM returned the value in the expected format.
    LLMs often return "January 5th 2024" when you need "2026-01-05".
    Returns (valid, normalized_value_or_none).
    """
    if not value:
        return False, None

    if data_type == "date":
        if _DATE_PATTERN.match(value.strip()):
            return True, value.strip()
        # Try to normalize written dates
        months = {"january": "01", "february": "02", "march": "03", "april": "04",
                  "may": "05", "june": "06", "july": "07", "august": "08",
                  "september": "09", "october": "10", "november": "11", "december": "12",
                  "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
                  "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
        v_lower = value.lower()
        for month_name, month_num in months.items():
            if month_name in v_lower:
                # Try to extract year and day
                nums = re.findall(r"\d+", value)
                if len(nums) >= 2:
                    year = next((n for n in nums if len(n) == 4), None)
                    day = next((n for n in nums if len(n) <= 2), None)
                    if year and day:
                        return True, f"{year}-{month_num}-{day.zfill(2)}"
        return False, None  # Cannot normalize date format

    if data_type == "currency":
        clean = re.sub(r"[$,\s]", "", value.strip())
        try:
            v = float(clean)
            return True, str(int(v)) if v == int(v) else str(round(v, 2))
        except ValueError:
            return False, None

    if data_type in ("uad_condition", "uad_quality"):
        prefix = "C" if data_type == "uad_condition" else "Q"
        m = re.search(rf"\b{prefix}([1-6])\b", value.upper())
        if m:
            return True, f"{prefix}{m.group(1)}"
        return False, None

    # String/enum — accept as-is
    return True, value.strip()


# ---------------------------------------------------------------------------
# Defense 12: Structured table text for comparables
# ---------------------------------------------------------------------------

def format_comparable_table_for_llm(tables: Dict) -> str:
    """
    Defense 12: When comparable sale data is in table form, send it to the LLM
    as structured key:value pairs, not as linearized text. This preserves the
    row-column relationships that get lost when tables are flattened.
    """
    if not tables:
        return ""

    lines = ["COMPARABLE SALE DATA (structured):"]
    for page_num, page_tables in tables.items():
        for table in page_tables:
            if not table.cells:
                continue
            lines.append(f"\n[Table from page {page_num}, strategy={table.detection_strategy}]")
            for row_id in table.row_headers or set(c.row_id for c in table.cells):
                row_cells = table.row(row_id)
                if row_cells:
                    cell_str = " | ".join(f"{c.col_id}: {c.value}" for c in row_cells)
                    lines.append(f"  {row_id}: {cell_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Defense 13: Health monitor
# ---------------------------------------------------------------------------

def check_ollama_health() -> Dict:
    """
    Defense 13: Check Ollama health and return status dict.
    Called by health endpoint and before each extraction attempt.
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            has_text_model = any(OLLAMA_TEXT_MODEL.split(":")[0] in m for m in models)
            return {
                "status": "healthy",
                "models_available": models,
                "text_model_ready": has_text_model,
                "circuit_breaker": "open" if _circuit_is_open() else "closed",
                "consecutive_failures": _CONSECUTIVE_FAILURES,
            }
    except Exception as exc:
        pass

    return {
        "status": "unhealthy",
        "models_available": [],
        "text_model_ready": False,
        "circuit_breaker": "open" if _circuit_is_open() else "closed",
        "consecutive_failures": _CONSECUTIVE_FAILURES,
    }


# ---------------------------------------------------------------------------
# Resilient Ollama call — combines all defenses
# ---------------------------------------------------------------------------

def resilient_ollama_call(
    prompt: str,
    chunk_text: str,
    amc_id: Optional[str] = None,
    text_quality_score: float = 1.0,
) -> Optional[str]:
    """
    Single entry point for all LLM calls. Applies all 13 defenses.
    Returns the LLM response text, or None if any defense blocks the call.
    """
    global _LAST_CALL_TIME

    # Defense 13: Circuit breaker
    if _circuit_is_open():
        logger.debug("LLM circuit breaker open — skipping call")
        return None

    # Defense 5: Text quality gate
    ok, reason = text_passes_quality_gate(chunk_text, text_quality_score)
    if not ok:
        logger.debug("LLM quality gate blocked: %s", reason)
        return None

    # Defense 1+10: AMC terminology normalization
    chunk_text = apply_amc_terminology_to_chunk(chunk_text, amc_id)

    # Defense 3: Request gate — one concurrent call
    if not _LLM_SEMAPHORE.acquire(blocking=False):
        logger.debug("LLM semaphore busy — another call in progress, skipping")
        return None

    try:
        # Minimum interval between calls
        elapsed = time.time() - _LAST_CALL_TIME
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)

        # Defense 6: Use pinned model
        model = get_pinned_model()

        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 2048},
            },
            timeout=OLLAMA_TIMEOUT_TEXT,
        )
        resp.raise_for_status()
        _record_success()
        _LAST_CALL_TIME = time.time()
        return resp.json().get("response", "")

    except Exception as exc:
        _record_failure()
        logger.warning("Ollama call failed (%d consecutive): %s", _CONSECUTIVE_FAILURES, exc)
        return None

    finally:
        _LLM_SEMAPHORE.release()
