"""
Signature page rules (SIG-1, SIG-2, date sequencing / checklist 96-112)
and the reconciliation date relationship (signature date >= effective date).
"""

from __future__ import annotations

import datetime as _dt

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


def _parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---- SIG-1 appraiser signature / name present -----------------------------

@rule(id="SIG-1", num="96", section="signature", phase=1, name="Appraiser signed / name present")
def sig1_signed(ctx: QCContext):
    val = ctx.appraisal.value("appraiser_name") or ctx.appraisal.value("date_of_signature")
    ev = [ctx.appraisal.evidence("appraiser_name"), ctx.appraisal.evidence("date_of_signature")]
    if val and str(val).strip():
        return RuleResult(rule_id="SIG-1", checklist_num="96", section="signature",
                          status=RuleStatus.PASS, fields_involved=["appraiser_name"], evidence=ev)
    return RuleResult(rule_id="SIG-1", checklist_num="96", section="signature",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SIG-1-missing"),
                      fields_involved=["appraiser_name", "date_of_signature"],
                      template_id="SIG-1-missing", evidence=ev, confidence=0.6)


# ---- SIG date sequencing: signature date >= effective date ----------------

@rule(id="SIG-D", num="101", section="signature", phase=1, name="Signature date >= effective date")
def sig_date_sequence(ctx: QCContext):
    sig = _parse_date(ctx.appraisal.value("date_of_signature"))
    eff = _parse_date(ctx.appraisal.value("effective_date"))
    ev = [ctx.appraisal.evidence("date_of_signature"), ctx.appraisal.evidence("effective_date")]
    if sig is None or eff is None:
        return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                          status=RuleStatus.SKIPPED, message="signature/effective date not parseable",
                          fields_involved=["date_of_signature", "effective_date"], evidence=ev)
    if sig >= eff:
        return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                          status=RuleStatus.PASS,
                          fields_involved=["date_of_signature", "effective_date"], evidence=ev)
    return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("SIG-date"),
                      fields_involved=["date_of_signature", "effective_date"],
                      template_id="SIG-date", evidence=ev)


# ---- SIG-2 appraiser name matches engagement ------------------------------

@rule(id="SIG-2", num="G", section="signature", phase=2,
      applies_when=lambda ctx: ctx.has_engagement and bool(ctx.engagement.value("appraiser_name")),
      name="Appraiser name matches engagement")
def sig2_appraiser_name(ctx: QCContext):
    return H.cross_doc_match(ctx, "SIG-2", "G", "signature", "appraiser_name", "SIG-2-field",
                             authority="engagement", kind="name", label="Appraiser name")
