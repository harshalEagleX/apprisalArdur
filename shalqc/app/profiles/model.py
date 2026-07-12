"""
profiles.model (prof-*) — SHALqc.md §6.2 AmcProfile.

The parsed, merged form of `<code>.yaml` deep-merged over `_base.yaml`. Carries
everything the engine and report builder need to specialize a run for one AMC:
which rules run, how their severities remap, per-rule thresholds, the wording
file, custom-rule module names, and routing overrides. Zero engine code changes
per AMC — a new AMC is a new profile (P7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AmcProfile:
    amc_code: str
    name: str = ""
    version: str = ""
    # rule_id -> bool (on/off). Absent rule ⇒ default (rules.default, usually on).
    rules_on: Dict[str, bool] = field(default_factory=dict)
    rules_default_on: bool = True
    # rule_id -> {canonical_status: remapped_status} e.g. {"S-5": {"FAIL": "VERIFY"}}
    severity_overrides: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # dotted threshold keys, e.g. {"SCA-NET.net_adjustment_pct": 15}
    thresholds: Dict[str, Any] = field(default_factory=dict)
    custom_rules: List[str] = field(default_factory=list)
    wording_file: str = ""
    routing_overrides: Dict[str, dict] = field(default_factory=dict)
    engagement_hints: Dict[str, List[str]] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    # True when resolution fell back to _base because the requested amc_code had
    # no profile file — the loader pairs this with a HOLD finding (§6.1).
    is_fallback: bool = False

    def remap_status(self, rule_id: str, status: str) -> str:
        """Apply this AMC's severity override for a rule's canonical status."""
        return self.severity_overrides.get(rule_id, {}).get(status, status)

    def threshold(self, key: str, default=None):
        return self.thresholds.get(key, default)
