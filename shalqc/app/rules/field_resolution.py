"""
rules.field_resolution (frl-1.0.0) — close rule-vs-extraction name drift.

DocView.field(name) consults resolve_field() when a direct lookup misses, BEFORE
declaring the field missing. Resolution order (first hit wins):

  1. explicit alias      config/field_resolution.yaml `aliases:` (string or list)
  2. comp suffix alias   comp_<N>_<suffix> -> comp_<N>_<mapped suffix>
  3. schema synonym      schema_loader.get_field(name).canonical_name
  4. derive              a computed value from app/rules/derivations.py

Returns an ExtractedField (a real one for 1-3; a synthesized source="derived"
one for 4) or None. None => the field is genuinely absent (a real VERIFY), so
this layer only ever *finds* values that already exist — it never fabricates.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Dict, Optional

import yaml

from app.extraction.result import ExtractedField
from app.rules.derivations import DERIVERS

__version__ = "frl-1.0.0"

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "field_resolution.yaml"
_COMP_RE = re.compile(r"^(comp_\d+)_(.+)$")


class _Resolution:
    def __init__(self, path: Path = _CONFIG_PATH):
        self._path = path
        self._lock = threading.RLock()
        self.aliases: Dict[str, list] = {}
        self.comp_suffix: Dict[str, str] = {}
        self.derive: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            aliases = {}
            for k, v in (raw.get("aliases") or {}).items():
                aliases[k] = v if isinstance(v, list) else [v]
            self.aliases = aliases
            self.comp_suffix = dict(raw.get("comp_suffix_aliases") or {})
            self.derive = dict(raw.get("derive") or {})
            logger.info("field_resolution loaded: %d aliases, %d comp-suffix, %d derive",
                        len(self.aliases), len(self.comp_suffix), len(self.derive))

    # -- candidate names (aliases + comp suffix + schema synonym) --------
    def _alias_targets(self, name: str) -> list:
        targets = list(self.aliases.get(name, []))
        m = _COMP_RE.match(name)
        if m and m.group(2) in self.comp_suffix:
            targets.append(f"{m.group(1)}_{self.comp_suffix[m.group(2)]}")
        return targets


_R = _Resolution()


def reload() -> None:
    _R.reload()


def _found(by_name: Dict[str, ExtractedField], key: str) -> Optional[ExtractedField]:
    ef = by_name.get(key)
    return ef if (ef is not None and ef.found) else None


def resolve_field(name: str, by_name: Dict[str, ExtractedField]) -> Optional[ExtractedField]:
    """Return an ExtractedField for `name` via alias/synonym/derive, or None."""
    # 1 + 2: explicit + comp-suffix aliases
    for target in _R._alias_targets(name):
        ef = _found(by_name, target)
        if ef is not None:
            return ef

    # 3: schema synonym -> canonical name that may be what extraction stored
    try:
        from app.extraction.schema import schema_loader
        fd = schema_loader.get_field(name)
        if fd is not None and fd.canonical_name != name:
            ef = _found(by_name, fd.canonical_name)
            if ef is not None:
                return ef
    except Exception:
        pass

    # 4: derive a computed value
    fn_name = _R.derive.get(name)
    if fn_name and fn_name in DERIVERS:
        def _get(n: str) -> Optional[str]:
            ef = _found(by_name, n)
            return ef.value if ef is not None else None
        value = DERIVERS[fn_name](_get)
        if value is not None:
            return ExtractedField(
                canonical_name=name, value=str(value),
                source="derived", confidence=0.9, page=0,
            )
    return None
