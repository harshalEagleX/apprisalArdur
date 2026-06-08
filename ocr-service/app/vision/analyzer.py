"""Comparable-photo analyzers — backend-agnostic.

A photo analyzer turns one rendered comp-photo page image into PhotoSignals (the
QC-relevant facts the SCA-27 / SCA-16V rules read). Two backends implement the same
interface; the extractor never knows which one ran:

  • GeminiPhotoAnalyzer   — Google AI Studio (gemini-flash). Multimodal: one call
    returns building / MLS-watermark / distress / condition as JSON. Free tier, no
    billing. Preferred.
  • GoogleVisionPhotoAnalyzer — Google Cloud Vision label/text detection. Coarser
    (generic labels, no condition grade) and requires billing.

get_photo_analyzer() returns the configured analyzer, or None when vision is disabled
or unconfigured — in which case the photo rules degrade to VERIFY/SKIPPED (P-6).

Cost control (P-13): results are cached by image hash so re-processing never re-bills,
and the caller caps how many pages are analyzed (config.VISION_MAX_PAGES).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional

from app import config

logger = logging.getLogger(__name__)

_SIGNAL_CACHE: Dict[str, "PhotoSignals"] = {}
_CACHE_MAX = 2048
_VALID_COND = {"C1", "C2", "C3", "C4", "C5", "C6"}


@dataclass
class PhotoSignals:
    """QC facts read off one comp-photo page. None = "not assessed"."""
    building: bool = False          # page shows residential building/house photos
    distress: bool = False          # a building looks damaged / boarded-up / derelict
    mls_text: Optional[bool] = None  # MLS/realtor/listing watermark text visible
    condition: Optional[str] = None  # apparent UAD condition (C1-C6) of the comps


_PROMPT = (
    "This image is a page from a mortgage appraisal report's COMPARABLE photo addendum. "
    "Respond ONLY as compact JSON with exactly these keys: "
    "is_building (boolean: true if the page shows photographs of residential buildings/houses), "
    "mls_watermark (boolean: true if any MLS / Zillow / Redfin / Realtor / brokerage watermark "
    "or logo text is visible on the photos), "
    "distress (boolean: true if any building appears damaged, boarded-up, derelict, or under "
    "heavy construction), "
    "condition (one of C1, C2, C3, C4, C5, C6, or unknown — the overall UAD condition of the "
    "comparable buildings)."
)


class GeminiPhotoAnalyzer:
    """Google AI Studio (Gemini) multimodal backend."""

    backend = "gemini"

    def __init__(self) -> None:
        self._key = config.GEMINI_API_KEY
        self._url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.GEMINI_MODEL}:generateContent"
        )

    def analyze(self, image_bytes: bytes, want_text: bool = False) -> Optional[PhotoSignals]:
        # want_text is honored for the cost-symmetric Cloud Vision backend; for Gemini
        # every signal comes back in the single call, so it is always populated.
        key = hashlib.sha256(image_bytes).hexdigest()
        if key in _SIGNAL_CACHE:
            return _SIGNAL_CACHE[key]
        import requests
        body = {
            "contents": [{"parts": [
                {"text": _PROMPT},
                {"inline_data": {"mime_type": "image/png",
                                 "data": base64.b64encode(image_bytes).decode()}},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            resp = requests.post(
                self._url,
                headers={"Content-Type": "application/json", "X-goog-api-key": self._key},
                json=body, timeout=config.GEMINI_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Gemini vision HTTP %s: %s", resp.status_code, resp.text[:200])
                return None
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text = next((p["text"] for p in reversed(parts) if "text" in p), "")
            sig = _parse_signals(text)
            if sig and len(_SIGNAL_CACHE) < _CACHE_MAX:
                _SIGNAL_CACHE[key] = sig
            return sig
        except Exception as exc:  # never break the pipeline (P-6)
            logger.warning("Gemini vision failed: %s", exc)
            return None


class GoogleVisionPhotoAnalyzer:
    """Google Cloud Vision label/text backend (coarser, requires billing)."""

    backend = "google_vision"

    _BUILDING = ("house", "building", "home", "residential", "property", "real estate",
                 "cottage", "siding", "roof", "facade", "porch", "driveway")
    _MLS = ("mls", "realtor", "listing", "coldwell", "re/max", "remax", "keller williams",
            "century 21", "zillow", "redfin", "compass")
    _DISTRESS = ("ruins", "demolition", "rubble", "tarp", "boarded", "abandoned",
                 "derelict", "dilapidated")

    def __init__(self) -> None:
        from app.vision.vision_client import get_vision_client
        self._client = get_vision_client()

    def analyze(self, image_bytes: bytes, want_text: bool = False) -> Optional[PhotoSignals]:
        if self._client is None:
            return None
        ann = self._client.annotate(image_bytes, want_text=want_text)
        if ann is None:
            return None
        sig = PhotoSignals(
            building=ann.any_label_contains(*self._BUILDING, min_score=0.55),
            distress=ann.any_label_contains(*self._DISTRESS, min_score=0.5),
        )
        if want_text:
            sig.mls_text = any(t in ann.text.lower() for t in self._MLS)
        return sig


def _parse_signals(text: str) -> Optional[PhotoSignals]:
    try:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
    except Exception:
        return None
    cond = str(data.get("condition", "")).upper().strip()
    return PhotoSignals(
        building=bool(data.get("is_building")),
        distress=bool(data.get("distress")),
        mls_text=bool(data.get("mls_watermark")),
        condition=cond if cond in _VALID_COND else None,
    )


def analyzer_available() -> bool:
    """True when vision is enabled and a backend is actually configured."""
    if not config.VISION_ENABLED:
        return False
    backend = (config.VISION_BACKEND or "auto").lower()
    if backend in ("auto", "gemini") and config.GEMINI_API_KEY:
        return True
    if backend in ("auto", "google_vision"):
        from app.vision.vision_client import vision_available
        return vision_available()
    return False


def get_photo_analyzer():
    """Return the configured PhotoSignals analyzer, or None (rules then VERIFY)."""
    if not config.VISION_ENABLED:
        return None
    backend = (config.VISION_BACKEND or "auto").lower()
    if backend in ("auto", "gemini") and config.GEMINI_API_KEY:
        return GeminiPhotoAnalyzer()
    if backend in ("auto", "google_vision"):
        from app.vision.vision_client import vision_available
        if vision_available():
            return GoogleVisionPhotoAnalyzer()
    return None
