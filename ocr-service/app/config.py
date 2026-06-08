"""
Service-wide configuration loaded from environment variables.
Never hardcode database URLs, model names, or thresholds here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://postgres@localhost/ardurApprisal"
)

ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
MODEL_VERSION: str = os.getenv("MODEL_VERSION", "adaptive-1.0.0")

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TEXT_MODEL: str = os.getenv("OLLAMA_TEXT_MODEL", "mistral:7b")
OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "llava:13b")
OLLAMA_TIMEOUT_TEXT: int = int(os.getenv("OLLAMA_TIMEOUT_TEXT", "30"))
OLLAMA_TIMEOUT_VISION: int = int(os.getenv("OLLAMA_TIMEOUT_VISION", "120"))

# Google Cloud Vision (comparable-photo analysis: SCA-27 / SCA-16V).
# VISION_ENABLED gates all cloud calls; the client also requires the
# google-cloud-vision library AND credentials (a service-account JSON via
# GOOGLE_APPLICATION_CREDENTIALS, or a GOOGLE_CLOUD_VISION_API_KEY). When any of
# these is missing the photo rules degrade to VERIFY (graceful, P-6).
VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "false").lower() in ("1", "true", "yes")
GOOGLE_CLOUD_VISION_API_KEY: str = os.getenv("GOOGLE_CLOUD_VISION_API_KEY", "")
GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
VISION_TIMEOUT: int = int(os.getenv("VISION_TIMEOUT", "30"))
VISION_LABEL_SCORE: float = float(os.getenv("VISION_LABEL_SCORE", "0.6"))
# Cost guards (Cloud Vision bills per feature per image):
#   VISION_MAX_PAGES  hard cap on comp-photo pages annotated per appraisal.
#   VISION_DETECT_MLS add TEXT_DETECTION for the MLS-watermark/FHA check (+1 unit/page);
#                     off by default so a normal run is LABEL-only (1 unit/page).
VISION_MAX_PAGES: int = int(os.getenv("VISION_MAX_PAGES", "3"))
VISION_DETECT_MLS: bool = os.getenv("VISION_DETECT_MLS", "false").lower() in ("1", "true", "yes")

# Vision backend selection: "auto" prefers Gemini (AI Studio, free tier, no billing)
# when GEMINI_API_KEY is set, else falls back to Google Cloud Vision. Gemini is a
# multimodal model — one call returns building/MLS/distress/condition as JSON.
VISION_BACKEND: str = os.getenv("VISION_BACKEND", "auto")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT: int = int(os.getenv("GEMINI_TIMEOUT", "40"))
