"""registry.loader — the version-namespaced field registry loader (L2).

Keyed by (uad_version, form_type, field_id). Loads config/field_registry/<uad_version>/
so a new UAD version is a new directory, never a rekey. Fail-safe by design: an
unknown version/form/field answers "I don't know" (False), never a guess — the
form-aware N/A gate only acts on a POSITIVE "absent" fact.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, Set

import yaml

logger = logging.getLogger(__name__)

__version__ = "reg-0.1.0"

_ROOT = Path(__file__).parent.parent.parent / "config" / "field_registry"
_DEFAULT_VERSION = "uad26"


class FieldRegistry:
    """Thread-safe, hot-reloadable. `absent_fields[uad_version][form_type]` is the
    set of field_ids that are UNAMBIGUOUSLY not on that form."""

    def __init__(self, root: Path = _ROOT) -> None:
        self._root = root
        self._lock = threading.RLock()
        self._absent: Dict[str, Dict[str, Set[str]]] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            absent: Dict[str, Dict[str, Set[str]]] = {}
            if self._root.is_dir():
                for vdir in self._root.iterdir():
                    if not vdir.is_dir():
                        continue
                    forms_file = vdir / "forms.yaml"
                    if not forms_file.exists():
                        continue
                    try:
                        data = yaml.safe_load(forms_file.read_text(encoding="utf-8")) or {}
                    except yaml.YAMLError as exc:
                        logger.error("field_registry: bad YAML %s: %s", forms_file, exc)
                        continue
                    per_form: Dict[str, Set[str]] = {}
                    for form_type, spec in (data.get("forms") or {}).items():
                        fields = (spec or {}).get("absent_fields") or []
                        per_form[str(form_type)] = {str(f) for f in fields}
                    absent[vdir.name] = per_form
            self._absent = absent
            logger.info("field_registry loaded: versions=%s", list(absent.keys()))

    def known_form(self, form_type: str, uad_version: str = _DEFAULT_VERSION) -> bool:
        """True iff the registry has an entry for this (version, form) — i.e. we can
        reason about applicability for it at all."""
        if not form_type:
            return False
        return form_type in self._absent.get(uad_version, {})

    def is_absent_on_form(self, field_id: str, form_type: str,
                          uad_version: str = _DEFAULT_VERSION) -> bool:
        """True ONLY when the registry POSITIVELY records that `field_id` does not
        exist on `form_type`. Unknown version/form/field → False (fail-safe)."""
        if not form_type or not field_id:
            return False
        return field_id in self._absent.get(uad_version, {}).get(form_type, set())


# Singleton — import this everywhere (mirrors normalize.normalizer).
registry = FieldRegistry()
