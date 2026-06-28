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


# ---- G-C56 C5/C6 condition → HOLD when AMC policy says stop ----------------
# Source: Equity Solutions USA EL body: "C5 or C6 condition, please stop all work"
# Activation: only when policy.stop_on_c5_c6 is True (loaded from amc_policies.yaml)

@rule(id="G-C56", num="G-c56", section="global", phase=1,
      applies_when=lambda ctx: ctx.policy.is_active("stop_on_c5_c6", default=False),
      name="C5/C6 condition triggers AMC stop")
def g_c56_stop(ctx: QCContext):
    cond = (ctx.appraisal.value("subject_grid_condition_rating")
            or ctx.appraisal.value("condition_rating") or "").upper().strip()
    ev = [ctx.appraisal.evidence("subject_grid_condition_rating")]
    if not cond:
        return RuleResult(rule_id="G-C56", checklist_num="G-c56", section="global",
                          status=RuleStatus.SKIPPED,
                          message="Subject condition rating could not be read; C5/C6 stop check skipped.",
                          fields_involved=["subject_grid_condition_rating"], evidence=ev)
    if cond in ("C5", "C6"):
        return RuleResult(rule_id="G-C56", checklist_num="G-c56", section="global",
                          status=RuleStatus.HOLD,
                          message=f"Subject property is rated {cond}. The engagement letter requires stopping all work and contacting the AMC before proceeding when the subject is in C5 or C6 condition.",
                          fields_involved=["subject_grid_condition_rating"], evidence=ev)
    return RuleResult(rule_id="G-C56", checklist_num="G-c56", section="global",
                      status=RuleStatus.PASS, fields_involved=["subject_grid_condition_rating"], evidence=ev)


# ---- G-LAVA Hawaiian lava zones 1 and 2 → HOLD when policy says stop --------
# Source: Equity Solutions USA EL body: "lava zones 1 and 2, please stop all work"

@rule(id="G-LAVA", num="G-lava", section="global", phase=1,
      applies_when=lambda ctx: (
          ctx.policy.is_active("stop_on_lava_zone", default=False)
          and (ctx.order.state or "").upper() == "HI"
      ),
      name="Hawaiian lava zone triggers AMC stop")
def g_lava_stop(ctx: QCContext):
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    zip_code = (ctx.appraisal.value("zip_code") or ctx.order.zip_code or "")
    ev = [ctx.appraisal.evidence("addendum_text")]

    # Lava zones 1 and 2 are on the Big Island (Hawaii County, zip 967xx)
    # Maui and Oahu properties are not in lava zones 1/2
    if not zip_code.startswith("967"):
        return RuleResult(rule_id="G-LAVA", checklist_num="G-lava", section="global",
                          status=RuleStatus.PASS,
                          message="Subject ZIP code does not indicate Big Island (lava zones 1-2 area); lava zone check passed.",
                          fields_involved=["zip_code"], evidence=ev)

    import re
    if re.search(r"lava\s+zone\s*[12]\b", addendum, re.I):
        return RuleResult(rule_id="G-LAVA", checklist_num="G-lava", section="global",
                          status=RuleStatus.HOLD,
                          message="The property appears to be in a Hawaiian lava zone 1 or 2. The engagement letter requires stopping all work and contacting the AMC immediately.",
                          fields_involved=["addendum_text"], evidence=ev)

    # Big Island property but no explicit lava zone mention — flag for reviewer
    return RuleResult(rule_id="G-LAVA", checklist_num="G-lava", section="global",
                      status=RuleStatus.VERIFY,
                      message="Subject is in Hawaii (Big Island ZIP). Please confirm the property is not in lava zone 1 or 2; the engagement letter requires stopping work if it is.",
                      fields_involved=["zip_code"], evidence=ev, confidence=0.6)


# ---- G-MFG Pre-1976 manufactured home → HOLD when policy says stop ----------
# Source: Equity Solutions USA EL body: "Manufactured Home built prior to June 15, 1976"

@rule(id="G-MFG", num="G-mfg", section="global", phase=1,
      applies_when=lambda ctx: ctx.policy.is_active("stop_on_pre1976_manufactured", default=False),
      name="Pre-1976 manufactured home triggers AMC stop")
def g_mfg_stop(ctx: QCContext):
    design = (ctx.appraisal.value("design_style") or "").lower()
    year_built_raw = ctx.appraisal.value("year_built") or ctx.order.zip_code
    year_built_raw = ctx.appraisal.value("year_built") or ""
    ev = [ctx.appraisal.evidence("design_style"), ctx.appraisal.evidence("year_built")]

    import re
    is_manufactured = re.search(r"manufactured|mobile\s+home|modular", design, re.I) is not None
    if not is_manufactured:
        return RuleResult(rule_id="G-MFG", checklist_num="G-mfg", section="global",
                          status=RuleStatus.NOT_APPLICABLE,
                          message="Property does not appear to be a manufactured home.",
                          fields_involved=["design_style"], evidence=ev)

    year_m = re.search(r"\b(19\d{2}|20\d{2})\b", str(year_built_raw))
    if not year_m:
        return RuleResult(rule_id="G-MFG", checklist_num="G-mfg", section="global",
                          status=RuleStatus.VERIFY,
                          message="Subject appears to be a manufactured home but the year built could not be confirmed. Please verify the subject was not built before June 15, 1976; the engagement letter requires stopping work if it was.",
                          fields_involved=["year_built"], evidence=ev, confidence=0.5)

    year = int(year_m.group(1))
    if year < 1976:
        return RuleResult(rule_id="G-MFG", checklist_num="G-mfg", section="global",
                          status=RuleStatus.HOLD,
                          message=f"Subject is a manufactured home built in {year}, which is before the June 15, 1976 HUD standard cutoff. The engagement letter requires stopping all work and contacting the AMC immediately.",
                          fields_involved=["design_style", "year_built"], evidence=ev)

    return RuleResult(rule_id="G-MFG", checklist_num="G-mfg", section="global",
                      status=RuleStatus.PASS, fields_involved=["design_style", "year_built"], evidence=ev)
