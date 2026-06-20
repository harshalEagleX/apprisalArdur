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


# ---- G-0 engagement letter completeness gate --------------------------------
#
# This must be phase=1 (lowest phase number) so it fires before any overlay
# rule that reads engagement fields. When the engagement is absent, dependent
# rules that check engagement values will see empty DocView fields and produce
# meaningless NOT_APPLICABLE or false-PASS results — this gate makes that
# structural gap BLOCKING (HOLD) rather than silent.
#
# Honest scope: v1 detects absence at the Python boundary (engagement_path=None
# → DocView.present=False). Distinguishing PENDING vs NOT_PROVIDED vs
# EXTRACTION_FAILED requires the Java/batch matcher to forward per-document
# ingestion status, which is a deferred phase-2 item.

@rule(id="G-0", num="B0", section="global", phase=1,
      name="Engagement letter / order form present and extracted")
def g0_engagement_present(ctx: QCContext):
    ev = [ctx.engagement.evidence("loan_type")]
    if ctx.has_engagement:
        return RuleResult(rule_id="G-0", checklist_num="B0", section="global",
                          status=RuleStatus.PASS,
                          fields_involved=["loan_type"], evidence=ev)

    # Engagement not present at the Python boundary. Branch on the ingestion status
    # forwarded by the Java/batch matcher (Layer A — data existence):
    #   NOT_PROVIDED         → genuinely no engagement for this workflow → N/A.
    #   PENDING / FAILED /   → the document exists but isn't usable → BLOCKING HOLD.
    #   None (not forwarded) → unknown → block, since silently passing overlay rules
    #                          on missing authority data is the failure mode G-0 exists
    #                          to prevent.
    status = getattr(ctx, "engagement_status", None)
    if status == "NOT_PROVIDED":
        return RuleResult(rule_id="G-0", checklist_num="B0", section="global",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="No engagement letter / order form is associated with this "
                                  "transaction; lender-overlay rules do not apply.",
                          fields_involved=["loan_type"], evidence=ev)
    detail = {
        "PENDING": "is still awaiting extraction (status: PENDING)",
        "EXTRACTION_FAILED": "failed to extract (status: EXTRACTION_FAILED)",
    }.get(status, "was not extracted")
    return RuleResult(
        rule_id="G-0", checklist_num="B0", section="global",
        status=RuleStatus.HOLD,
        message=(
            f"The engagement letter / order form {detail}. "
            "All lender-overlay rules (comp count minimum, site value requirement, "
            "declining-market clause, AMC naming) cannot be evaluated without it. "
            "Re-process after the engagement document is available."
        ),
        fields_involved=["loan_type"], evidence=ev,
    )


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
