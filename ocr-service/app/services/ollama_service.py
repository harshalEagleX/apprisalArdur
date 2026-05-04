"""
Ollama Service — local LLM inference for appraisal QC commentary analysis.

Models: llava:7b for both text and vision by default.

Setup (one-time):
    ollama pull llava:7b

All calls are synchronous (this service runs inside a threadpool in FastAPI).
Temperature is fixed at 0 for deterministic QC decisions.
"""

import json
import logging
import os
import re
import asyncio
import base64
import io
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "llava:7b")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "45.0"))  # seconds
OLLAMA_TEXT_NUM_CTX = int(os.getenv("OLLAMA_TEXT_NUM_CTX", "1024"))
OLLAMA_VISION_NUM_CTX = int(os.getenv("OLLAMA_VISION_NUM_CTX", "1024"))
OLLAMA_TEXT_KEEP_ALIVE = os.getenv("OLLAMA_TEXT_KEEP_ALIVE", "10m")
OLLAMA_VISION_KEEP_ALIVE = os.getenv("OLLAMA_VISION_KEEP_ALIVE", "10m")
OLLAMA_MAX_CONCURRENCY = int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1"))
_TEXT_MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar("ollama_text_model", default=None)
_VISION_MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar("ollama_vision_model", default=None)
_REQUEST_OLLAMA_DISABLED: ContextVar[bool] = ContextVar("ollama_request_disabled", default=False)
_OLLAMA_SEMAPHORES: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except Exception:
    OPENCV_AVAILABLE = False


def _ollama_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _OLLAMA_SEMAPHORES.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(OLLAMA_MAX_CONCURRENCY)
        _OLLAMA_SEMAPHORES[loop] = semaphore
    return semaphore


def get_active_text_model() -> str:
    return _TEXT_MODEL_OVERRIDE.get() or OLLAMA_MODEL


def get_active_vision_model() -> str:
    return _VISION_MODEL_OVERRIDE.get() or OLLAMA_VISION_MODEL


@contextmanager
def use_model_selection(text_model: Optional[str] = None, vision_model: Optional[str] = None):
    text_token = _TEXT_MODEL_OVERRIDE.set(text_model or OLLAMA_MODEL)
    vision_token = _VISION_MODEL_OVERRIDE.set(vision_model or OLLAMA_VISION_MODEL)
    try:
        yield
    finally:
        _TEXT_MODEL_OVERRIDE.reset(text_token)
        _VISION_MODEL_OVERRIDE.reset(vision_token)


@contextmanager
def ollama_request_guard():
    """
    Bound the blast radius of slow/downstream Ollama failures to a single QC request.

    Once a request experiences a hard Ollama timeout we short-circuit later LLM calls
    in the same request and let deterministic fallbacks finish the pipeline quickly.
    """
    disable_token = _REQUEST_OLLAMA_DISABLED.set(False)
    try:
        yield
    finally:
        _REQUEST_OLLAMA_DISABLED.reset(disable_token)


def _ollama_disabled_for_request() -> bool:
    return _REQUEST_OLLAMA_DISABLED.get()


def _disable_ollama_for_request(reason: str, *, model: str) -> None:
    if not _REQUEST_OLLAMA_DISABLED.get():
        logger.warning(
            "Disabling further Ollama calls for this QC request after %s (model=%s); deterministic fallbacks will continue.",
            reason,
            model,
        )
    _REQUEST_OLLAMA_DISABLED.set(True)


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
        model = get_active_text_model()
        return any(model in m for m in models)
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
    if _ollama_disabled_for_request():
        return None
    payload = {
        "model": get_active_text_model(),
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": OLLAMA_TEXT_KEEP_ALIVE,
        "options": {
            "temperature": 0.0,
            "num_ctx": OLLAMA_TEXT_NUM_CTX,
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
        logger.info("Ollama request timed out (model=%s)", get_active_text_model())
        _disable_ollama_for_request("text timeout", model=get_active_text_model())
        return None
    except httpx.HTTPStatusError as e:
        logger.info("Ollama HTTP error: %s", e)
        return None
    except Exception as e:
        logger.info("Ollama call failed: %s", e)
        return None


def _detect_checkbox_state_opencv(crop_image) -> Optional[bool]:
    """
    Cheap local checkbox detector for small form crops.

    Returns:
        True when a checkbox appears confidently marked
        False when a checkbox appears confidently empty
        None when no confident checkbox box is found
    """
    if not OPENCV_AVAILABLE:
        return None

    try:
        if hasattr(crop_image, "convert"):
            gray = np.array(crop_image.convert("L"))
        else:
            gray = crop_image

        if gray is None or gray.size == 0:
            return None

        # Focus on the left side where form checkboxes usually sit.
        width = gray.shape[1]
        roi = gray[:, :max(40, int(width * 0.45))]
        if roi.size == 0:
            return None

        blurred = cv2.GaussianBlur(roi, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            7,
        )

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_candidate: Optional[tuple[float, bool]] = None

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < 36 or area > 2500:
                continue
            aspect = w / float(h or 1)
            if not 0.65 <= aspect <= 1.35:
                continue

            contour_area = cv2.contourArea(contour)
            if contour_area < area * 0.35:
                continue

            pad = 2
            x1 = max(0, x + pad)
            y1 = max(0, y + pad)
            x2 = min(thresh.shape[1], x + w - pad)
            y2 = min(thresh.shape[0], y + h - pad)
            if x2 <= x1 or y2 <= y1:
                continue

            inner = thresh[y1:y2, x1:x2]
            fill_ratio = float(np.count_nonzero(inner)) / float(inner.size or 1)

            # Empty checkbox tends to keep only border pixels.
            if fill_ratio <= 0.10:
                score = contour_area
                candidate = (score, False)
            # Marked checkbox has noticeably denser interior strokes.
            elif fill_ratio >= 0.22:
                score = contour_area + fill_ratio
                candidate = (score, True)
            else:
                continue

            if best_candidate is None or candidate[0] > best_candidate[0]:
                best_candidate = candidate

        if best_candidate is None:
            return None
        return best_candidate[1]

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Task 1: Canned commentary detection (N-6, N-7 rules)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Checkbox detection via OpenCV first, then the configured vision model.
# Only called when OCR text-pattern detection returned None (uncertain)
# ---------------------------------------------------------------------------

def detect_checkbox_vision(page_image, label_text: str) -> Optional[bool]:
    """
    Use OpenCV first, then the configured vision model, to detect checkbox state.

    Strategy:
      1. Use pytesseract.image_to_data to locate the label text on the page
      2. Crop a region around/left-of the label (where checkboxes appear in UAD forms)
      3. Run a fast OpenCV checkbox detector on the crop
      4. If still uncertain, send the crop to Ollama vision: "Is the checkbox checked? YES or NO only."

    Returns:
        True  = local detector/model says checkbox is checked
        False = local detector/model says checkbox is NOT checked
        None  = no confident checkbox state found
    """
    try:
        if _ollama_disabled_for_request():
            return None
        import base64
        import io
        import numpy as np
        import pytesseract
        from PIL import Image as PILImage

        # Convert to PIL if it's a numpy array
        if not isinstance(page_image, PILImage.Image):
            page_image = PILImage.fromarray(page_image)

        # Find the label text position using Tesseract bounding boxes
        page_gray = page_image.convert("L")
        data = pytesseract.image_to_data(page_gray, output_type=pytesseract.Output.DICT)

        label_words = label_text.lower().split()
        label_x, label_y, label_h = None, None, None

        for i, word in enumerate(data["text"]):
            if word.lower() in label_words and data["conf"][i] > 30:
                label_x = data["left"][i]
                label_y = data["top"][i]
                label_h = data["height"][i]
                break

        if label_x is None:
            # Label not found — send a 200×50 header strip and ask generally
            strip = page_gray.crop((0, 0, min(page_gray.width, 800), min(page_gray.height, 200)))
        else:
            # Crop: region to the left of and around the label (checkbox is left of label)
            pad = max(label_h * 2, 30)
            x1 = max(0, label_x - pad * 4)
            y1 = max(0, label_y - pad)
            x2 = min(page_gray.width, label_x + pad * 2)
            y2 = min(page_gray.height, label_y + pad * 2)
            strip = page_gray.crop((x1, y1, x2, y2))

        opencv_result = _detect_checkbox_state_opencv(strip)
        if opencv_result is not None:
            return opencv_result

        # Encode as base64 PNG for Ollama vision API
        buf = io.BytesIO()
        strip.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        prompt = (
            f'Look at this image from an appraisal form. '
            f'Is the checkbox next to "{label_text}" marked with an X or checkmark? '
            f'Answer YES if checked or NO if empty. One word only.'
        )

        payload = {
            "model": get_active_vision_model(),
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "keep_alive": OLLAMA_VISION_KEEP_ALIVE,
            "options": {
                "temperature": 0.0,
                "num_ctx": OLLAMA_VISION_NUM_CTX,
                "num_predict": 5,
            },
        }

        r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=min(OLLAMA_TIMEOUT, 15.0))
        r.raise_for_status()
        response = r.json().get("response", "").strip().upper()

        if "YES" in response:
            return True
        if "NO" in response:
            return False
        return None

    except httpx.TimeoutException:
        logger.info("Ollama checkbox vision request timed out (model=%s)", get_active_vision_model())
        _disable_ollama_for_request("vision timeout", model=get_active_vision_model())
        return None
    except Exception as e:
        logger.debug("llava:13b checkbox detection failed for '%s': %s", label_text, e)
        return None


def is_vision_model_available() -> bool:
    """Check if the single configured llava:13b model is loaded in Ollama."""
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        model = get_active_vision_model()
        return any(model in m for m in models)
    except Exception:
        return False


def is_llava_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        model = get_active_vision_model()
        return "llava" in model.lower() and any(model in m for m in models)
    except Exception:
        return False


async def generate_async(prompt: str, system: str = "", max_tokens: int = 256) -> Optional[str]:
    if _ollama_disabled_for_request():
        return None
    payload = {
        "model": get_active_text_model(),
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": OLLAMA_TEXT_KEEP_ALIVE,
        "options": {
            "temperature": 0.0,
            "num_ctx": OLLAMA_TEXT_NUM_CTX,
            "num_predict": max_tokens,
            "top_k": 1,
        },
    }
    try:
        async with _ollama_semaphore():
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "").strip()
    except httpx.TimeoutException:
        logger.info("Async Ollama request timed out (model=%s)", get_active_text_model())
        _disable_ollama_for_request("async text timeout", model=get_active_text_model())
        return None
    except Exception as exc:
        logger.info("Async Ollama call failed: %s: %s", exc.__class__.__name__, exc)
        return None


async def gather_text_prompts(prompts: list[tuple[str, str, int]]) -> list[Optional[str]]:
    return await asyncio.gather(
        *(generate_async(prompt, system=system, max_tokens=max_tokens) for prompt, system, max_tokens in prompts)
    )


async def analyze_photo_llava(page_image, prompt: str) -> Optional[str]:
    if _ollama_disabled_for_request():
        return None
    try:
        from PIL import Image as PILImage
        if not isinstance(page_image, PILImage.Image):
            page_image = PILImage.fromarray(page_image)
        buf = io.BytesIO()
        page_image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        payload = {
            "model": get_active_vision_model(),
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "keep_alive": OLLAMA_VISION_KEEP_ALIVE,
            "options": {"temperature": 0.0, "num_ctx": OLLAMA_VISION_NUM_CTX, "num_predict": 120},
        }
        async with _ollama_semaphore():
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "").strip()
    except httpx.TimeoutException:
        logger.info("Ollama photo analysis timed out (model=%s)", get_active_vision_model())
        _disable_ollama_for_request("photo vision timeout", model=get_active_vision_model())
        return None
    except Exception as exc:
        logger.debug("llava:13b photo analysis failed: %s", exc)
        return None


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
    Classify commentary as canned or specific using the configured llava:13b model.

    Returns:
        True  = canned (generic)
        False = specific (good)
        None  = ollama unavailable or inconclusive
    """
    if not text or len(text.strip()) < 20:
        return None

    try:
        from app.services.model_inference import classify_commentary_fast
        fast = classify_commentary_fast(text)
        if fast is not None:
            is_canned, confidence = fast
            if confidence >= 0.90:
                return is_canned
    except Exception:
        pass

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


VERIFY_QUESTION_SYSTEM = (
    "You are a mortgage appraisal QC assistant. Generate one specific human-review "
    "question. Use the actual values and document reference. Output only the question."
)


def generate_verify_question(
    *,
    rule_description: str,
    field_name: str,
    extracted_value: object = None,
    expected_value: object = None,
    confidence: float = 0.0,
    evidence: str = "",
) -> Optional[str]:
    prompt = f"""
Rule being checked: {rule_description}
Field: {field_name}
Value extracted from appraisal: {extracted_value}
Expected/reference value: {expected_value}
Confidence: {confidence:.2f}
Evidence/document location: {evidence or "not specified"}

Generate a single, specific question for the human reviewer.
The question must reference the actual values and the document location when available.
Do not add explanations, bullets, or meta-commentary.
""".strip()
    response = _generate(prompt, system=VERIFY_QUESTION_SYSTEM, max_tokens=120)
    if not response:
        return None
    return response.strip().splitlines()[0].strip().strip('"')


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
