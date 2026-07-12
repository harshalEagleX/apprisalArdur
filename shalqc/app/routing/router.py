"""
routing.router (crt-1.0.0) — SHALqc.md §7 confidence routing.

The router sits BETWEEN extraction and rules. It loads config/routing.yaml
(hot-reloadable, editable via PUT /routing/config with no deploy) and does two
things:

  1. route(field_name, confidence) -> "auto_accept" | "review" | "reject"
     A labelling decision the reviewer UI can show.

  2. apply(field_set) -> int
     THE P4 enforcement mechanism (SHALqc.md §7 / §12 DoD #4): any field read
     below its `review` threshold is unusable, so its value is SUPPRESSED to
     MISSING (raw value preserved, P2) BEFORE the rule engine runs. A rule can
     therefore never FAIL on a below-threshold field — the field simply isn't
     there to compare, so the needs[] gate degrades the rule to VERIFY.

Per-field thresholds support shell-style wildcards ("comp_*_sale_price"); the
most specific (longest literal prefix) match wins, so "money is stricter"
without listing all nine comps.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.extraction.result import ExtractedField, ExtractedFieldSet

__version__ = "crt-1.0.0"

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "routing.yaml"


@dataclass
class Thresholds:
    auto_accept: float = 0.90
    review: float = 0.70


class Router:
    def __init__(self, path: Path = _CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._raw: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            d = self._raw.get("defaults") or {}
            self._default = Thresholds(
                auto_accept=float(d.get("auto_accept", 0.90)),
                review=float(d.get("review", 0.70)),
            )
            self._fields: Dict[str, Thresholds] = {}
            for pattern, over in (self._raw.get("fields") or {}).items():
                self._fields[pattern] = Thresholds(
                    auto_accept=float(over.get("auto_accept", self._default.auto_accept)),
                    review=float(over.get("review", self._default.review)),
                )
            logger.info("Router loaded (%s): %d field overrides", self.version, len(self._fields))

    @property
    def version(self) -> str:
        return (self._raw.get("meta") or {}).get("version", "unknown")

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """PUT /routing/config — replace config in memory and persist (§9)."""
        with self._lock:
            self._path.write_text(yaml.safe_dump(new_config, sort_keys=False), encoding="utf-8")
            self.reload()

    def thresholds_for(self, field_name: str) -> Thresholds:
        with self._lock:
            best_pattern = None
            for pattern in self._fields:
                if fnmatch.fnmatch(field_name, pattern):
                    # most specific = longest literal (non-wildcard) length
                    literal = len(pattern.replace("*", "").replace("?", ""))
                    if best_pattern is None or literal > best_pattern[1]:
                        best_pattern = (pattern, literal)
            return self._fields[best_pattern[0]] if best_pattern else self._default

    def route(self, field_name: str, confidence: float) -> str:
        t = self.thresholds_for(field_name)
        if confidence >= t.auto_accept:
            return "auto_accept"
        if confidence >= t.review:
            return "review"
        return "reject"

    def apply(self, field_set: ExtractedFieldSet) -> int:
        """Suppress every field read below its `review` threshold → MISSING.
        Returns the number suppressed (for report.degradations / P11)."""
        suppressed = 0
        for _name, ef in field_set:
            if not ef.found:
                continue
            t = self.thresholds_for(ef.canonical_name)
            if ef.confidence < t.review:
                if not ef.raw_value:
                    ef.raw_value = ef.value
                ef.suppressed = True
                ef.suppression_reason = (
                    f"below routing review threshold {t.review} "
                    f"(confidence {ef.confidence}) — unusable, routed to MISSING"
                )
                suppressed += 1
        if suppressed:
            logger.info("router: suppressed %d sub-threshold field(s)", suppressed)
        return suppressed


# Singleton
router = Router()


def route(field_name: str, confidence: float) -> str:
    return router.route(field_name, confidence)
