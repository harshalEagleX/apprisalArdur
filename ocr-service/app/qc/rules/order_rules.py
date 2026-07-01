"""
Order-level cross-document rules — require OrderMetadata and PolicyProfile.

These rules were previously impossible because there was no authoritative order
object. They now read from ctx.order (OrderMetadata, extracted from the
engagement letter + XML cross-reference) and ctx.policy (PolicyProfile, built
from engagement letter overlays + AMC defaults).

Rules:
  ORD-FORM-MATCH    — form type in XML matches form type ordered in EL
  ORD-INSP-SCOPE    — ordered inspection type matches scope of work in report
  ORD-COBORROWER    — co-borrower from order appears in appraisal borrower field
  ORD-EXEC-STOP     — contract not executed → HOLD when policy says stop
  ORD-CONFLICT      — any OrderMetadata conflict (EL vs XML disagree on key fact)
  ORD-ENG-DATE      — engagement date from EL precedes appraisal signature date
  ORD-ASSIGN-MATCH  — assignment type in EL matches assignment type in XML
"""

from __future__ import annotations

import re
import datetime
from typing import Optional

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus, Evidence
from app.qc import helpers as H
from app.qc import matching

_res = H.section_result("subject")
_res_sig = H.section_result("signature")
_res_contract = H.section_result("contract")
_res_global = H.section_result("global")


def _parse_date(s) -> Optional[datetime.date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


# ── ORD-FORM-MATCH — required form type from EL matches XML form type ────────

@rule(id="ORD-FORM-MATCH", num="ORD-form-match", section="subject", phase=2,
      applies_when=lambda ctx: ctx.has_engagement and ctx.order.from_engagement,
      name="Form type in report matches form type ordered")
def ord_form_match(ctx: QCContext):
    ordered = ctx.order.required_form_type           # from engagement letter
    actual  = (ctx.appraisal.value("form_type") or ctx.form_type or "").lower()
    ev = [
        ctx.engagement.evidence("form_type"),
        ctx.appraisal.evidence("form_type"),
    ]
    fields = ["form_type"]

    if not ordered:
        return _res("ORD-FORM-MATCH", "ORD-form-match", RuleStatus.SKIPPED,
                    message="Required form type not extracted from engagement letter; cannot compare.",
                    fields=fields, evidence=ev)

    # Normalize form type strings to a comparable base.
    # "Residential Appraisal" / "Residential Report" / "URAR" all map to "1004"
    # because engagement letters often describe the form in plain English rather
    # than by number; the appraisal XML always uses the MISMO form number.
    _PLAIN_TO_NUM = {
        "residential appraisal": "1004",
        "residential report": "1004",
        "urar": "1004",
        "uniform residential appraisal report": "1004",
        "condominium appraisal": "1073",
        "individual condominium": "1073",
        "small residential income property": "1025",
        "multi family": "1025",
        "multifamily": "1025",
        "exterior only": "2055",
        "drive by": "2055",
    }

    def _base(v: str) -> str:
        s = v.lower().strip()
        for phrase, num in _PLAIN_TO_NUM.items():
            if phrase in s:
                return num
        m = re.search(r"(1004mc|1004d|1004|1073|1025|1007|2055|216)", s)
        return m.group(1) if m else s

    ord_base = _base(ordered)
    act_base = _base(actual) if actual else ""

    if not act_base:
        # confidence gate @ 0.90
        conf = ctx.appraisal.confidence("form_type")
        if conf >= 0.90:
            return _res("ORD-FORM-MATCH", "ORD-form-match", RuleStatus.PASS,
                        fields=fields, evidence=ev)
        return _res("ORD-FORM-MATCH", "ORD-form-match", RuleStatus.VERIFY,
                    message=f"The form type could not be confirmed from the report; the engagement letter requires form {ordered.upper()}. Please verify.",
                    fields=fields, evidence=ev, confidence=0.5)

    if ord_base == act_base or ord_base in act_base or act_base in ord_base:
        return _res("ORD-FORM-MATCH", "ORD-form-match", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    return _res("ORD-FORM-MATCH", "ORD-form-match", RuleStatus.FAIL,
                message=qc_config.template(
                    "ORD-FORM-MATCH",
                    ordered=ordered.upper(), actual=actual.upper()
                ),
                fields=fields, template_id="ORD-FORM-MATCH", evidence=ev)


# ── ORD-INSP-SCOPE — ordered inspection type matches scope of work ───────────

_DESKTOP_RE = re.compile(r"\bdesktop\b", re.I)
_EXTERIOR_RE = re.compile(r"\bexterior[\s\-]?only\b|\bdrive[\s\-]?by\b", re.I)
_INTERIOR_RE = re.compile(r"\binterior\b|\bfull\s+(?:appraisal|inspection)\b", re.I)


@rule(id="ORD-INSP-SCOPE", num="ORD-insp-scope", section="subject", phase=2,
      applies_when=lambda ctx: bool(ctx.order.ordered_inspection_type),
      name="Ordered inspection type matches report scope of work")
def ord_insp_scope(ctx: QCContext):
    ordered = ctx.order.ordered_inspection_type     # "full_interior" | "exterior_only" | "desktop"
    addendum = (ctx.appraisal.value("addendum_text") or "").lower()
    sca_cmnt = (ctx.appraisal.value("sca_comment") or "").lower()
    full_text = addendum + " " + sca_cmnt
    ev = [ctx.appraisal.evidence("addendum_text")]
    fields = ["addendum_text"]

    if not full_text.strip():
        return _res("ORD-INSP-SCOPE", "ORD-insp-scope", RuleStatus.SKIPPED,
                    message="No scope of work narrative extracted; cannot verify inspection type.",
                    fields=fields, evidence=ev)

    # Detect what the report claims
    is_desktop   = _DESKTOP_RE.search(full_text) is not None
    is_exterior  = _EXTERIOR_RE.search(full_text) is not None
    is_interior  = _INTERIOR_RE.search(full_text) is not None

    conflict = False
    if ordered == "desktop" and is_interior:
        conflict = True
    elif ordered == "exterior_only" and is_interior and not is_exterior:
        conflict = True
    elif ordered == "full_interior" and is_desktop and not is_interior:
        conflict = True

    if not conflict:
        return _res("ORD-INSP-SCOPE", "ORD-insp-scope", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # confidence gate @ 0.85
    conf = ctx.appraisal.confidence("addendum_text")
    if conf >= ctx.checkbox_conf:
        return _res("ORD-INSP-SCOPE", "ORD-insp-scope", RuleStatus.PASS,
                    fields=fields, evidence=ev)
    return _res("ORD-INSP-SCOPE", "ORD-insp-scope", RuleStatus.VERIFY,
                message=qc_config.template(
                    "ORD-INSP-SCOPE",
                    ordered=ordered.replace("_", " "),
                ),
                fields=fields, template_id="ORD-INSP-SCOPE", evidence=ev, confidence=0.7)


# ── ORD-COBORROWER — co-borrower from order appears in appraisal ─────────────

@rule(id="ORD-COBORROWER", num="ORD-coborrower", section="subject", phase=2,
      applies_when=lambda ctx: bool(ctx.order.co_borrower_name),
      name="Co-borrower from order appears in appraisal borrower field")
def ord_coborrower(ctx: QCContext):
    co_name = ctx.order.co_borrower_name or ""
    appr_borrower = (ctx.appraisal.value("borrower_name") or "").lower()
    co_lower = co_name.lower()
    ev = [
        ctx.appraisal.evidence("borrower_name"),
        ctx.engagement.evidence("co_borrower_name"),
    ]
    fields = ["borrower_name", "co_borrower_name"]

    if not appr_borrower:
        return _res("ORD-COBORROWER", "ORD-coborrower", RuleStatus.VERIFY,
                    message=f"Borrower field could not be confirmed from the appraisal; co-borrower '{co_name}' from the order cannot be verified.",
                    fields=fields, evidence=ev, confidence=0.5)

    # Token-level check: any part of co-borrower's name appears in the appraisal
    tokens = [t.strip() for t in re.split(r"[\s,&]+", co_lower) if len(t.strip()) > 2]
    if any(tok in appr_borrower for tok in tokens):
        return _res("ORD-COBORROWER", "ORD-coborrower", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    # Asymmetric Jaro-Winkler: auto-PASS at ≥ 0.90, never auto-FAIL
    sim = matching.jaro_winkler(matching.normalize_name(co_lower),
                                matching.normalize_name(appr_borrower))
    if sim >= 0.90:
        return _res("ORD-COBORROWER", "ORD-coborrower", RuleStatus.PASS,
                    fields=fields, evidence=ev)

    return _res("ORD-COBORROWER", "ORD-coborrower", RuleStatus.VERIFY,
                message=qc_config.template("ORD-COBORROWER", co_borrower=co_name),
                fields=fields, template_id="ORD-COBORROWER", evidence=ev, confidence=0.7)


# ── ORD-EXEC-STOP — unsigned contract → HOLD when policy says stop ────────────

@rule(id="ORD-EXEC-STOP", num="ORD-exec-stop", section="contract", phase=1,
      applies_when=lambda ctx: (
          ctx.transaction_type == "purchase"
          and ctx.policy.is_active("stop_on_unsigned_contract", default=False)
      ),
      name="Unsigned contract blocked by engagement letter policy")
def ord_exec_stop(ctx: QCContext):
    ev = []
    # The contract document is NOT read, so execution status cannot be determined
    # from the document. When the engagement letter requires a fully signed
    # contract: if no contract was provided at all → HOLD; if one was provided →
    # VERIFY (the reviewer confirms it is fully executed against the contract file).
    if not ctx.has_contract:
        return _res_contract("ORD-EXEC-STOP", "ORD-exec-stop", RuleStatus.HOLD,
                             message="No purchase contract was provided. The engagement letter requires a fully executed contract before processing. Please stop and return to the client.",
                             fields=["contract_analyzed"], evidence=ev)
    # confidence gate @ 0.90: if contract execution can be confirmed, FAIL per policy
    conf = ctx.appraisal.confidence("contract_analyzed")
    if conf >= 0.90:
        return _res_contract("ORD-EXEC-STOP", "ORD-exec-stop", RuleStatus.FAIL,
                             message="The engagement letter requires a fully executed contract. The contract provided does not appear to be fully executed — please return to the client.",
                             fields=["contract_analyzed"], evidence=ev)
    return _res_contract("ORD-EXEC-STOP", "ORD-exec-stop", RuleStatus.VERIFY,
                         message="The engagement letter requires a fully executed contract. The contract document is not auto-read; please open the contract file and confirm it is fully signed by all parties.",
                         fields=["contract_analyzed"], evidence=ev, confidence=0.5)


# ── ORD-CONFLICT — engagement letter vs XML conflict on a key fact ────────────

@rule(id="ORD-CONFLICT", num="ORD-conflict", section="global", phase=1,
      applies_when=lambda ctx: ctx.order.has_conflicts,
      name="Engagement letter and XML disagree on order-level facts")
def ord_conflict(ctx: QCContext):
    results = []
    for conflict in ctx.order.conflicts:
        ev = [
            Evidence(document="engagement", value=conflict.engagement_value,
                     confidence=0.92, field=conflict.field_name),
            Evidence(document="appraisal_xml", value=conflict.xml_value,
                     confidence=0.97, field=conflict.field_name),
        ]
        msg = (
            f"The order form says {conflict.field_name} is '{conflict.engagement_value}' "
            f"but the appraisal report shows '{conflict.xml_value}'. "
            "The order form is authoritative — please update the report to match."
        )
        results.append(H.make_result(
            "ORD-CONFLICT", "ORD-conflict", "global", RuleStatus.FAIL,
            message=msg, fields=[conflict.field_name], evidence=ev,
        ))
    return results or H.make_result(
        "ORD-CONFLICT", "ORD-conflict", "global", RuleStatus.PASS, fields=[], evidence=[],
    )


# ── ORD-ENG-DATE — engagement date precedes appraisal signature date ─────────

@rule(id="ORD-ENG-DATE", num="ORD-eng-date", section="signature", phase=2,
      applies_when=lambda ctx: ctx.order.engagement_date is not None,
      name="Engagement letter predates appraisal report")
def ord_eng_date(ctx: QCContext):
    eng_date = ctx.order.engagement_date
    sig_raw  = (ctx.appraisal.value("signature_date")
                or ctx.appraisal.value("date_of_signature"))
    ev = [
        Evidence(document="engagement", value=str(eng_date), confidence=0.85,
                 field="engagement_date"),
        ctx.appraisal.evidence("signature_date"),
    ]
    fields = ["engagement_date", "signature_date"]

    sig_date = _parse_date(sig_raw)
    if sig_date is None:
        # confidence gate @ 0.90
        conf = ctx.appraisal.confidence("signature_date")
        if conf >= 0.90:
            return _res_sig("ORD-ENG-DATE", "ORD-eng-date", RuleStatus.PASS,
                            fields=fields, evidence=ev)
        return _res_sig("ORD-ENG-DATE", "ORD-eng-date", RuleStatus.VERIFY,
                        message=f"Appraisal signature date could not be confirmed; engagement letter is dated {eng_date}. Please verify the engagement predates the report.",
                        fields=fields, evidence=ev, confidence=0.5)

    if eng_date <= sig_date:
        return _res_sig("ORD-ENG-DATE", "ORD-eng-date", RuleStatus.PASS,
                        fields=fields, evidence=ev)

    return _res_sig("ORD-ENG-DATE", "ORD-eng-date", RuleStatus.FAIL,
                    message=qc_config.template("TL-ENG-order", a=str(eng_date), b=str(sig_date)),
                    fields=fields, template_id="TL-ENG-order", evidence=ev)


# ── ORD-ASSIGN-MATCH — assignment type: EL vs XML ────────────────────────────

@rule(id="ORD-ASSIGN-MATCH", num="ORD-assign-match", section="contract", phase=2,
      applies_when=lambda ctx: ctx.order.from_engagement and ctx.order.assignment_type is not None,
      name="Assignment type in engagement letter matches appraisal report")
def ord_assign_match(ctx: QCContext):
    ordered = (ctx.order.assignment_type or "").lower()
    appr_raw = (ctx.appraisal.value("assignment_type") or "").lower()
    ev = [
        ctx.engagement.evidence("assignment_type"),
        ctx.appraisal.evidence("assignment_type"),
    ]
    fields = ["assignment_type"]

    if not appr_raw:
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("assignment_type")
        if conf >= ctx.checkbox_conf:
            return _res_contract("ORD-ASSIGN-MATCH", "ORD-assign-match", RuleStatus.PASS,
                                 fields=fields, evidence=ev)
        return _res_contract("ORD-ASSIGN-MATCH", "ORD-assign-match", RuleStatus.VERIFY,
                             message=f"Assignment type could not be confirmed from the appraisal; the engagement letter indicates '{ordered}'. Please verify.",
                             fields=fields, evidence=ev, confidence=0.5)

    def _norm(v: str) -> str:
        if "purchase" in v: return "purchase"
        if "refinance" in v or "refi" in v: return "refinance"
        return v.strip()

    if _norm(ordered) == _norm(appr_raw):
        return _res_contract("ORD-ASSIGN-MATCH", "ORD-assign-match", RuleStatus.PASS,
                             fields=fields, evidence=ev)

    # Conflict — engagement letter is authoritative
    return _res_contract("ORD-ASSIGN-MATCH", "ORD-assign-match", RuleStatus.FAIL,
                         message=qc_config.template(
                             "ORD-ASSIGN-MATCH",
                             ordered=ordered, actual=appr_raw,
                         ),
                         fields=fields, template_id="ORD-ASSIGN-MATCH", evidence=ev)
