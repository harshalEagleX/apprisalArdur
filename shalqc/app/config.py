"""
app.config — one place that reads the environment (.env) into typed settings.

Loads `.env` from the shalqc folder at import (python-dotenv), so every module
imports settings from here instead of scattering os.environ reads. Secrets never
appear in code — only in the gitignored .env (SHALqc.md §10 / §17 PII rules).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    # auth
    internal_api_key: str = field(default_factory=lambda: _env("INTERNAL_API_KEY"))
    # storage
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL"))
    redis_llm_cache_url: str = field(default_factory=lambda: _env("REDIS_LLM_CACHE_URL") or _env("REDIS_URL"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # LLM — SHALqc.md §10: 2× openai/gpt-oss-120b, primary → fallback
    together_keys: List[str] = field(default_factory=lambda: [
        k for k in (_env("TOGETHER_API_KEY_1"), _env("TOGETHER_API_KEY_2")) if k
    ])
    together_model: str = field(default_factory=lambda: _env("TOGETHER_MODEL", "openai/gpt-oss-120b"))
    together_base_url: str = "https://api.together.xyz/v1/chat/completions"
    groq_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "openai/gpt-oss-120b"))
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions"

    llm_max_calls_per_order: int = field(default_factory=lambda: int(_env("LLM_MAX_CALLS_PER_ORDER", "28") or 28))
    llm_cache_ttl_hours: int = field(default_factory=lambda: int(_env("LLM_CACHE_TTL_HOURS", "72") or 72))

    # final_shalqccore.md §9: language|legacy judgment path. "language" runs the
    # v1.0.69 language-driven judge (app/language/*); "legacy" keeps the rule
    # engine. Both share extraction/locate/report; roll out flips this default.
    judge_mode: str = field(default_factory=lambda: _env("JUDGE_MODE", "legacy") or "legacy")

    # Step 1 sign-off gate: when true, the runtime refuses to run an AMC checklist
    # whose compiled bundle is not status=active (approved). Off by default so a
    # fresh environment still runs (with a loud degradation); flip on in prod so an
    # unvalidated binding can never reach a live order.
    require_signed_bundle: bool = field(
        default_factory=lambda: _env("QC_REQUIRE_SIGNED_BUNDLE", "false").lower() in ("1", "true", "yes"))

    @property
    def llm_configured(self) -> bool:
        return bool(self.together_keys or self.groq_key)


settings = Settings()
