"""
Deterministic contract-section rules (T1) — SHALqc.md §5.

Applicability is transaction-type gated (applies_when), not needs[] gated,
because the *presence* of contract fields is exactly what these rules judge:
on a purchase the contract must be analyzed; on a refinance the contract
section must be blank. So needs[] is intentionally empty and the body inspects
the fields directly (the one legitimate place a body reads possibly-absent
fields — because absence is the signal, per SHALqc.md §3.3).
"""

from __future__ import annotations

from app.normalize import normalize
from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Evidence, Status, Verdict

_REFI_BLANK_FIELDS = ["contract_price", "contract_date", "concessions_amount"]


def _is_purchase(ctx: QCContext) -> bool:
    return ctx.transaction_type == "purchase"


def _is_refi(ctx: QCContext) -> bool:
    return ctx.transaction_type == "refinance"


def _truthy(raw) -> bool:
    return normalize("boolean", raw) == "True"


# ── C-1 (purchase) contract analyzed ────────────────────────────────────────

@rule(id="C-1", checklist="14", section="contract", version=1,
      applies_when=_is_purchase, name="Contract analyzed (purchase)")
def c1_analyzed(ctx: QCContext) -> Verdict:
    ev = ctx.appraisal.evidence("did_analyze_contract")
    if _truthy(ctx.appraisal.value("did_analyze_contract")):
        return Verdict(rule_id="C-1", status=Status.PASS, evidence=[ev],
                       fields_involved=["did_analyze_contract"])
    # Not marked analyzed on a purchase — low confidence can't auto-FAIL (P4).
    status = Status.FAIL if ev.confidence >= ctx.review_conf else Status.VERIFY
    return Verdict(
        rule_id="C-1", status=status, message_key="C-1.not_analyzed",
        message="Purchase order: the contract-analysis box is not marked analyzed.",
        evidence=[ev], fields_involved=["did_analyze_contract"], confidence=0.8,
    )


# ── C-1R (refinance) contract section must be blank ─────────────────────────

@rule(id="C-1R", checklist="14", section="contract", version=1,
      applies_when=_is_refi, name="Contract section blank (refinance)")
def c1_refi_blank(ctx: QCContext) -> Verdict:
    populated = [f for f in _REFI_BLANK_FIELDS
                 if ctx.appraisal.value(f) and ctx.appraisal.confidence(f) >= ctx.review_conf]
    if not populated:
        return Verdict(rule_id="C-1R", status=Status.PASS, fields_involved=_REFI_BLANK_FIELDS)
    ev = [ctx.appraisal.evidence(f) for f in populated]
    return Verdict(
        rule_id="C-1R", status=Status.FAIL, message_key="C-1.refi_not_blank",
        message="Refinance order: the contract section must be blank but carries "
                + ", ".join(populated) + ".",
        evidence=ev, fields_involved=populated, confidence=0.85,
    )
