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
        # confidence gate @ 0.90
        conf = min(ctx.appraisal.confidence("date_of_signature"),
                   ctx.appraisal.confidence("effective_date"))
        if conf >= 0.90:
            return RuleResult(rule_id="SIG-D", checklist_num="101", section="signature",
                              status=RuleStatus.PASS,
                              fields_involved=["date_of_signature", "effective_date"], evidence=ev)
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
        # confidence gate @ 0.85
        conf = min(ctx.appraisal.confidence("appraiser_cert_expiration_date"),
                   ctx.appraisal.confidence("date_of_signature"))
        if conf >= ctx.checkbox_conf:
            return RuleResult(rule_id="DOC-1", checklist_num="113", section="signature",
                              status=RuleStatus.PASS,
                              fields_involved=["appraiser_cert_expiration_date"], evidence=ev)
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

# URAR form prints "(only if required)" as placeholder text in the supervisor
# section when no supervisor applies. OCR reads this as a name — filter it out.
_SUPERVISOR_PLACEHOLDER = {
    "only if required", "(only if required)", "n/a", "na", "not applicable",
    "if applicable", "only if applicable",
}


def _has_supervisor(ctx: QCContext) -> bool:
    name = (ctx.appraisal.value("supervisory_appraiser_name") or "").strip().lower()
    cert = ctx.appraisal.value("supervisory_appraiser_cert_number")
    if name in _SUPERVISOR_PLACEHOLDER:
        return False
    return bool(name or cert)


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
    # name_containment: the order form's appraiser name is the required identity;
    # the report may add a middle name the order form omitted (e.g. "John Jenkins"
    # vs "John Brandon Jenkins") without that being a genuine mismatch.
    return H.cross_doc_match(ctx, "SIG-2", "G", "signature", "appraiser_name", "SIG-2-field",
                             authority="engagement", kind="name_containment", label="Appraiser name")


# ---- SIG-4 appraiser email present -----------------------------------------

@rule(id="SIG-4", num="103", section="signature", phase=2, name="Appraiser email present")
def sig4_email(ctx: QCContext):
    email = str(ctx.appraisal.value("appraiser_email") or "").strip()
    ev = [ctx.appraisal.evidence("appraiser_email")]
    if "@" in email and "." in email.split("@")[-1]:
        return RuleResult(rule_id="SIG-4", checklist_num="103", section="signature",
                          status=RuleStatus.PASS, fields_involved=["appraiser_email"], evidence=ev)
    # confidence gate @ 0.90
    conf = ctx.appraisal.confidence("appraiser_email")
    if conf >= 0.90:
        return RuleResult(rule_id="SIG-4", checklist_num="103", section="signature",
                          status=RuleStatus.PASS, fields_involved=["appraiser_email"], evidence=ev)
    return RuleResult(rule_id="SIG-4", checklist_num="103", section="signature",
                      status=RuleStatus.VERIFY, message=qc_config.template("SIG-4-email"),
                      fields_involved=["appraiser_email"], template_id="SIG-4-email",
                      evidence=ev, confidence=0.6)


# ============================================================================
# NEW RULES — appended below existing rules (do not modify above)
# ============================================================================

# ---- SIG-TRAINEE Trainee appraiser requires supervisory cosign --------------
#
# When the appraiser's license type identifies them as a trainee or apprentice,
# USPAP and state regulations require a supervisory appraiser to co-sign.
# Both the supervisory appraiser's name AND license/certificate number must be
# present; missing either is a hard FAIL.

import re as _re   # re is already imported at module level, but guard for append safety

_TRAINEE_RX = _re.compile(
    r"trainee|apprentice|(?<!\w)at\b|registered\s+appraiser\s+trainee", _re.I,
)


@rule(id="SIG-TRAINEE", num="SIG-trainee", section="signature", phase=2,
      name="Trainee appraiser requires supervisory cosign")
def sig_trainee(ctx: QCContext):
    lic_type = (ctx.appraisal.value("appraiser_license_type") or "").strip()
    sup_name = (ctx.appraisal.value("supervisory_appraiser_name") or "").strip()
    sup_lic = (
        ctx.appraisal.value("supervisory_appraiser_cert_number")
        or ctx.appraisal.value("supervisory_appraiser_license_number")
        or ""
    ).strip()
    ev = [
        ctx.appraisal.evidence("appraiser_license_type"),
        ctx.appraisal.evidence("supervisory_appraiser_name"),
        ctx.appraisal.evidence("supervisory_appraiser_cert_number"),
    ]
    fields = [
        "appraiser_license_type",
        "supervisory_appraiser_name",
        "supervisory_appraiser_cert_number",
    ]

    if not lic_type:
        # Cannot evaluate — data missing.
        return RuleResult(
            rule_id="SIG-TRAINEE", checklist_num="SIG-trainee", section="signature",
            status=RuleStatus.NOT_APPLICABLE,
            message="Appraiser license type could not be read; trainee check skipped.",
            fields_involved=fields, evidence=ev,
        )

    if not _TRAINEE_RX.search(lic_type):
        # Not a trainee designation — rule does not apply.
        return RuleResult(
            rule_id="SIG-TRAINEE", checklist_num="SIG-trainee", section="signature",
            status=RuleStatus.NOT_APPLICABLE, fields_involved=fields, evidence=ev,
        )

    # Trainee identified — supervisory name AND license are both required.
    if sup_name and sup_lic:
        return RuleResult(
            rule_id="SIG-TRAINEE", checklist_num="SIG-trainee", section="signature",
            status=RuleStatus.PASS, fields_involved=fields, evidence=ev,
        )

    return RuleResult(
        rule_id="SIG-TRAINEE", checklist_num="SIG-trainee", section="signature",
        status=RuleStatus.FAIL,
        message=qc_config.template("SIG-TRAINEE", type=lic_type),
        fields_involved=fields, template_id="SIG-TRAINEE", evidence=ev,
    )


# ---- SIG-CO Appraiser company name/address/phone present (checklist 97-99) --
#
# The signature block must identify the appraiser's company by name, address AND
# phone (checklist items 97, 98, 99). All three come from the MISMO APPRAISER
# party (company name + address attributes; phone from CONTACT_DETAIL). None had
# a rule before. Absence is surfaced as VERIFY — not FAIL — because these are also
# read positionally from the PDF on some layouts and can be missed, so we ask a
# human rather than hard-rejecting a value we may simply have failed to read.
@rule(id="SIG-CO", num="97,98,99", section="signature", phase=2,
      name="Appraiser company name, address and phone present")
def sig_company(ctx: QCContext):
    out = []
    for field, num, tmpl in (
        ("appraiser_company_name", "97", "SIG-CO-name"),
        ("appraiser_company_address", "98", "SIG-CO-addr"),
        ("appraiser_phone", "99", "SIG-CO-phone"),
    ):
        val = str(ctx.appraisal.value(field) or "").strip()
        ev = [ctx.appraisal.evidence(field)]
        if len(val) >= 3:
            out.append(RuleResult(
                rule_id="SIG-CO", checklist_num=num, section="signature",
                status=RuleStatus.PASS, fields_involved=[field], evidence=ev))
        else:
            out.append(RuleResult(
                rule_id="SIG-CO", checklist_num=num, section="signature",
                status=RuleStatus.VERIFY, message=qc_config.template(tmpl),
                fields_involved=[field], template_id=tmpl, evidence=ev, confidence=0.6))
    return out
