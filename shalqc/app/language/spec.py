"""
language.spec — the compiled checklist item (§3 output row) shared across modules.

One CompiledItem is the runtime unit: the AMC's own check text plus the labels it
was bound to. Produced by the compiler (offline, cached), consumed by the packet
builder + judge. The runtime never re-binds; it reads these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# scope vocabulary the binder assigns (§3 step 1).
SCOPES = {"subject", "comps", "cross_document", "narrative", "visual", "unbound"}
# judgeable vocabulary (§3 step 1).
JUDGEABLE = {"text", "visual", "needs_engagement"}


@dataclass
class CompiledItem:
    item_id: str
    check_text: str
    reject_text: Optional[str] = None
    section: str = "other"
    bound_labels: List[str] = field(default_factory=list)
    scope: str = "unbound"
    expects: str = ""
    judgeable: str = "text"
    # AnnexB Part 2: cross-section conditional. None for a plain check; else
    # {condition_labels: [...], consequence_labels: [...]}. The judge evaluates
    # the condition first (rule 8): not-met → NOT_APPLICABLE; met → judge the
    # consequence; condition unreadable → REVIEW.
    conditional: Optional[Dict[str, List[str]]] = None
    # how the binding was produced: "llm" | "heuristic" | "constant" — telemetry.
    bound_by: str = "heuristic"
    # AnnexB Part 1 Step 3/4: binder confidence; low/empty → REVIEW_NEEDED.
    binder_confidence: float = 1.0

    @classmethod
    def from_yaml(cls, d: Dict[str, Any]) -> "CompiledItem":
        return cls(
            item_id=str(d.get("item_id") or d.get("id") or "?"),
            check_text=d.get("check_text", "") or "",
            reject_text=d.get("reject_text"),
            section=d.get("section", "other") or "other",
            bound_labels=list(d.get("bound_labels") or []),
            scope=d.get("scope", "unbound") or "unbound",
            expects=d.get("expects", "") or "",
            judgeable=d.get("judgeable", "text") or "text",
            conditional=d.get("conditional"),
            bound_by=d.get("bound_by", "heuristic") or "heuristic",
            binder_confidence=float(d.get("binder_confidence", 1.0) or 1.0),
        )

    def to_yaml(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id, "check_text": self.check_text,
            "reject_text": self.reject_text, "section": self.section,
            "bound_labels": self.bound_labels, "scope": self.scope,
            "expects": self.expects, "judgeable": self.judgeable,
            "conditional": self.conditional,
            "bound_by": self.bound_by, "binder_confidence": self.binder_confidence,
        }

    @property
    def all_labels(self) -> List[str]:
        """Every label the packet should carry — bound + conditional sets."""
        labels = list(self.bound_labels)
        if self.conditional:
            for key in ("condition_labels", "consequence_labels"):
                for l in (self.conditional.get(key) or []):
                    if l not in labels:
                        labels.append(l)
        return labels
