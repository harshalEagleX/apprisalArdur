"""
report.wording (rpt-1.0.0) — SHALqc.md §6.3 / §8.

Renders an AMC's verbatim "Reject as:" text. The engine produces a
`message_key` + values; this looks the key up in the AMC's wording file
(config/amc_profiles/<code>.wording.yaml: message_key -> template with {value}
placeholders) and fills it. A different AMC's phrasing is a different wording
file — zero engine code (§6.3).

Fallback chain (SHALqc-CORE §4.5 last validator row): missing key ⇒ use the
verdict's own plain `message` as the wording, so a card is never blank.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

__version__ = "rpt-1.0.0"

logger = logging.getLogger(__name__)

_PROFILE_DIR = Path(__file__).parent.parent.parent / "config" / "amc_profiles"


class WordingBook:
    """Loads and caches one AMC wording file's templates."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, str]] = {}

    def _load(self, wording_file: str) -> Dict[str, str]:
        with self._lock:
            if wording_file in self._cache:
                return self._cache[wording_file]
            path = _PROFILE_DIR / wording_file
            templates: Dict[str, str] = {}
            if path.exists():
                try:
                    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    templates = raw.get("templates") or {}
                except Exception as exc:
                    logger.error("wording: could not read %s: %s", path, exc)
            self._cache[wording_file] = templates
            return templates

    def reload(self) -> None:
        with self._lock:
            self._cache.clear()

    def render(self, wording_file: Optional[str], message_key: Optional[str],
               values: Optional[Dict[str, Any]] = None, fallback: str = "") -> str:
        """Render `message_key` from `wording_file` with `values`. Falls back to
        `fallback` (the verdict's plain message) when the key/file is absent."""
        if not message_key or not wording_file:
            return fallback
        template = self._load(wording_file).get(message_key)
        if not template:
            return fallback
        try:
            return template.format(**(values or {}))
        except (KeyError, IndexError, ValueError):
            # a placeholder without a matching value → return the raw template
            # rather than crash the report (P6).
            return template


# Singleton
wording_book = WordingBook()
