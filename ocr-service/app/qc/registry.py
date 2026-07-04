"""
Rule registry.

Every QC rule is a function registered with @rule(...). Metadata on the
decorator drives the engine: the checklist id/number, section, rollout phase,
and an applicability predicate that gates the rule on loan/transaction/form
type (e.g. FHA rules only fire for FHA loans). Importing app.qc.rules populates
the registry as a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from app.qc.context import QCContext


@dataclass
class RuleSpec:
    rule_id: str
    checklist_num: str
    section: str
    phase: int
    fn: Callable
    applies_when: Optional[Callable[[QCContext], bool]] = None
    name: str = ""
    # Guide-anchored severity of this rule's findings. "standard" = a Fannie hard
    # requirement (missing field/narrative → real defect). "advisory" = a soft /
    # directional check Fannie does NOT mandate (e.g. net-adjustment direction,
    # list-vs-value gap) — the engine tags its findings finding_type="advisory" so
    # the reviewer queue can separate must-fix from FYI. Drives the severity split,
    # never suppresses a finding.
    severity: str = "standard"

    def applicable(self, ctx: QCContext) -> bool:
        if self.applies_when is None:
            return True
        try:
            return bool(self.applies_when(ctx))
        except Exception:
            return True


_REGISTRY: List[RuleSpec] = []


def rule(id: str, num: str, section: str, phase: int,
         applies_when: Optional[Callable[[QCContext], bool]] = None, name: str = "",
         severity: str = "standard"):
    def deco(fn: Callable) -> Callable:
        _REGISTRY.append(RuleSpec(
            rule_id=id, checklist_num=num, section=section, phase=phase,
            fn=fn, applies_when=applies_when, name=name or fn.__name__,
            severity=severity,
        ))
        return fn
    return deco


def all_rules() -> List[RuleSpec]:
    return list(_REGISTRY)


def clear_registry() -> None:
    """Test helper — empty the registry."""
    _REGISTRY.clear()
