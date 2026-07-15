"""
language.spec — the compiled checklist item (§3 output row) shared across modules.

One CompiledItem is the runtime unit: the AMC's own check text plus the labels it
was bound to. Produced by the compiler (offline, cached), consumed by the packet
builder + judge. The runtime never re-binds; it reads these.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# scope vocabulary the binder assigns (§3 step 1).
SCOPES = {"subject", "comps", "cross_document", "narrative", "visual", "unbound"}
# judgeable vocabulary (§3 step 1).
JUDGEABLE = {"text", "visual", "needs_engagement"}

# PART 1.1 (over-checking fix): an item is REJECTABLE only when the AMC gave it
# rejection authority — an authored reject_text, or explicit reject-language in the
# check itself. Every other item is descriptive guidance (informational) that must
# never reach the reviewer VERIFY/reject queue. Derived DYNAMICALLY from the
# checklist text — no per-item, no per-AMC hardcoding.
_REJECT_LANG_RX = re.compile(
    r"\b(reject\s+as|reject\s+for|add\s+(?:a\s+)?rejection|then\s+hold|"
    r"n/?a\s+not\s+allowed|not\s+allowed|place\s+on\s+hold)\b", re.I)


def derive_severity(reject_text: Optional[str], check_text: str) -> str:
    """"rejectable" iff the AMC gave this check reject authority, else "informational"."""
    if (reject_text or "").strip():
        return "rejectable"
    return "rejectable" if _REJECT_LANG_RX.search(check_text or "") else "informational"


@dataclass
class CompiledItem:
    item_id: str
    check_text: str
    reject_text: Optional[str] = None
    section: str = "other"
    # the checklist's short human name for this check (e.g. "Form Type (Product)")
    # — carried to the reviewer card as its title/description.
    item_name: str = ""
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
    # PART 1.1: "rejectable" (AMC gave this check reject authority) | "informational"
    # (descriptive guidance — demoted from the reviewer queue). Left "" it is derived
    # in __post_init__ from reject_text + check_text, so EVERY construction path (the
    # compiler, from_yaml, a direct build in a test) gets the same dynamic answer; an
    # explicit value (an override pin, or a stored bundle) is respected.
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            self.severity = derive_severity(self.reject_text, self.check_text)

    @classmethod
    def from_yaml(cls, d: Dict[str, Any]) -> "CompiledItem":
        return cls(
            item_id=str(d.get("item_id") or d.get("id") or "?"),
            check_text=d.get("check_text", "") or "",
            reject_text=d.get("reject_text"),
            section=d.get("section", "other") or "other",
            item_name=d.get("item_name", "") or "",
            bound_labels=list(d.get("bound_labels") or []),
            scope=d.get("scope", "unbound") or "unbound",
            expects=d.get("expects", "") or "",
            judgeable=d.get("judgeable", "text") or "text",
            conditional=d.get("conditional"),
            bound_by=d.get("bound_by", "heuristic") or "heuristic",
            binder_confidence=float(d.get("binder_confidence", 1.0) or 1.0),
            severity=d.get("severity", "") or "",
        )

    def to_yaml(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id, "check_text": self.check_text,
            "reject_text": self.reject_text, "section": self.section,
            "item_name": self.item_name,
            "bound_labels": self.bound_labels, "scope": self.scope,
            "expects": self.expects, "judgeable": self.judgeable,
            "conditional": self.conditional,
            "bound_by": self.bound_by, "binder_confidence": self.binder_confidence,
            "severity": self.severity,
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
