"""
rules.verdict (rul-1.0.0) — SHALqc.md §5 rule contract / §13 status model.

Verdict{status, evidence[], message_key, confidence} is what every rule returns.
Status vocabulary is PASS | FAIL | VERIFY | NOT_APPLICABLE (SHALqc-CORE §4.2).
HOLD is NOT in the judge/rule vocabulary — it is emitted only by intake gates
(pipeline/intake.py G-0..G-3) and AMC profile severity remaps (SHALqc.md §13);
a rule that needs to escalate returns FAIL and the profile may remap it to HOLD.

Guardrail (SHALqc.md P4 / SHALqc-CORE §0): a FAIL requires high-confidence
evidence. Doubt degrades to VERIFY. Low confidence can NEVER auto-FAIL — this is
enforced structurally by the engine's needs[] gate and by `degrade_if_low`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    VERIFY = "VERIFY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    # HOLD is intake/profile-only — never returned by a rule body. Present here
    # so the report builder and profile remaps share one vocabulary.
    HOLD = "HOLD"


@dataclass
class Evidence:
    """One value a verdict rests on — powers the reviewer's click-to-scroll."""

    field: str
    value: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0
    page: int = 0
    bbox: Optional[Dict[str, float]] = None
    location_quality: Optional[str] = None   # SHALqc-CORE §3: exact|region|page|none
    document: str = "appraisal"   # appraisal | engagement | contract


@dataclass
class Verdict:
    """A single rule outcome. A rule may return one Verdict or a list of them
    (e.g. S-1 checks address+city+state+zip separately)."""

    rule_id: str
    status: Status
    section: str = ""
    checklist_num: str = ""
    message_key: Optional[str] = None       # → AMC wording template (report/wording.py)
    message: str = ""                        # fallback plain text when no wording template
    evidence: List[Evidence] = field(default_factory=list)
    fields_involved: List[str] = field(default_factory=list)
    confidence: float = 1.0
    tier: int = 1                            # 1 deterministic | 2 llm-judged | 3 verify-pass
    # Provenance of a degradation (SHALqc-CORE §4.5): ungrounded | math_mismatch |
    # low_confidence_input | llm_unavailable | mo_conflict | na_disputed. None
    # when the verdict was rendered cleanly.
    degraded_reason: Optional[str] = None
    # SHALqc-CORE §0/DoD#6: who rendered this status. "" = deterministic pass;
    # "C2:judge_v1" = the LLM judge (traceable to a C2 reply + prompt version).
    judged_by: str = ""
    # CORE §4.2: the LLM's reviewer-facing plain sentence (what the reviewer reads).
    reason_plain: str = ""
    # Who must act on this finding (significance layer): "appraiser" → real
    # reviewer/AMC finding; "engine" → an engine-health item (unmapped field,
    # unimplemented check, extraction gap) that must NEVER reach the reviewer or
    # produce AMC wording. Default appraiser.
    actionable_by: str = "appraiser"

    @property
    def is_exception(self) -> bool:
        return self.status in (Status.FAIL, Status.VERIFY, Status.HOLD)


def degrade_to_verify(verdict: Verdict, reason: str) -> Verdict:
    """Downgrade a FAIL to VERIFY (P4). PASS/VERIFY/NA pass through unchanged —
    only a FAIL can be blocked. Stamps the reason for the audit dump."""
    if verdict.status == Status.FAIL:
        verdict.status = Status.VERIFY
        verdict.degraded_reason = reason
        verdict.confidence = min(verdict.confidence, 0.6)
    return verdict


def contract_cap(verdicts):
    """SHALqc-CORE §11: contract reads are the least trustworthy input, so a FAIL
    that RESTS on a contract-sourced value (source 'contract', conf 0.75) is
    capped at VERIFY unless an appraisal-sourced value in the same finding
    corroborates it. Proves 'a contract-backed rule is incapable of FAIL'
    structurally (DoD #12). Mutates + returns the list."""
    for v in verdicts:
        if v.status != Status.FAIL:
            continue
        uses_contract = any((e.source or "").endswith("contract") for e in v.evidence)
        corroborated = any((e.source or "").endswith(("xml", "pdf_digital", "grid"))
                           for e in v.evidence)
        if uses_contract and not corroborated:
            v.status = Status.VERIFY
            v.degraded_reason = (v.degraded_reason or "") + "|contract_uncorroborated"
            v.confidence = min(v.confidence, 0.6)
    return verdicts
