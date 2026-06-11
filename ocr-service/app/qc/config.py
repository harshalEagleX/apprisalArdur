"""
QC config loader — thresholds and verbatim rejection templates.

Loaded once from config/qc_thresholds.yaml and config/qc_templates.yaml so
business analysts can tune cutoffs and edit client-facing wording without a
code change or deploy (P-4). reload() re-reads both files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class QCConfig:
    def __init__(self) -> None:
        self._thresholds: Dict[str, Any] = {}
        self._templates: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        with open(_CONFIG_DIR / "qc_thresholds.yaml") as f:
            self._thresholds = yaml.safe_load(f) or {}
        with open(_CONFIG_DIR / "qc_templates.yaml") as f:
            self._templates = yaml.safe_load(f) or {}

    # -- thresholds -------------------------------------------------------
    @property
    def structured_conf(self) -> float:
        return self._thresholds.get("confidence", {}).get("structured", 0.75)

    @property
    def checkbox_conf(self) -> float:
        return self._thresholds.get("confidence", {}).get("checkbox", 0.85)

    @property
    def match_threshold(self) -> float:
        return self._thresholds.get("match", {}).get("match_threshold", 0.88)

    @property
    def review_threshold(self) -> float:
        return self._thresholds.get("match", {}).get("review_threshold", 0.75)

    def semantic(self, key: str, default: float = 0.0) -> float:
        return self._thresholds.get("semantic", {}).get(key, default)

    def subject(self, key: str, default=None):
        """Subject-section content config (generic names, APN format map)."""
        return self._thresholds.get("subject", {}).get(key, default)

    # -- templates --------------------------------------------------------
    def template(self, template_id: str, **kwargs) -> str:
        """Return the filled rejection template; falls back to the id if missing."""
        raw = self._templates.get(template_id)
        if raw is None:
            return template_id
        try:
            return raw.format(**kwargs) if kwargs else raw
        except (KeyError, IndexError):
            return raw


# module singleton
qc_config = QCConfig()
