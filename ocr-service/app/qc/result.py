"""
QC rule outcome model.

Five-state outcome (maps to MIRA Auto-Clear / Exception / Escalation / N-A):
  PASS            — rule satisfied.
  FAIL            — deterministic violation; a rejection message is emitted.
  VERIFY          — needs human confirmation (judgment rule, or low extraction
                    confidence on an otherwise-FAIL/PASS rule).
  HOLD            — escalate to senior/compliance (illegal zoning, H&BU not Yes,
                    loan-type discrepancy). Short-circuits dependent rules.
  NOT_APPLICABLE  — rule does not apply to this loan/transaction/form type.
  SKIPPED         — could not evaluate (prerequisite data missing / rule error).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    VERIFY = "VERIFY"
    HOLD = "HOLD"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SKIPPED = "SKIPPED"


# Map our 5-state model onto the existing adaptive_validation_results.result
# column (pass|fail|warning|info|skipped) so we can persist without a migration.
_DB_RESULT = {
    RuleStatus.PASS: "pass",
    RuleStatus.FAIL: "fail",
    RuleStatus.VERIFY: "warning",
    RuleStatus.HOLD: "fail",
    RuleStatus.NOT_APPLICABLE: "info",
    RuleStatus.SKIPPED: "skipped",
}


@dataclass
class Evidence:
    """Where a value came from — powers the side-by-side reviewer view."""
    document: str                       # appraisal | engagement | contract
    value: Optional[str] = None
    confidence: float = 0.0
    page: Optional[int] = None
    bbox: Optional[Dict[str, float]] = None   # {x,y,w,h} when available
    method: Optional[str] = None
    field: Optional[str] = None         # canonical field name (e.g. comp_1_sale_price)
                                        # — lets the UI label which comparable / the subject


@dataclass
class RuleResult:
    rule_id: str                        # e.g. "S-1"
    checklist_num: str                  # e.g. "C" or "15" (master index)
    section: str                        # subject | contract | signature | ...
    status: RuleStatus
    message: str = ""                   # filled rejection template (FAIL/VERIFY)
    fields_involved: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 1.0             # engine's confidence in THIS finding
    template_id: Optional[str] = None

    @property
    def is_exception(self) -> bool:
        return self.status in (RuleStatus.FAIL, RuleStatus.VERIFY, RuleStatus.HOLD)

    def to_db_dict(self, document_id: str, transaction_id: Optional[str] = None) -> dict:
        snapshot = {
            "status": self.status.value,
            "checklist_num": self.checklist_num,
            "template_id": self.template_id,
            "evidence": [
                {
                    "document": e.document, "value": e.value,
                    "confidence": e.confidence, "page": e.page,
                    "bbox": e.bbox, "method": e.method,
                }
                for e in self.evidence
            ],
        }
        return {
            "document_id": document_id,
            "transaction_id": transaction_id,
            "rule_id": self.rule_id,
            "rule_category": self.section,
            "fields_involved": json.dumps(self.fields_involved),
            "result": _DB_RESULT[self.status],
            "confidence": self.confidence,
            "explanation": self.message or self.status.value,
            "field_values_snapshot": json.dumps(snapshot),
        }


@dataclass
class RuleTiming:
    """Wall-clock time one rule's evaluation actually took (perf_counter delta).
    Measured around spec.fn(ctx) in the engine — never estimated."""
    rule_id: str
    section: str
    status: str
    ms: float


@dataclass
class QCReport:
    """All rule results for one transaction, plus a roll-up."""
    transaction_id: str
    results: List[RuleResult] = field(default_factory=list)
    # Real measured timings. rule_timings is filled by the engine (one entry per
    # rule it executed); stage_ms is filled by the transaction orchestrator (the
    # extraction/QC pipeline stages). Both are wall-clock perf_counter deltas.
    rule_timings: List[RuleTiming] = field(default_factory=list)
    stage_ms: Dict[str, float] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        c = {s.value: 0 for s in RuleStatus}
        for r in self.results:
            c[r.status.value] += 1
        return c

    @property
    def overall(self) -> RuleStatus:
        """A transaction auto-clears only when no FAIL/HOLD/VERIFY remain."""
        statuses = {r.status for r in self.results}
        if RuleStatus.HOLD in statuses:
            return RuleStatus.HOLD
        if RuleStatus.FAIL in statuses:
            return RuleStatus.FAIL
        if RuleStatus.VERIFY in statuses:
            return RuleStatus.VERIFY
        return RuleStatus.PASS
