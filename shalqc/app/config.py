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


_TRUTHY = ("1", "true", "yes", "on")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name)
    return raw.lower() in _TRUTHY if raw else default


@dataclass
class Settings:
    # ── deploy posture ────────────────────────────────────────────────────────
    # One source of truth for "is this a hardened deployment?", mirroring the Java
    # side (app.deploy.strict / a "prod" profile). Everything that must fail-CLOSED
    # in production (auth, signed-bundle gate) keys off `is_production` so there is
    # no second place to forget. Local dev stays fail-OPEN with warnings.
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "dev"))
    deploy_strict: bool = field(default_factory=lambda: _flag("APP_DEPLOY_STRICT"))

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
    # 2026-07-17 measured on a real Together tier (5 golden orders): inflight=8 (× keys)
    # exceeds the tier's request rate → 429s → retry backoffs that made a run BOTH
    # slower AND lossier (ESGA 120s / 18 items fell back to needs_data) than a lower
    # setting (inflight=2 → 22s / 0 fallbacks / +11 items judged). A high setting is
    # counterproductive under 429-retry storms, so the default is conservative — raise
    # TOGETHER_MAX_INFLIGHT_PER_KEY only if your tier's measured rate can take it.
    together_max_inflight_per_key: int = field(
        default_factory=lambda: int(_env("TOGETHER_MAX_INFLIGHT_PER_KEY", "2") or 2))
    together_timeout_s: float = field(
        default_factory=lambda: float(_env("TOGETHER_TIMEOUT_S", "45") or 45))

    llm_max_calls_per_order: int = field(default_factory=lambda: int(_env("LLM_MAX_CALLS_PER_ORDER", "28") or 28))
    llm_cache_ttl_hours: int = field(default_factory=lambda: int(_env("LLM_CACHE_TTL_HOURS", "72") or 72))

    # Judge self-consistency (B3): gpt-oss-120b is non-deterministic even at temp 0
    # (batched attention), so a borderline SATISFIED/NOT_SATISFIED can flip run-to-run
    # and auto-decide an order wrongly. When N>1, decisive verdicts are re-judged N-1
    # more times and any item that is NOT unanimous is downgraded to REVIEW (a human
    # confirms rather than trust a coin-flip). Default 1 = OFF: no extra calls, no
    # behavior change. Only decisive outcomes are re-run (REVIEW/CANNOT_EVALUATE already
    # go to a human), so the cost is bounded to the auto-decided subset, not the order.
    judge_self_consistency_n: int = field(
        default_factory=lambda: max(1, int(_env("JUDGE_SELF_CONSISTENCY_N", "1") or 1)))

    # final_shalqccore.md §9: language|legacy judgment path. "language" runs the
    # language-driven judge (app/language/*) and IS the product; "legacy" keeps the
    # old rule engine only for the test/debug path. Defaults to language so a deploy
    # that forgets JUDGE_MODE runs SHALqc, not the retired engine.
    judge_mode: str = field(default_factory=lambda: _env("JUDGE_MODE", "language") or "language")

    # Step 1 sign-off gate: when true, the runtime refuses to run an AMC checklist
    # whose compiled bundle is not status=active (approved). Resolved in __post_init__
    # so it defaults to ON in production (an unvalidated binding can never reach a live
    # order) while a dev box still runs a draft bundle with a loud degradation.
    # Explicit QC_REQUIRE_SIGNED_BUNDLE always wins.
    require_signed_bundle: bool = False

    @property
    def is_production(self) -> bool:
        """Hardened deployment: strict flag set OR a prod-ish APP_ENV. The single
        switch every fail-closed guard reads."""
        return self.deploy_strict or "prod" in self.app_env.lower()

    @property
    def llm_configured(self) -> bool:
        return bool(self.together_keys)

    def production_problems(self) -> List[str]:
        """Config that MUST be set for a hardened deployment (empty list = OK). Mirrors
        the Java ProductionReadinessValidator so both services fail-closed the same way."""
        problems: List[str] = []
        if not self.internal_api_key:
            problems.append("INTERNAL_API_KEY unset — API auth would be open (set it, or unset APP_DEPLOY_STRICT for dev).")
        if not self.llm_configured:
            problems.append("No TOGETHER_API_KEY_1/2 — the language judge cannot run.")
        if self.judge_mode != "language":
            problems.append(f"JUDGE_MODE='{self.judge_mode}' — production must run the language judge.")
        return problems

    def __post_init__(self) -> None:
        # Signed-bundle gate defaults to is_production; explicit env override wins.
        raw = _env("QC_REQUIRE_SIGNED_BUNDLE")
        self.require_signed_bundle = _flag("QC_REQUIRE_SIGNED_BUNDLE") if raw else self.is_production

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
