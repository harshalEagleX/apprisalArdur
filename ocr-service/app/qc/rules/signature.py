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
                          status=RuleStatus.VERIFY,
                          message="The signature date or effective date could not be read; please verify the signature date is on or after the effective date.",
                          fields_involved=["date_of_signature", "effective_date"], evidence=ev, confidence=0.5)
    if sig >= eff:
        gap_days = int(qc_config.semantic("signature_gap_days", 30))
        if (sig - eff).days > gap_days:
            # signing long after inspection is unusual — reviewer confirms the
            # reporting timeline
            return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                              status=RuleStatus.VERIFY,
                              message=qc_config.template("SIG-1-gap", value=gap_days),
                              fields_involved=["date_of_signature", "effective_date"],
                              template_id="SIG-1-gap", evidence=ev, confidence=0.6)
        return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                          status=RuleStatus.PASS,
                          fields_involved=["date_of_signature", "effective_date"], evidence=ev)
    return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("SIG-date"),
                      fields_involved=["date_of_signature", "effective_date"],
                      template_id="SIG-date", evidence=ev)


# ---- DOC-1 license not expired at signature ---------------------------------

@rule(id="DOC-1", num="113", section="signature", phase=2, name="License current at signature")
def doc1_license_current(ctx: QCContext):
    exp = _parse_date(ctx.appraisal.value("appraiser_cert_expiration_date"))
    sig = _parse_date(ctx.appraisal.value("date_of_signature"))
    ev = [ctx.appraisal.evidence("appraiser_cert_expiration_date"),
          ctx.appraisal.evidence("date_of_signature")]
    if exp is None or sig is None:
        return RuleResult(rule_id="DOC-1", checklist_num="113", section="signature",
                          status=RuleStatus.VERIFY,
                          message="The license expiration or signature date could not be read; please verify the license was current when the report was signed.",
                          fields_involved=["appraiser_cert_expiration_date", "date_of_signature"],
                          evidence=ev, confidence=0.5)
    if exp >= sig:
        return RuleResult(rule_id="DOC-1", checklist_num="113", section="signature",
                          status=RuleStatus.PASS,
                          fields_involved=["appraiser_cert_expiration_date"], evidence=ev)
    # an expired license has no tolerance
    return RuleResult(rule_id="DOC-1", checklist_num="113", section="signature",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("DOC-1-expired"),
                      fields_involved=["appraiser_cert_expiration_date", "date_of_signature"],
                      template_id="DOC-1-expired", evidence=ev)


# ---- SIG-SUP supervisory appraiser section consistency -----------------------

def _has_supervisor(ctx: QCContext) -> bool:
    return bool(ctx.appraisal.value("supervisory_appraiser_name")
                or ctx.appraisal.value("supervisory_appraiser_cert_number"))


@rule(id="SIG-SUP", num="111", section="signature", phase=2, applies_when=_has_supervisor,
      name="Supervisory appraiser section complete")
def sig_supervisor(ctx: QCContext):
    inspect = (ctx.appraisal.value("supervisory_appraiser_did_inspect") or "").strip()
    ev = [ctx.appraisal.evidence("supervisory_appraiser_name"),
          ctx.appraisal.evidence("supervisory_appraiser_did_inspect")]
    if inspect:
        return RuleResult(rule_id="SIG-SUP", checklist_num="111", section="signature",
                          status=RuleStatus.PASS,
                          fields_involved=["supervisory_appraiser_name",
                                           "supervisory_appraiser_did_inspect"], evidence=ev)
    return RuleResult(rule_id="SIG-SUP", checklist_num="111", section="signature",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("SIG-sup"),
                      fields_involved=["supervisory_appraiser_name",
                                       "supervisory_appraiser_did_inspect"],
                      template_id="SIG-sup", evidence=ev, confidence=0.6)


# ---- SIG-3 appraiser licensed in the property's state ---------------------

@rule(id="SIG-3", num="102", section="signature", phase=2,
      name="Appraiser licensed in property state")
def sig3_license_state(ctx: QCContext):
    lic = (ctx.appraisal.value("appraiser_license_state") or "").strip().upper()
    prop = (ctx.appraisal.value("state") or "").strip().upper()
    ev = [ctx.appraisal.evidence("appraiser_license_state"), ctx.appraisal.evidence("state")]
    if not lic or not prop:
        return RuleResult(rule_id="SIG-3", checklist_num="102", section="signature",
                          status=RuleStatus.VERIFY,
                          message="The appraiser license state or property state could not be read; please verify the appraiser is licensed in the property's state.",
                          fields_involved=["appraiser_license_state", "state"], evidence=ev, confidence=0.5)
    if lic == prop:
        return RuleResult(rule_id="SIG-3", checklist_num="102", section="signature",
                          status=RuleStatus.PASS,
                          fields_involved=["appraiser_license_state", "state"], evidence=ev)
    return RuleResult(rule_id="SIG-3", checklist_num="102", section="signature",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("SIG-3-state", a=lic, b=prop),
                      fields_involved=["appraiser_license_state", "state"],
                      template_id="SIG-3-state", evidence=ev)


# ---- SIG-2 appraiser name matches engagement ------------------------------

@rule(id="SIG-2", num="G", section="signature", phase=2,
      applies_when=lambda ctx: ctx.has_engagement and bool(ctx.engagement.value("appraiser_name")),
      name="Appraiser name matches engagement")
def sig2_appraiser_name(ctx: QCContext):
    return H.cross_doc_match(ctx, "SIG-2", "G", "signature", "appraiser_name", "SIG-2-field",
                             authority="engagement", kind="name", label="Appraiser name")
