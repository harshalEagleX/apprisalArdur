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
EXTRACTION_LAYER_VERSION: str = os.getenv("EXTRACTION_LAYER_VERSION", "0.1.16")

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

# ── QC rule-engine version ─────────────────────────────────────────────────────
# Semantic version of the QC ruleset's LOGIC — bump when rule behaviour changes.
# It is combined at runtime with an auto-computed fingerprint of the registered
# rule ids, so the stamp also changes when rules are added/removed even if this
# string isn't bumped. Stamped on every QCResult so a finding that appears or
# disappears between two runs is attributable to a rule change vs a report change.
QC_RULESET_VERSION: str = os.getenv("QC_RULESET_VERSION", "qc-1.0.0")

# ── Field locator (reviewer click-to-scroll) ───────────────────────────────────
# After extraction, locate each found value's bounding box on its page so the
# reviewer UI can scroll to and highlight the exact field. Coordinates are
# normalized [0,1] fractions of the page (top-left origin) — what the PDF viewer
# expects. Precision-gated per the MIRA spec: ambiguous / too-short / too-long
# values fall back to a page-level reference (no box).
FIELD_LOCATOR_ENABLED: bool = os.getenv("FIELD_LOCATOR_ENABLED", "true").lower() in ("1", "true", "yes")
# Value strings shorter than this (normalized) are too ambiguous to highlight
# precisely (e.g. "C3", "Q4", "Yes") unless their page is already known AND the
# value occurs exactly once on that page.
FIELD_LOCATOR_MIN_LEN: int = int(os.getenv("FIELD_LOCATOR_MIN_LEN", "4"))
# Value strings longer than this are narrative/paragraph text — a single box is
# not meaningful, so they stay page-level only.
FIELD_LOCATOR_MAX_LEN: int = int(os.getenv("FIELD_LOCATOR_MAX_LEN", "80"))
# Pad the located box by this fraction of the page on every side so the highlight
# sits comfortably around the text rather than clipping it.
FIELD_LOCATOR_PAD: float = float(os.getenv("FIELD_LOCATOR_PAD", "0.004"))
