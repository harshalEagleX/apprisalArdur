"""Google Cloud Vision client — thin, lazy, gracefully degrading.

Contract (P-12):
  • Input: PNG/JPEG image bytes.
  • Output: VisionAnnotation (labels, full OCR text, localized object names).
  • Availability: vision_available() is True only when VISION_ENABLED is set AND the
    google-cloud-vision library is importable AND credentials are present (a
    service-account JSON via GOOGLE_APPLICATION_CREDENTIALS, or an API key via
    GOOGLE_CLOUD_VISION_API_KEY). Otherwise get_vision_client() returns None and the
    photo rules degrade to VERIFY (P-6 — no cloud call, no billing, no crash).
  • Errors: annotate() returns None on any per-image API failure (the caller treats a
    missing annotation as "could not verify" → VERIFY), never raises to the pipeline.

The library is imported lazily inside the client so importing this module never
requires google-cloud-vision to be installed.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app import config

logger = logging.getLogger(__name__)

# Image-hash -> annotation cache so re-processing a document never re-bills (P-13).
_ANNOTATION_CACHE: Dict[tuple, "VisionAnnotation"] = {}
_CACHE_MAX = 2048


@dataclass
class VisionAnnotation:
    """One image's annotations, normalized away from the SDK's proto types."""
    labels: List[Tuple[str, float]] = field(default_factory=list)  # (description, score)
    text: str = ""                                                 # full OCR text
    objects: List[str] = field(default_factory=list)               # localized object names

    def has_label(self, *names: str, min_score: float = 0.0) -> bool:
        low = {n.lower() for n in names}
        return any(desc.lower() in low and score >= min_score for desc, score in self.labels)

    def any_label_contains(self, *substrings: str, min_score: float = 0.0) -> bool:
        subs = [s.lower() for s in substrings]
        return any(score >= min_score and any(s in desc.lower() for s in subs)
                   for desc, score in self.labels)


def _credentials_present() -> bool:
    if config.GOOGLE_CLOUD_VISION_API_KEY:
        return True
    cred = config.GOOGLE_APPLICATION_CREDENTIALS or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return bool(cred) and os.path.exists(cred)


def vision_available() -> bool:
    """True only when the feature is enabled, the library is importable, and creds exist."""
    if not config.VISION_ENABLED:
        return False
    if not _credentials_present():
        return False
    try:
        import google.cloud.vision  # noqa: F401
    except Exception:
        return False
    return True


class VisionClient:
    """Wraps google-cloud-vision; one instance is reused across a transaction."""

    def __init__(self) -> None:
        from google.cloud import vision  # lazy: only when actually constructed
        self._vision = vision
        api_key = config.GOOGLE_CLOUD_VISION_API_KEY
        if api_key:
            from google.api_core.client_options import ClientOptions
            self._client = vision.ImageAnnotatorClient(
                client_options=ClientOptions(api_key=api_key))
        else:
            # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
            self._client = vision.ImageAnnotatorClient()

    def annotate(self, image_bytes: bytes, want_text: bool = False) -> Optional[VisionAnnotation]:
        """Annotate one image. None on any failure.

        Cost control (P-4/P-13): Cloud Vision bills PER FEATURE PER IMAGE. We request
        only LABEL_DETECTION by default (building + distress signals); TEXT_DETECTION
        (the MLS-watermark check) is added only when want_text is set, so a typical
        conventional appraisal costs 1 unit/page, not 3. Results are cached by image
        hash so re-processing a document never re-bills.
        """
        key = (hashlib.sha256(image_bytes).hexdigest(), bool(want_text))
        if key in _ANNOTATION_CACHE:
            return _ANNOTATION_CACHE[key]
        try:
            vision = self._vision
            image = vision.Image(content=image_bytes)
            features = [vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION, max_results=15)]
            if want_text:
                features.append(vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION))
            request = vision.AnnotateImageRequest(image=image, features=features)
            resp = self._client.annotate_image(request, timeout=config.VISION_TIMEOUT)
            if resp.error and resp.error.message:
                logger.warning("Vision API error: %s", resp.error.message)
                return None
            labels = [(l.description, float(l.score)) for l in resp.label_annotations]
            text = resp.full_text_annotation.text if (want_text and resp.full_text_annotation) else ""
            ann = VisionAnnotation(labels=labels, text=text or "", objects=[])
            if len(_ANNOTATION_CACHE) < _CACHE_MAX:
                _ANNOTATION_CACHE[key] = ann
            return ann
        except Exception as exc:  # never break the pipeline on a vision failure (P-6)
            logger.warning("Vision annotate failed: %s", exc)
            return None


_CLIENT: Optional[VisionClient] = None
_TRIED = False


def get_vision_client() -> Optional[VisionClient]:
    """Return a cached client, or None when vision is unavailable (no crash, no cost)."""
    global _CLIENT, _TRIED
    if not vision_available():
        return None
    if _CLIENT is None and not _TRIED:
        _TRIED = True
        try:
            _CLIENT = VisionClient()
        except Exception as exc:
            logger.warning("Vision client construction failed: %s", exc)
            _CLIENT = None
    return _CLIENT
