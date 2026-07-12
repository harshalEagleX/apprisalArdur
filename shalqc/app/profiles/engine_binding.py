"""
profiles.engine_binding (prof-binding-1.0.0) — SHALqc.md §6.

Applies an AmcProfile to a run. Two responsibilities:

  1. `active_rules(profile)` — filter the registry to the rules this AMC runs
     (rules.default on/off + explicit on/off list). Custom-rule discovery under
     rules/custom/<amc_code>/ is imported here so those @rule decorators
     register (§6.4) — additions for AMC #2 are a new module, zero engine edits.

  2. `apply_severity(profile, verdicts)` — remap each verdict's status per the
     AMC's severity_overrides (e.g. S-5 FAIL→VERIFY for an AMC that treats the
     neighborhood-name check as soft). This is also the ONLY sanctioned way a
     verdict becomes HOLD (SHALqc.md §13: HOLD is intake- or profile-sourced,
     never a rule body).

The engine reads profile.rules_on directly for the on/off gate
(rules/engine.py `_profile_allows`), so binding stays a thin, testable layer.
"""

from __future__ import annotations

import importlib
import logging
from typing import List

from app.profiles.model import AmcProfile
from app.rules.registry import RuleSpec, all_rules
from app.rules.verdict import Status, Verdict

__version__ = "prof-binding-1.0.0"

logger = logging.getLogger(__name__)


def discover_custom_rules(profile: AmcProfile) -> None:
    """Import this AMC's custom rule modules so their @rule decorators register.
    Modules live at app.rules.custom.<amc_code>.* and are named in the profile's
    custom_rules list. Missing modules are logged, never fatal (P6)."""
    for module_name in profile.custom_rules:
        dotted = f"app.rules.custom.{profile.amc_code}.{module_name}"
        try:
            importlib.import_module(dotted)
            logger.info("profiles: loaded custom rule module %s", dotted)
        except Exception as exc:
            logger.warning("profiles: custom rule module %s not loaded: %s", dotted, exc)


def active_rules(profile: AmcProfile) -> List[RuleSpec]:
    """The subset of the registry this AMC runs, honoring rules.default and the
    explicit on/off list."""
    discover_custom_rules(profile)
    result: List[RuleSpec] = []
    for spec in all_rules():
        enabled = profile.rules_on.get(spec.rule_id, profile.rules_default_on)
        if enabled:
            result.append(spec)
    return result


def apply_severity(profile: AmcProfile, verdicts: List[Verdict]) -> List[Verdict]:
    """Remap verdict statuses per the AMC severity_overrides. Returns the same
    list (mutated in place) for convenience."""
    for v in verdicts:
        remapped = profile.remap_status(v.rule_id, v.status.value)
        if remapped != v.status.value:
            try:
                v.status = Status(remapped)
                v.degraded_reason = (v.degraded_reason or "") + f"|profile_remap:{remapped}"
            except ValueError:
                logger.warning("profiles: %s has invalid severity remap %r", v.rule_id, remapped)
    return verdicts
