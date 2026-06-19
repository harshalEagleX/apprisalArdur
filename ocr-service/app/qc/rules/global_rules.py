"""
Cross-cutting rules that don't belong to one report section.

G-1 loan-type discrepancy: engagement letter says Conventional but the
appraisal carries FHA markers (case number / FHA boxes) — escalate as HOLD,
per the agreed rule that loan type from the engagement letter is authoritative
and any conflict is material.
"""

from __future__ import annotations

import re

from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

# FHA case numbers follow the format: digits-digits (e.g. "051-8234567").
# They always contain a hyphen and are never purely numeric.
_FHA_CASE_RE = re.compile(r"^\d{2,3}-\d{7}$")


def _is_fha_case_number(value: str) -> bool:
    """Return True only when the value looks like a genuine FHA case number.
    Purely-numeric strings (lender order/tracking numbers) are excluded."""
    if not value:
        return False
    v = value.strip()
    return bool(_FHA_CASE_RE.match(v))


@rule(id="G-1", num="B", section="global", phase=2, name="Loan-type consistency (engagement vs appraisal)")
def g1_loan_type(ctx: QCContext):
    eng_loan = ctx.loan_type
    # Check both the appraisal and engagement for an FHA case number.
    # Validate format: FHA numbers contain a hyphen (e.g. "051-8234567");
    # purely-numeric lender tracking numbers are never FHA case numbers.
    appr_case = ctx.appraisal.value("fha_case_number") or ""
    eng_case = ctx.engagement.value("fha_case_number") or ""
    fha_markers = _is_fha_case_number(appr_case) or _is_fha_case_number(eng_case)
    ev = [ctx.engagement.evidence("loan_type"), ctx.appraisal.evidence("fha_case_number")]
    if not ctx.has_engagement:
        return RuleResult(rule_id="G-1", checklist_num="B", section="global",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="Engagement letter / order form not available.", evidence=ev)
    if eng_loan == "conventional" and fha_markers:
        return RuleResult(rule_id="G-1", checklist_num="B", section="global",
                          status=RuleStatus.HOLD,
                          message="Engagement letter indicates Conventional but the appraisal "
                                  "carries an FHA case number. Loan-type discrepancy — escalate.",
                          fields_involved=["loan_type", "fha_case_number"], evidence=ev)
    return RuleResult(rule_id="G-1", checklist_num="B", section="global",
                      status=RuleStatus.PASS, fields_involved=["loan_type"], evidence=ev)
