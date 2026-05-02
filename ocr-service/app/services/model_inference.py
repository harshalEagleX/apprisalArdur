"""Runtime loaders for trained PKL models.

Models are optional: if a PKL is missing or incompatible, inference falls back
to existing deterministic logic.
"""

from __future__ import annotations

import logging
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "training" / "models"


@lru_cache(maxsize=1)
def _load_model(filename: str) -> Optional[dict]:
    path = MODELS_DIR / filename
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            model = pickle.load(handle)
        logger.info("Loaded runtime model %s", filename)
        return model
    except Exception as exc:
        logger.info("Failed to load runtime model %s: %s", filename, exc)
        return None


def correct_ocr_value(value: str) -> tuple[str, bool]:
    model = _load_model("ocr_correction_model.pkl")
    if not model or not value:
        return value, False
    try:
        vectorizer = model.get("vectorizer")
        classifier = model.get("classifier")
        if not vectorizer or not classifier:
            return value, False
        prediction = classifier.predict(vectorizer.transform([value]))[0]
        prediction = str(prediction)
        return prediction, prediction != value
    except Exception as exc:
        logger.debug("OCR correction model inference failed: %s", exc)
        return value, False


def classify_commentary_fast(text: str) -> Optional[tuple[bool, float]]:
    model = _load_model("commentary_classifier.pkl")
    if not model or not text:
        return None
    try:
        pipeline = model.get("pipeline")
        if not pipeline:
            return None
        label = str(pipeline.predict([text])[0]).upper()
        confidence = 0.0
        if hasattr(pipeline, "predict_proba"):
            confidence = float(max(pipeline.predict_proba([text])[0]))
        is_canned = label in {"CANNED", "TRUE", "1", "GENERIC"}
        return is_canned, confidence
    except Exception as exc:
        logger.debug("Commentary classifier inference failed: %s", exc)
        return None


def calibrate_confidence(text: str, *signals: float) -> float:
    baseline = sum(signals) / len(signals) if signals else 0.7
    model = _load_model("confidence_model.pkl")
    if not model or not text:
        return max(0.0, min(1.0, baseline))
    try:
        pipeline = model.get("pipeline")
        if not pipeline:
            return max(0.0, min(1.0, baseline))
        predicted = float(pipeline.predict([text])[0])
        return max(0.0, min(1.0, (baseline + predicted) / 2.0))
    except Exception as exc:
        logger.debug("Confidence model inference failed: %s", exc)
        return max(0.0, min(1.0, baseline))
