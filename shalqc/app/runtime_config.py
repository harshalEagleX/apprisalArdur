"""
app.runtime_config (rtc-1.0.0) — settings the FRONTEND owns.

`app/config.py` reads the environment once at import. That is right for secrets
and deploy posture, and wrong for anything an operator should be able to change
without a redeploy — which is the standing requirement here: configuration is
changed in the UI, not by editing Python and not by shelling into a box to set
an env var.

So tunables resolve in three layers, most specific first:

    runtime_config table (frontend writes)  ->  .env  ->  code default

A row's ABSENCE is meaningful: it means "fall through to the environment". That
is why clearing a setting deletes the row rather than storing an empty string —
storing "" would pin the setting to empty forever and look identical to unset.

Reads are cached in-process with a short TTL. Extraction reads these on every
call, and going to Postgres each time would put a database round trip inside a
per-page loop for values that change a few times a month. The TTL bounds how
stale a running worker can be after an operator saves; `invalidate()` makes the
writing process immediate.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

__version__ = "rtc-1.0.0"

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 30.0
_lock = threading.Lock()
_cache: Dict[str, Any] = {}
_cache_at: float = 0.0


# ── the editable surface ──────────────────────────────────────────────────────
#
# An allow-list, deliberately. Without it, a PUT could set `database_url` or
# `internal_api_key` from the browser — the UI would become a remote-code-and-
# credentials console. Anything not listed here is NOT settable at runtime and
# stays where it belongs, in the environment.
#
# `type` drives both validation and the control the frontend renders.
EDITABLE: Dict[str, Dict[str, Any]] = {
    "vision_provider": {
        "type": "enum", "choices": ["together", "anthropic"], "group": "vision",
        "label": "Vision provider",
        "help": "Which service transcribes UAD 3.6 pages. The judge is unaffected.",
    },
    "vision_model": {
        "type": "string", "group": "vision", "label": "Vision model",
        "help": "Must be SERVERLESS and accept image input. Dedicated-only models "
                "(e.g. the Qwen3-VL line on Together) require a provisioned GPU "
                "endpoint billed per hour and will not work here.",
    },
    "vision_model_section": {"type": "string", "group": "vision", "label": "Model — sections"},
    "vision_model_grid": {"type": "string", "group": "vision", "label": "Model — sales grid"},
    "vision_model_escalate": {
        "type": "string", "group": "vision", "label": "Model — retry escalation",
        "help": "Used when a checksum fails. A different model family gives an "
                "uncorrelated second opinion rather than the same misread twice.",
    },
    "vision_dpi_section": {"type": "int", "min": 72, "max": 400, "group": "vision",
                           "label": "Render DPI — sections"},
    "vision_dpi_grid": {"type": "int", "min": 72, "max": 400, "group": "vision",
                        "label": "Render DPI — sales grid"},
    "vision_dpi_retry": {"type": "int", "min": 72, "max": 400, "group": "vision",
                         "label": "Render DPI — retry"},
    "vision_budget_usd_per_order": {
        "type": "float", "min": 0.0, "max": 25.0, "group": "vision",
        "label": "Budget per order (USD)",
        "help": "Hard ceiling. Extraction stops and unread regions become REVIEW "
                "cards rather than silently overrunning.",
    },
    "vision_max_retries": {"type": "int", "min": 0, "max": 5, "group": "vision",
                           "label": "Checksum retries per region"},
    "vision_effort_section": {"type": "enum", "choices": ["low", "medium", "high"],
                              "group": "vision", "label": "Effort — sections"},
    "vision_effort_grid": {"type": "enum", "choices": ["low", "medium", "high"],
                           "group": "vision", "label": "Effort — sales grid"},
    "extract_max_pages": {"type": "int", "min": 1, "max": 500, "group": "extraction",
                          "label": "Max pages scanned",
                          "help": "A UAD 3.6 report runs 25-45 pages and its entire "
                                  "valuation sits past page 8."},
    "judge_self_consistency_n": {"type": "int", "min": 1, "max": 5, "group": "judge",
                                 "label": "Judge self-consistency (N)",
                                 "help": "N>1 re-judges decisive verdicts and downgrades "
                                         "any non-unanimous item to REVIEW."},
    "llm_max_calls_per_order": {"type": "int", "min": 1, "max": 200, "group": "judge",
                                "label": "Max LLM calls per order"},
}


class ConfigError(ValueError):
    """A rejected write. Carries a message meant to be shown in the UI."""


def _coerce(key: str, value: Any) -> Any:
    """Validate and coerce one setting. Raises ConfigError with a message the
    frontend can render verbatim."""
    spec = EDITABLE.get(key)
    if spec is None:
        raise ConfigError(
            f"'{key}' is not runtime-configurable. Settable keys: "
            f"{', '.join(sorted(EDITABLE))}")
    kind = spec["type"]

    if kind == "enum":
        if value not in spec["choices"]:
            raise ConfigError(
                f"{key} must be one of {spec['choices']}, got {value!r}")
        return value
    if kind == "string":
        text = str(value).strip()
        if not text:
            raise ConfigError(f"{key} cannot be empty — delete it to fall back to the environment")
        return text
    if kind in ("int", "float"):
        try:
            n = int(value) if kind == "int" else float(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{key} must be a number, got {value!r}") from None
        lo, hi = spec.get("min"), spec.get("max")
        if lo is not None and n < lo:
            raise ConfigError(f"{key} must be >= {lo}, got {n}")
        if hi is not None and n > hi:
            raise ConfigError(f"{key} must be <= {hi}, got {n}")
        return n
    if kind == "bool":
        return bool(value)
    raise ConfigError(f"unsupported setting type '{kind}' for {key}")


# ── read ──────────────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    """All overrides, cached. Persistence being unavailable is NOT an error —
    it means every setting falls through to the environment, which is exactly
    the behaviour before this layer existed."""
    global _cache, _cache_at
    now = time.monotonic()
    with _lock:
        if _cache_at and (now - _cache_at) < _CACHE_TTL_S:
            return _cache
    loaded: Dict[str, Any] = {}
    try:
        from app.persistence import repo
        from app.persistence.models import RuntimeConfig
        with repo._session() as s:  # noqa: SLF001 — repo exposes no generic reader
            if s is not None:
                for row in s.query(RuntimeConfig).all():
                    loaded[row.key] = row.value.get("v") if isinstance(row.value, dict) else row.value
    except Exception as exc:
        logger.debug("runtime_config: no overrides available (%s)", exc)
    with _lock:
        _cache, _cache_at = loaded, now
    return loaded


def invalidate() -> None:
    """Drop the read cache — called after a write so the writing process sees
    its own change immediately instead of up to the TTL later."""
    global _cache_at
    with _lock:
        _cache_at = 0.0


def get(key: str, default: Any = None) -> Any:
    """Resolve one setting: runtime override -> app.config -> supplied default."""
    overrides = _load()
    if key in overrides:
        return overrides[key]
    from app.config import settings
    return getattr(settings, key, default)


def effective() -> Dict[str, Any]:
    """Every editable setting with its value AND where that value came from.

    The provenance is the point: an operator looking at a misbehaving run needs
    to know whether a value was set in the UI or is falling through to a deploy
    env var, because those are fixed in different places.
    """
    from app.config import settings
    overrides = _load()
    out: Dict[str, Any] = {}
    for key, spec in EDITABLE.items():
        out[key] = {
            "value": overrides.get(key, getattr(settings, key, None)),
            "source": "runtime" if key in overrides else "environment",
            "env_value": getattr(settings, key, None),
            **{k: v for k, v in spec.items() if k != "type"},
            "type": spec["type"],
        }
    return out


# ── write ─────────────────────────────────────────────────────────────────────

def set_many(updates: Dict[str, Any], who: str = "frontend") -> Dict[str, Any]:
    """Validate and persist a batch of settings. All-or-nothing: if any value is
    invalid, nothing is written — a half-applied config change is worse than a
    rejected one because it leaves the system in a state nobody chose."""
    coerced = {k: _coerce(k, v) for k, v in updates.items()}

    from app.persistence import repo
    from app.persistence.models import RuntimeConfig
    before = json.dumps(_load(), sort_keys=True, default=str)

    with repo._session() as s:  # noqa: SLF001
        if s is None:
            raise ConfigError(
                "no database configured — runtime settings cannot be saved "
                "(set DATABASE_URL, or configure via .env)")
        for key, value in coerced.items():
            row = s.get(RuntimeConfig, key)
            if row is None:
                s.add(RuntimeConfig(key=key, value={"v": value}, updated_by=who))
            else:
                row.value = {"v": value}
                row.updated_by = who
                row.updated_at = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc)
    invalidate()
    _audit(before, json.dumps(_load(), sort_keys=True, default=str), who,
           ",".join(sorted(coerced)))
    return coerced


def unset(keys: List[str], who: str = "frontend") -> List[str]:
    """Delete overrides so they fall back to the environment."""
    from app.persistence import repo
    from app.persistence.models import RuntimeConfig
    before = json.dumps(_load(), sort_keys=True, default=str)
    removed: List[str] = []
    with repo._session() as s:  # noqa: SLF001
        if s is None:
            raise ConfigError("no database configured — nothing to unset")
        for key in keys:
            row = s.get(RuntimeConfig, key)
            if row is not None:
                s.delete(row)
                removed.append(key)
    invalidate()
    _audit(before, json.dumps(_load(), sort_keys=True, default=str), who,
           "unset:" + ",".join(sorted(removed)))
    return removed


def _audit(before: str, after: str, who: str, what: str) -> None:
    """§17 config audit. Best-effort — a missing audit row must never fail the
    config change the operator actually asked for."""
    try:
        import hashlib
        from app.persistence import repo
        from app.persistence.models import ConfigAudit
        with repo._session() as s:  # noqa: SLF001
            if s is not None:
                s.add(ConfigAudit(
                    who=who, what=f"runtime_config:{what}"[:64],
                    before_hash=hashlib.sha256(before.encode()).hexdigest()[:16],
                    after_hash=hashlib.sha256(after.encode()).hexdigest()[:16]))
    except Exception as exc:
        logger.debug("runtime_config: audit write skipped (%s)", exc)
