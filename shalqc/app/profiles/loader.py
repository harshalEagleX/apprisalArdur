"""
profiles.loader (prof-loader-1.0.0) — SHALqc.md §6.1 resolution.

manifest.amc_code → config/amc_profiles/<code>.yaml → deep-merge over
`_base.yaml` → AmcProfile. An unknown code resolves to `_base` with
`is_fallback=True`, which the caller pairs with a HOLD finding "AMC profile not
found" (§6.1). Loaded at intake, cacheable; hot-reloadable.

"Hardcoded now, dynamic forever" (§6): the loading mechanism is fully dynamic
from day one — there simply happens to be one real profile file today (AMC001).
Onboarding AMC #2 is a new YAML + wording file, zero engine code (§6.4).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.profiles.model import AmcProfile

__version__ = "prof-loader-1.0.0"

logger = logging.getLogger(__name__)

_PROFILE_DIR = Path(__file__).parent.parent.parent / "config" / "amc_profiles"
_BASE_NAME = "_base"


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge `over` onto `base` (over wins). Dicts merge key-wise;
    every other type (including lists) is replaced wholesale — an AMC that lists
    `rules.off: [X]` replaces, it does not append to, the base list."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("profiles: could not read %s: %s", path, exc)
        return {}


def _to_profile(amc_code: str, merged: Dict[str, Any], is_fallback: bool) -> AmcProfile:
    rules = merged.get("rules") or {}
    default_on = str(rules.get("default", "on")).lower() in ("on", "true", "1", "yes")
    rules_on: Dict[str, bool] = {}
    for rid in (rules.get("off") or []):
        rules_on[rid] = False
    for rid in (rules.get("on") or []):
        rules_on[rid] = True
    meta = merged.get("meta") or {}
    return AmcProfile(
        amc_code=amc_code,
        name=meta.get("name", ""),
        version=meta.get("version", ""),
        rules_on=rules_on,
        rules_default_on=default_on,
        severity_overrides=rules.get("severity_overrides") or {},
        thresholds=rules.get("thresholds") or {},
        custom_rules=rules.get("custom_rules") or [],
        wording_file=merged.get("wording_file") or "",
        routing_overrides=merged.get("routing_overrides") or {},
        engagement_hints=merged.get("engagement_hints") or {},
        output=merged.get("output") or {},
        is_fallback=is_fallback,
    )


class ProfileLoader:
    def __init__(self, profile_dir: Path = _PROFILE_DIR) -> None:
        self._dir = profile_dir
        self._lock = threading.RLock()
        self._cache: Dict[str, AmcProfile] = {}

    def load(self, amc_code: Optional[str]) -> AmcProfile:
        """Resolve an AmcProfile for `amc_code` (deep-merged over _base).
        Unknown/absent code ⇒ _base profile with is_fallback=True."""
        key = (amc_code or "").strip() or _BASE_NAME
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            base = _read_yaml(self._dir / f"{_BASE_NAME}.yaml")
            profile_path = self._dir / f"{key}.yaml"
            is_fallback = key != _BASE_NAME and not profile_path.exists()
            over = {} if is_fallback else _read_yaml(profile_path)
            merged = _deep_merge(base, over)
            profile = _to_profile(key if not is_fallback else _BASE_NAME, merged, is_fallback)
            if is_fallback:
                logger.warning("profiles: no profile for amc_code=%s — using _base (HOLD)", amc_code)
            self._cache[key] = profile
            return profile

    def reload(self) -> None:
        """Drop the cache so the next load re-reads from disk
        (POST /amc/profiles/reload, §9)."""
        with self._lock:
            self._cache.clear()

    def resolve_amc(self, engagement_text: str = "", order_id: str = "") -> Optional[str]:
        """Dynamic AMC selection (no engine hardcoding): scan every profile's
        own `resolve` block and return the amc_code whose declared alias appears
        in the engagement text OR whose order_id_prefix starts the order_id.

        Any AMC self-registers by adding a `resolve:` block to its YAML — the
        loader has no per-AMC knowledge. First match wins (profiles are scanned
        in filename order; `_base` carries no resolve block so it never matches).
        """
        text = (engagement_text or "").lower()
        oid = (order_id or "").upper()
        for path in sorted(self._dir.glob("*.yaml")):
            if path.name.endswith(".wording.yaml") or path.stem == _BASE_NAME:
                continue
            raw = _read_yaml(path)
            resolve = raw.get("resolve") or {}
            code = (raw.get("meta") or {}).get("amc_code") or path.stem
            for alias in (resolve.get("aliases") or []):
                if alias and alias.lower() in text:
                    return code
            for prefix in (resolve.get("order_id_prefixes") or []):
                if prefix and oid.startswith(prefix.upper()):
                    return code
        return None


# Singleton
profile_loader = ProfileLoader()


def load_profile(amc_code: Optional[str]) -> AmcProfile:
    return profile_loader.load(amc_code)
