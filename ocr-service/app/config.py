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
