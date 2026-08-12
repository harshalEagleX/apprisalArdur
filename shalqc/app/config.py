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
    # Rate limits are PER KEY, so each additional key is a linear throughput gain
    # with NO extra 429 risk (unlike raising per-key inflight, which contends on
    # one key's budget). Reads TOGETHER_API_KEY_1..8 so adding a key to .env is
    # all it takes to widen the pipe — the TogetherPool round-robins across them.
    together_keys: List[str] = field(default_factory=lambda: [
        k for k in (_env(f"TOGETHER_API_KEY_{i}") for i in range(1, 9)) if k
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
    #
    # 2026-07-18 RE-MEASURED after the TogetherPool refund fix, on the theory that
    # the 2026-07-17 result was an artifact of a permanently-starved token bucket.
    # It was not — the conclusion holds. Same order (ESGA-0005949), caching fully
    # disabled, cold both ways:
    #     inflight=2 (4 slots)  → 83.1s, s6=0
    #     inflight=4 (8 slots)  → 92.4s, s6=0   ← SLOWER
    # Provider per-key throughput is the ceiling, so extra in-flight requests buy
    # contention rather than parallelism. Concurrency is NOT the latency lever here;
    # more API KEYS (limits are per-key) or fewer/smaller judge calls are.
    together_max_inflight_per_key: int = field(
        default_factory=lambda: int(_env("TOGETHER_MAX_INFLIGHT_PER_KEY", "2") or 2))
    # 2026-07-18 (unjudged-loss investigation): 45s was BELOW the real tail. On a
    # cold ESNC-0006153 run the judge's p50 call was 9.5s but three batches sat at
    # exactly 45.0s — clipped by this ceiling, not answered slowly — and each took
    # its whole batch down to REVIEW llm_unavailable (8 items). The ceiling only
    # binds on calls that are already slow, so raising it costs nothing on the
    # 9.5s median and buys back the tail. `_call_timeout_s` in llm/client.py scales
    # the effective per-call budget by the requested max_tokens on top of this.
    together_timeout_s: float = field(
        default_factory=lambda: float(_env("TOGETHER_TIMEOUT_S", "120") or 120))

    # ── extraction ────────────────────────────────────────────────────────────
    # Was a hardcoded `max_pages: int = 8` in pdf_digital/pdf_scanned — right for a
    # 1004, blind for the 40-page UAD 3.6 URAR whose entire valuation (market trends,
    # listing history, 6-comp grid, reconciliation, certifications) lives on pages
    # 9-40. 60 covers a long 3.6 report with room; a 1004 still costs 8 pages of work
    # because the loop stops at len(doc).
    extract_max_pages: int = field(default_factory=lambda: int(_env("EXTRACT_MAX_PAGES", "60") or 60))

    # ── UAD 3.6 vision extraction (app/extraction/vision/) ────────────────────
    # Single provider preserved: Together serves BOTH the judge (gpt-oss-120b) and
    # the 3.6 page transcription (gemma-4-31B-it). Different jobs on one account —
    # the judge reasons over already-extracted facts, the extractor reads pixels.
    #
    # SERVERLESS ONLY. The obvious-looking pick, Qwen3-VL-32B, is dedicated-only on
    # Together: using it means provisioning a GPU endpoint billed per hour whether
    # or not an order is processed (~$6.49/hr H100, ~$4.7k/month at 24/7), plus
    # cold-start latency at sparse traffic. That is a growth lever at sustained
    # high volume, not a starting point. gemma-4-31B-it is serverless, takes
    # Text+Image input, and supports JSON Mode.
    #
    # An Anthropic backend is implemented behind the same VisionProvider interface
    # and is one env var away (VISION_PROVIDER=anthropic) if the grid turns out to
    # need a stronger reader — the budget band ($0.50-0.75/order) affords it.
    vision_provider: str = field(default_factory=lambda: _env("VISION_PROVIDER", "together") or "together")
    vision_model: str = field(
        default_factory=lambda: _env("VISION_MODEL", "google/gemma-4-31B-it") or "google/gemma-4-31B-it")
    # Per-tier overrides. Default: the same verified model everywhere. Point
    # VISION_MODEL_ESCALATE at a different family for an uncorrelated second
    # opinion on a checksum failure, once that model's image support is verified.
    vision_model_section: str = field(
        default_factory=lambda: _env("VISION_MODEL_SECTION", "google/gemma-4-31B-it") or "google/gemma-4-31B-it")
    vision_model_grid: str = field(
        default_factory=lambda: _env("VISION_MODEL_GRID", "google/gemma-4-31B-it") or "google/gemma-4-31B-it")
    vision_model_escalate: str = field(
        default_factory=lambda: _env("VISION_MODEL_ESCALATE", "google/gemma-4-31B-it") or "google/gemma-4-31B-it")
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    # Dedicated Together key for VISION. Together's rate limits are PER KEY, so
    # giving extraction its own key means a 40-page order's image traffic cannot
    # eat the judge's token budget and trigger the 429-retry storms that made
    # runs both slower AND lossier (see the together_max_inflight_per_key note
    # above). Falls back to the shared pool when unset, so this is an
    # optimisation rather than a requirement.
    together_vision_api_key: str = field(default_factory=lambda: _env("TOGETHER_API_GEMMA"))
    # Render DPI. MEASURED against this provider, and the result is blunt:
    #
    #     DPI    pixels        upload    prompt_tokens   address read
    #      72    612x792        91 KB        298         correct
    #     130    1105x1430     205 KB        298         correct
    #     200    1700x2200     322 KB        298         correct
    #
    # The token count is IDENTICAL at every DPI — Together downscales server-side
    # to a fixed internal representation — so raising DPI buys no extra detail
    # and no extra accuracy, only upload bytes. At high concurrency those bytes
    # are actively harmful: oversized payloads produced connection failures that
    # cost whole sections.
    #
    # This is also exactly WHY the grid is read as per-comparable column CROPS
    # (render.label_and_column_clips). Since the model always sees a fixed-size
    # image, a crop is genuinely higher effective resolution — the same budget
    # spent on one column instead of on four columns plus margin.
    vision_dpi_section: int = field(default_factory=lambda: int(_env("VISION_DPI_SECTION", "100") or 100))
    vision_dpi_grid: int = field(default_factory=lambda: int(_env("VISION_DPI_GRID", "110") or 110))
    vision_dpi_retry: int = field(default_factory=lambda: int(_env("VISION_DPI_RETRY", "150") or 150))
    # Hard per-order spend ceiling in USD. The governor stops issuing calls when the
    # projected cost of the NEXT call would breach it, so an order degrades to REVIEW
    # cards instead of silently overrunning the budget. User-set band: $0.50-0.75.
    vision_budget_usd_per_order: float = field(
        default_factory=lambda: float(_env("VISION_BUDGET_USD_PER_ORDER", "0.75") or 0.75))
    # Checksum-failure retries per region (re-prompt with the arithmetic error, then
    # escalate DPI). 0 disables the retry loop entirely.
    vision_max_retries: int = field(default_factory=lambda: int(_env("VISION_MAX_RETRIES", "2") or 2))
    # Output-token ceilings. MEASURED, not guessed: gemma-4-31B-it is a REASONING
    # model — it writes into a `reasoning` field before emitting `content`, so the
    # ceiling must cover deliberation PLUS the JSON. A 24-field section consumed
    # ~2,900 output tokens; at 1,500 it ran out mid-reasoning and returned an
    # EMPTY content field, i.e. full latency and full token spend for nothing.
    #
    # But a ceiling is NOT free to over-size, which the "generous on purpose" note
    # here used to claim. Two costs bite from the other side:
    #
    #   * Output generates serially at a measured 25 tok/s floor under concurrency,
    #     so a 9,000-token ceiling is ~360s of wall clock — beyond the 180s read
    #     timeout. Calls that need the headroom time out while working correctly.
    #   * A call that actually REACHES its ceiling has truncated, so it returns
    #     nothing. Run 14 spent 27,000 output tokens — 36% of the order — on three
    #     grid calls pinned at exactly 9,000 that produced zero fields.
    #
    # Keep `ceiling / 25 tok/s` inside the provider's read timeout. The provider
    # logs a warning when a configured ceiling breaches that relationship.
    vision_max_tokens_section: int = field(
        default_factory=lambda: int(_env("VISION_MAX_TOKENS_SECTION", "10000") or 10000))
    # One page's half of one comparable. 4,500 was measured too LOW: eight of run
    # 16's twelve grid calls stopped at exactly 4,500, i.e. truncated. A dense
    # crop needs more room than that, and at concurrency 8 it can be afforded —
    # 6,000 tokens is ~85s at the ~70 tok/s uncontended rate, comfortably inside
    # the read timeout, where at concurrency 23 the same call took 300s and died.
    vision_max_tokens_grid: int = field(
        default_factory=lambda: int(_env("VISION_MAX_TOKENS_GRID", "6000") or 6000))
    vision_max_tokens_triage: int = field(
        default_factory=lambda: int(_env("VISION_MAX_TOKENS_TRIAGE", "4000") or 4000))
    # Concurrent vision calls. Latency per call is ~40s and irreducible (it is
    # reasoning time, not JSON size — verified by measuring a value-only schema at
    # the same speed), so hitting a 60s/order target means the calls must overlap.
    # Bounded by ONE key's capacity: over-sending buys 429 retry storms, not
    # throughput.
    # Calls IN FLIGHT PER KEY. The total pool is this x the number of keys, so
    # adding a key widens the pool without re-tuning anything.
    #
    # A key serves roughly 101 output tok/s in total, shared across whatever is
    # running on it. Twenty-three calls over four keys is ~5.75 per key, so each
    # call sees ~17-25 tok/s — which is where the "25 tok/s floor" came from. It
    # was never a property of the model; it was self-inflicted, and it then set a
    # 4,500-token effective ceiling against a 180s timeout that killed every
    # section legitimately needing more.
    #
    # An earlier attempt at 8 total looked worse (494s vs 310s), but that test
    # changed the grid ceiling at the same time and had no rate-derived timeout,
    # so it measured two changes at once. With the timeout now sized from the
    # measured rate, fewer in flight means each call runs near 101 tok/s and
    # finishes well inside its budget instead of timing out at the ceiling.
    vision_calls_per_key: int = field(
        default_factory=lambda: int(_env("VISION_CALLS_PER_KEY", "2") or 2))
    # Absolute cap, kept as a safety rail for a large key pool.
    vision_concurrency: int = field(default_factory=lambda: int(_env("VISION_CONCURRENCY", "20") or 20))
    # Triage costs a serial round trip (~25s) before any section can start, which
    # a 60s budget cannot absorb. Off by default: sections are located by their
    # position in the document instead (section ORDER is stable across URAR
    # variants even where page NUMBERS are not). Turn on for unfamiliar layouts.
    vision_use_triage: bool = field(default_factory=lambda: _flag("VISION_USE_TRIAGE", False))
    # output_config.effort. Transcription is not a reasoning task; "low" keeps thinking
    # spend (which shares the max_tokens budget on Sonnet 5) off the section pass.
    vision_effort_section: str = field(default_factory=lambda: _env("VISION_EFFORT_SECTION", "low") or "low")
    vision_effort_grid: str = field(default_factory=lambda: _env("VISION_EFFORT_GRID", "medium") or "medium")

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

    @property
    def vision_configured(self) -> bool:
        """Can the UAD 3.6 vision extractor actually call a model? False makes the
        3.6 path degrade loudly (a documented gap + REVIEW cards) instead of
        emitting an empty field set that looks like a clean extraction."""
        if self.vision_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.vision_provider == "together":
            return bool(self.together_keys)
        return False

    def production_problems(self) -> List[str]:
        """Config that MUST be set for a hardened deployment (empty list = OK). Mirrors
        the Java ProductionReadinessValidator so both services fail-closed the same way."""
        problems: List[str] = []
        if not self.internal_api_key:
            problems.append("INTERNAL_API_KEY unset — API auth would be open (set it, or unset APP_DEPLOY_STRICT for dev).")
        if not self.llm_configured:
            problems.append("No TOGETHER_API_KEY_1..8 — the language judge cannot run.")
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
                "Together AI (TOGETHER_API_KEY_1..8) is the only LLM provider now.")


settings = Settings()
