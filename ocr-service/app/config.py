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

# ---------------------------------------------------------------------------
# Extraction layer version — bump on every extraction-behaviour change so
# results stay traceable to the logic that produced them (P-5/P-11 lineage).
EXTRACTION_LAYER_VERSION: str = os.getenv("EXTRACTION_LAYER_VERSION", "0.1.13")

# Groq LLM — the structured-extraction "brain" (NOT OCR). OCR stays the "eyes";
# this reads OCR text and returns structured fields. Used today to read the SCA
# comparable-sales grid when the deterministic table readers are unreliable.
# OpenAI-compatible API. gpt-oss-120b is a reasoning model → force JSON output
# with a low reasoning effort. Keys live in .env (gitignored), never in code.
LLM_EXTRACTION_ENABLED: bool = os.getenv("LLM_EXTRACTION_ENABLED", "true").lower() in ("1", "true", "yes")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TIMEOUT: int = int(os.getenv("GROQ_TIMEOUT", "45"))
GROQ_REASONING_EFFORT: str = os.getenv("GROQ_REASONING_EFFORT", "low")
# Client-side tokens-per-minute budget for the extraction model (Groq free tier
# limit is 8000 TPM; stay under it). When a call would exceed the rolling-60s
# budget the client waits — so a multi-page grid is processed in steps rather
# than 429-failing. Tune to your plan.
GROQ_TPM_LIMIT: int = int(os.getenv("GROQ_TPM_LIMIT", "6000"))
# Force the SCA LLM extractor to run even when deterministic extraction looks ok
# (A/B measurement). Default off → LLM runs only as a repair/fallback.
SCA_LLM_ALWAYS: bool = os.getenv("SCA_LLM_ALWAYS", "false").lower() in ("1", "true", "yes")

# Groq vision — fallback for comparable-photo analysis when Gemini fails or is
# rate-limited. Separate key/model (llama-4-scout multimodal). Image OCR/vision
# still prefers Gemini; Groq is the resilience backstop.
GROQ_VISION_API_KEY: str = os.getenv("GROQ_VISION_API_KEY", "")
GROQ_VISION_MODEL: str = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
