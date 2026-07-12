"""
Deterministic cross-field / cross-section rules (T1) — SHALqc.md §5.

These implement catalog same_section/cross_section checks whose logic IS
machine-evaluable from extracted (layout-independent) fields — converting them
from a blanket VERIFY into a real PASS/FAIL. Each dedups the catalog's generated
version (hand-coded wins). Every comparison routes through the ONE normalizer;
the needs[] gate handles missing/low-confidence inputs (→ VERIFY), so a body
here only runs on trusted data (P4).
"""

from __future__ import annotations

from app.normalize import compare as _compare
from app.normalize import dates as _dates
from app.normalize import normalize as _normalize
from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Status, Verdict

_TRUTHY = {"true", "yes", "1", "x", "checked"}


def _num(raw):
    n = _normalize("currency", raw)
    try:
        return float(n) if n is not None else None
    except (TypeError, ValueError):
        return None


# ── S-9 HOA dues present ⇒ PUD must be marked ───────────────────────────────

@rule(id="S-9", checklist="11", section="subject", version=1,
      needs=["hoa_dues", "is_pud"], name="HOA dues imply PUD marked")
def s9_hoa_pud(ctx: QCContext) -> Verdict:
    amt = _num(ctx.appraisal.value("hoa_dues"))
    pud = str(ctx.appraisal.value("is_pud") or "").strip().lower() in _TRUTHY
    ev = [ctx.appraisal.evidence("hoa_dues"), ctx.appraisal.evidence("is_pud")]
    if not amt or amt <= 0 or pud:
        return Verdict(rule_id="S-9", status=Status.PASS, evidence=ev,
                       fields_involved=["hoa_dues", "is_pud"])
    return Verdict(rule_id="S-9", status=Status.FAIL, confidence=0.8,
                   message_key="S-9.pud_not_marked",
                   message=f"HOA dues ({ctx.appraisal.value('hoa_dues')}) are present but PUD is not marked.",
                   evidence=ev, fields_involved=["hoa_dues", "is_pud"])


# ── I-AGE effective age ≤ actual age ────────────────────────────────────────

@rule(id="I-AGE", checklist="45", section="improvements", version=1,
      needs=["effective_age"], name="Effective age not greater than actual age")
def i_age(ctx: QCContext) -> Verdict:
    eff = _num(ctx.appraisal.value("effective_age"))
    actual = _num(ctx.appraisal.value("actual_age"))
    ev = [ctx.appraisal.evidence("effective_age"), ctx.appraisal.evidence("year_built")]
    if actual is None:
        # derive actual age from year_built + effective_date year
        yb = _dates.year_of(ctx.appraisal.value("year_built"))
        ey = _dates.year_of(ctx.appraisal.value("effective_date"))
        if yb and ey:
            actual = ey - yb
    if eff is None or actual is None:
        return Verdict(rule_id="I-AGE", status=Status.VERIFY, confidence=0.5,
                       message="Could not compute actual age — please confirm effective age is reasonable.",
                       evidence=ev, fields_involved=["effective_age", "year_built"])
    if eff <= actual + 0.5:
        return Verdict(rule_id="I-AGE", status=Status.PASS, evidence=ev,
                       fields_involved=["effective_age", "year_built"])
    return Verdict(rule_id="I-AGE", status=Status.FAIL, confidence=0.8,
                   message_key="I-AGE.eff_gt_actual",
                   message=f"Effective age ({eff:.0f}) exceeds actual age ({actual:.0f}).",
                   evidence=ev, fields_involved=["effective_age", "year_built"])


# ── R-1 SCA indicated value == final/appraised value ────────────────────────

@rule(id="R-1", checklist="R1", section="reconciliation", version=1,
      needs=["final_value_sca", "appraised_value"],
      name="SCA indicated value equals final value")
def r1_value(ctx: QCContext) -> Verdict:
    a, b = _num(ctx.appraisal.value("final_value_sca")), _num(ctx.appraisal.value("appraised_value"))
    ev = [ctx.appraisal.evidence("final_value_sca"), ctx.appraisal.evidence("appraised_value")]
    if a is None or b is None:
        return Verdict(rule_id="R-1", status=Status.VERIFY, confidence=0.5,
                       message="Could not compare indicated vs final value.", evidence=ev)
    if a == b:
        return Verdict(rule_id="R-1", status=Status.PASS, evidence=ev,
                       fields_involved=["final_value_sca", "appraised_value"])
    return Verdict(rule_id="R-1", status=Status.FAIL, confidence=0.85,
                   message_key="R-1.value_mismatch",
                   message=f"Sales-comparison value ({a:.0f}) does not equal the final value ({b:.0f}).",
                   evidence=ev, fields_involved=["final_value_sca", "appraised_value"])


# ── SIG-D signature date on/after effective date ────────────────────────────

@rule(id="SIG-D", checklist="SIG-D", section="signature", version=1,
      needs=["signature_date", "effective_date"], name="Signature date on/after effective date")
def sig_d(ctx: QCContext) -> Verdict:
    sd = _dates.parse_date(ctx.appraisal.value("signature_date"))
    ed = _dates.parse_date(ctx.appraisal.value("effective_date"))
    ev = [ctx.appraisal.evidence("signature_date"), ctx.appraisal.evidence("effective_date")]
    if sd is None or ed is None:
        return Verdict(rule_id="SIG-D", status=Status.VERIFY, confidence=0.5,
                       message="Could not compare signature and effective dates.", evidence=ev)
    if sd >= ed:
        return Verdict(rule_id="SIG-D", status=Status.PASS, evidence=ev,
                       fields_involved=["signature_date", "effective_date"])
    return Verdict(rule_id="SIG-D", status=Status.FAIL, confidence=0.85,
                   message_key="SIG-D.signed_before_effective",
                   message=f"Signature date ({sd.isoformat()}) is before the effective date ({ed.isoformat()}).",
                   evidence=ev, fields_involved=["signature_date", "effective_date"])


# ── SIG-3 appraiser license state == subject state ──────────────────────────

@rule(id="SIG-3", checklist="SIG-3", section="signature", version=1,
      needs=["appraiser_license_state", "state"], name="Appraiser licensed in subject state")
def sig_3(ctx: QCContext) -> Verdict:
    mr = _compare(None, ctx.appraisal.value("appraiser_license_state"),
                  ctx.appraisal.value("state"), kind=None)
    ev = [ctx.appraisal.evidence("appraiser_license_state"), ctx.appraisal.evidence("state")]
    if mr.verdict == "match":
        return Verdict(rule_id="SIG-3", status=Status.PASS, evidence=ev,
                       fields_involved=["appraiser_license_state", "state"])
    return Verdict(rule_id="SIG-3", status=Status.FAIL, confidence=0.8,
                   message_key="SIG-3.license_state_mismatch",
                   message=f"Appraiser license state ({ctx.appraisal.value('appraiser_license_state')}) "
                           f"differs from the subject state ({ctx.appraisal.value('state')}).",
                   evidence=ev, fields_involved=["appraiser_license_state", "state"])
