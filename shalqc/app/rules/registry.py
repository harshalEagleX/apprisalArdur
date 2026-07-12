"""
rules.registry (rul-1.0.0) — SHALqc.md §5 rule contract.

    @rule(id="S-1", checklist="C", section="subject", version=1,
          needs=["property_address", "engagement.property_address"], tier=1)
    def s1(ctx) -> Verdict | list[Verdict]

`needs[]` drives the pre-body gate (SHALqc.md §5, applied by the engine):
  * a needed doc is absent            → auto NOT_APPLICABLE (rule never runs)
  * a needed field is missing/blank   → auto VERIFY  ("please confirm X")
  * a needed field is below review conf→ auto VERIFY  (P4: low conf can't FAIL)
So a rule body only ever runs against present, above-threshold data — "rules
never see garbage."

`applies_when(ctx)` gates a rule on transaction/loan/form type (e.g. contract
rules only on purchases). `tier` is 1 deterministic / 2 llm-judged / 3 verify-
pass. Importing app.rules populates the registry as an import side effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from app.rules.context import QCContext


@dataclass
class RuleSpec:
    rule_id: str
    checklist_num: str
    section: str
    version: int
    fn: Callable
    needs: List[str] = field(default_factory=list)
    tier: int = 1
    applies_when: Optional[Callable[[QCContext], bool]] = None
    name: str = ""
    severity: str = "standard"     # standard (hard requirement) | advisory (FYI)

    def applicable(self, ctx: QCContext) -> bool:
        if self.applies_when is None:
            return True
        try:
            return bool(self.applies_when(ctx))
        except Exception:
            return True


_REGISTRY: List[RuleSpec] = []


def rule(id: str, checklist: str, section: str, version: int = 1,
         needs: Optional[List[str]] = None, tier: int = 1,
         applies_when: Optional[Callable[[QCContext], bool]] = None,
         name: str = "", severity: str = "standard"):
    def deco(fn: Callable) -> Callable:
        _REGISTRY.append(RuleSpec(
            rule_id=id, checklist_num=checklist, section=section, version=version,
            fn=fn, needs=needs or [], tier=tier, applies_when=applies_when,
            name=name or fn.__name__, severity=severity,
        ))
        return fn
    return deco


def all_rules() -> List[RuleSpec]:
    return list(_REGISTRY)


def rules_for_section(section: str) -> List[RuleSpec]:
    return [r for r in _REGISTRY if r.section == section]


def clear_registry() -> None:
    """Test helper — empty the registry."""
    _REGISTRY.clear()
