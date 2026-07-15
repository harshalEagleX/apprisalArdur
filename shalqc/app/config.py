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

    # LLM — 2026-07-13: single-provider (Together only). A second provider
    # (Groq) was tried as a failover but its account tier's tokens-per-minute
    # ceiling was far tighter than Together's own capacity, so a Together
    # slowdown just traded one failure mode for a different, more constrained
    # one. Deleted entirely rather than left disabled — see TogetherPool
    # (app/llm/together_pool.py) for the real fix: a per-key token-bucket +
    # in-flight governor that stops OVER-SENDING instead of reacting to 429s
    # after the fact.
    together_keys: List[str] = field(default_factory=lambda: [
        k for k in (_env("TOGETHER_API_KEY_1"), _env("TOGETHER_API_KEY_2")) if k
    ])
    together_model: str = field(default_factory=lambda: _env("TOGETHER_MODEL", "openai/gpt-oss-120b"))
    together_base_url: str = "https://api.together.xyz/v1/chat/completions"
    # Per-key governor (TogetherPool). tpm_budget is conservative-default; set
    # TOGETHER_TPM_BUDGET_PER_KEY from your actual Together tier limit.
    together_tpm_budget_per_key: int = field(
        default_factory=lambda: int(_env("TOGETHER_TPM_BUDGET_PER_KEY", "60000") or 60000))
    together_max_inflight_per_key: int = field(
        default_factory=lambda: int(_env("TOGETHER_MAX_INFLIGHT_PER_KEY", "8") or 8))
    together_timeout_s: float = field(
        default_factory=lambda: float(_env("TOGETHER_TIMEOUT_S", "45") or 45))

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
        return bool(self.together_keys)

    def __post_init__(self) -> None:
        # Groq was deleted entirely 2026-07-13 (see the LLM block above) — a
        # stray GROQ_* var almost always means a stale deploy config or a
        # leftover local .env, not an intentional setting, since nothing reads
        # it anymore. Fail loudly rather than silently ignoring it, so a
        # config drift gets caught at boot instead of discovered as "why is
        # this key configured but never used."
        stray = [n for n in ("GROQ_API_KEY", "GROQ_MODEL", "GROQ_VISION_API_KEY") if _env(n)]
        if stray:
            raise RuntimeError(
                f"Groq was removed from this codebase (2026-07-13) but {', '.join(stray)} "
                "is still set in the environment — remove it from .env/deployment secrets. "
                "Together AI (TOGETHER_API_KEY_1/2) is the only LLM provider now.")


settings = Settings()
