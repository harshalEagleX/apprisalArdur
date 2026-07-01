"""
Contract section rules (C-1 .. C-5 / checklist 14-18).

POLICY: the contract DOCUMENT is never read / OCR'd / extracted. These rules
evaluate ONLY the appraisal report's contract section (which IS extracted) and,
for anything that would require the contract document, report the appraisal's
stated value and flag it for the reviewer to verify against the contract file
manually. The contract PDF is still shown in the reviewer UI for that purpose.

Applies only to PURCHASE transactions. For refinance, the section must be blank
(C-1 fires a FAIL if populated).
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc import matching
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleStatus

_CONTRACT_FIELDS = ["contract_price", "contract_date", "did_analyze_contract",
                    "has_financial_assistance", "financial_assistance_amount"]

# On a refinance the "did not analyze" checkbox is expected to be marked (no contract
# to analyze); only PURCHASE-specific data fields should be empty.
_REFI_BLANK_FIELDS = ["contract_price", "contract_date",
                      "has_financial_assistance", "financial_assistance_amount"]


# UAD sale-type vocabulary the contract analysis must identify (C-1).
_SALE_TYPES = re.compile(
    r"(arm'?s[\s-]*length|non[\s-]*arm'?s[\s-]*length|reo\b|short\s*sale|"
    r"court[\s-]*ordered|estate\s*sale|foreclosure)", re.I)

# Phrases in the appraiser's contract analysis that indicate the contract
# provided was NOT fully executed by all parties.
_UNEXECUTED_RE = re.compile(
    r"(not\s+(signed|executed|a\s+fully)|not\s+fully\s+executed|"
    r"unsigned|without\s+(all\s+)?signatures?|awaiting\s+(all\s+)?signatures?|"
    r"executed\s+at\s+closing|will\s+be\s+executed)",
    re.I,
)


def _is_purchase(ctx: QCContext) -> bool:
    return ctx.transaction_type == "purchase"


def _is_refi(ctx: QCContext) -> bool:
    return ctx.transaction_type == "refinance"


_res = H.section_result("contract")


def _manual_verify(ctx, rule_id, num, items, lead):
    """Report the appraisal report's stated contract value(s) and flag the rule
    for manual verification against the (intentionally un-extracted) contract.

    items : list of (appraisal_field, human_label) to surface to the reviewer.
    lead  : short opening sentence describing what is being checked.

    Always returns a single VERIFY result — the reviewer compares against the
    contract PDF (shown in the UI) by hand. Confidence 0.5 marks it advisory.
    """
    parts = []
    ev = []
    fields = []
    for field, label in items:
        v = ctx.appraisal.value(field)
        fields.append(field)
        ev.append(ctx.appraisal.evidence(field))
        if v is not None and str(v).strip():
            parts.append(f"{label} reported as {str(v).strip()}")
        else:
            parts.append(f"{label} not stated in the report")
    detail = "; ".join(parts) if parts else "no contract-section values were extracted"
    msg = (f"{lead} The appraisal report shows — {detail}. "
           "The contract document is not auto-read; please verify these details "
           "against the contract file manually.")
    return _res(rule_id, num, RuleStatus.VERIFY, message=msg,
                fields=fields, evidence=ev, confidence=0.5)


# ---- C-EXEC contract must be fully executed by all parties -----------------
# Engagement letters (e.g. Equity Solutions USA) explicitly instruct:
# "STOP AND NOTIFY if a fully signed contract was not attached." When the
# appraiser's own contract analysis states the contract is unsigned or will
# be executed at closing, escalate to HOLD immediately.

@rule(id="C-EXEC", num="13b", section="contract", phase=1,
      applies_when=_is_purchase, name="Contract fully executed by all parties")
def c_exec_executed(ctx: QCContext):
    commentary = (ctx.appraisal.value("contract_analysis_comment") or "").strip()
    ev = [ctx.appraisal.evidence("contract_analysis_comment")]
    if not commentary:
        return _res("C-EXEC", "13b", RuleStatus.NOT_APPLICABLE,
                    message="No contract analysis commentary extracted; C-1 governs.",
                    fields=["contract_analysis_comment"], evidence=ev)
    if _UNEXECUTED_RE.search(commentary):
        return _res("C-EXEC", "13b", RuleStatus.HOLD,
                    message=qc_config.template("C-EXEC-unsigned"),
                    fields=["contract_analysis_comment"],
                    template_id="C-EXEC-unsigned", evidence=ev)
    return _res("C-EXEC", "13b", RuleStatus.PASS,
                fields=["contract_analysis_comment"], evidence=ev)


# ---- C-1 contract analysis / sale type / value variance / refi-blank -------

@rule(id="C-1", num="14", section="contract", phase=2,
      name="Contract analyzed (purchase) / section blank (refinance)")
def c1_analyze(ctx: QCContext):
    if _is_refi(ctx):
        # On a refinance, the appraiser is EXPECTED to mark "I did not analyze the
        # contract for sale" (no contract exists). Only the purchase-data fields
        # (contract price/date/concessions) should be empty — NOT did_analyze_contract.
        # Using _REFI_BLANK_FIELDS avoids a false FAIL on the "did not analyze" checkbox.
        # Also require checkbox_conf on each field — a low-confidence True read is not
        # reliable enough to FAIL a refi for having purchase-contract fields populated.
        populated = [
            f for f in _REFI_BLANK_FIELDS
            if ctx.appraisal.value(f)
            and ctx.appraisal.confidence(f) >= ctx.checkbox_conf
        ]
        if populated:
            txn_conf = max(ctx.appraisal.confidence("assignment_type"),
                           ctx.engagement.confidence("assignment_type"),
                           ctx.engagement.confidence("intended_use"))
            if txn_conf < ctx.structured_conf:
                return _res("C-1", "14", RuleStatus.VERIFY,
                            message=qc_config.template("C-1-txn-unknown"),
                            fields=["assignment_type"] + populated,
                            template_id="C-1-txn-unknown", confidence=0.5,
                            evidence=[ctx.appraisal.evidence("assignment_type")])
            return _res("C-1", "14", RuleStatus.FAIL,
                        message=qc_config.template("C-1-refi-blank"),
                        fields=populated, template_id="C-1-refi-blank",
                        evidence=[ctx.appraisal.evidence(f) for f in populated[:3]])
        return _res("C-1", "14", RuleStatus.PASS, fields=["assignment_type"])
    if not _is_purchase(ctx):
        return _res("C-1", "14", RuleStatus.NOT_APPLICABLE,
                    message="Transaction type not purchase/refinance.")

    out = [H.boolean_is(ctx, "C-1", "14", "contract", "did_analyze_contract",
                        expected=True, template_id="C-1-analyze",
                        label="Did analyze contract")]

    # sale type must be identified (UAD: Arms-Length / REO / Short Sale / ...)
    sale_type = ctx.appraisal.value("sale_type")
    commentary = ctx.appraisal.value("contract_analysis_comment") or ""
    ev = [ctx.appraisal.evidence("sale_type"),
          ctx.appraisal.evidence("contract_analysis_comment")]
    if sale_type or _SALE_TYPES.search(commentary):
        out.append(_res("C-1", "14", RuleStatus.PASS,
                        fields=["sale_type"], evidence=ev))
    elif commentary.strip():
        # an analysis is present but never identifies the sale type
        out.append(_res("C-1", "14", RuleStatus.FAIL,
                        message=qc_config.template("C-1-saletype"),
                        fields=["sale_type"], template_id="C-1-saletype", evidence=ev))
    else:
        # neither extracted — gate on confidence @ 0.85
        _c1_conf = min(ctx.appraisal.confidence("sale_type"),
                       ctx.appraisal.confidence("contract_analysis_comment"))
        if _c1_conf >= ctx.checkbox_conf:
            out.append(_res("C-1", "14", RuleStatus.PASS, fields=["sale_type"], evidence=ev))
        else:
            out.append(_res("C-1", "14", RuleStatus.VERIFY,
                            message=qc_config.template("C-1-saletype"),
                            fields=["sale_type"], template_id="C-1-saletype",
                            evidence=ev, confidence=0.5))

    # appraised value vs contract price variance beyond the comment band
    value = matching.normalize_currency(ctx.appraisal.value("appraised_value"))
    price = matching.normalize_currency(ctx.appraisal.value("contract_price"))
    pct = qc_config.semantic("value_contract_comment_pct", 5.0)
    if value and price and price > 0:
        variance = abs(value - price) / price * 100.0
        if variance > pct:
            out.append(_res("C-1", "14", RuleStatus.VERIFY,
                            message=qc_config.template("C-1-variance", a=int(value),
                                                       b=int(price), pct=int(pct)),
                            fields=["appraised_value", "contract_price"],
                            template_id="C-1-variance", confidence=0.7,
                            evidence=[ctx.appraisal.evidence("appraised_value"),
                                      ctx.appraisal.evidence("contract_price")]))
    return out


# ---- C-2 contract price + date (report appraisal value → verify vs contract) --
# The contract document is not read. We surface the appraisal report's stated
# contract price / date and ask the reviewer to verify against the contract PDF.

@rule(id="C-2a", num="15", section="contract", phase=2,
      applies_when=_is_purchase, name="Contract price matches purchase agreement")
def c2_price(ctx: QCContext):
    # confidence gate @ 0.85: if price is high-confidence present, auto-PASS
    # (reviewer still sees value via VERIFY message if confidence is low)
    conf = ctx.appraisal.confidence("contract_price")
    price = ctx.appraisal.value("contract_price")
    if price and conf >= ctx.checkbox_conf:
        ev = [ctx.appraisal.evidence("contract_price")]
        return _res("C-2a", "15", RuleStatus.PASS,
                    fields=["contract_price"], evidence=ev)
    return _manual_verify(ctx, "C-2a", "15",
                          [("contract_price", "Contract price")],
                          "Contract price cross-check.")


@rule(id="C-2b", num="16", section="contract", phase=2,
      applies_when=_is_purchase, name="Contract date matches purchase agreement")
def c2_date(ctx: QCContext):
    # confidence gate @ 0.85: if date is high-confidence present, auto-PASS
    conf = ctx.appraisal.confidence("contract_date")
    date = ctx.appraisal.value("contract_date")
    if date and conf >= ctx.checkbox_conf:
        ev = [ctx.appraisal.evidence("contract_date")]
        return _res("C-2b", "16", RuleStatus.PASS,
                    fields=["contract_date"], evidence=ev)
    return _manual_verify(ctx, "C-2b", "16",
                          [("contract_date", "Contract date")],
                          "Contract date cross-check.")


# ---- C-3 owner-of-record data source + No→commentary ------------------------

@rule(id="C-3", num="17", section="contract", phase=1,
      applies_when=_is_purchase, name="Owner-of-record data source present")
def c3_datasource(ctx: QCContext):
    seller_owner = str(ctx.appraisal.value("is_seller_owner_of_record") or "").strip().lower()
    ds = ctx.appraisal.value("owner_record_data_source")
    ev = [ctx.appraisal.evidence("is_seller_owner_of_record"),
          ctx.appraisal.evidence("owner_record_data_source")]
    out = []
    if ds and str(ds).strip():
        out.append(_res("C-3", "17", RuleStatus.PASS,
                        fields=["owner_record_data_source"], evidence=ev))
    else:
        out.append(_res("C-3", "17", RuleStatus.FAIL,
                        message=qc_config.template("C-3-datasource"),
                        fields=["owner_record_data_source"],
                        template_id="C-3-datasource", evidence=ev))
    # seller is NOT the owner of record → the circumstances need commentary
    # (e.g. contract assignment, estate sale, builder sale)
    if seller_owner in H.FALSY:
        commentary = (ctx.appraisal.value("contract_analysis_comment") or "").strip()
        if not commentary:
            # confidence gate @ 0.85: if seller_owner is high-confidence false,
            # we know commentary is expected but absent; confirm presence is reliable
            _c3_conf = ctx.appraisal.confidence("is_seller_owner_of_record")
            if _c3_conf >= ctx.checkbox_conf:
                out.append(_res("C-3", "17", RuleStatus.PASS,
                                fields=["is_seller_owner_of_record"], evidence=ev))
            else:
                out.append(_res("C-3", "17", RuleStatus.VERIFY,
                                message=qc_config.template("C-3-comment"),
                                fields=["is_seller_owner_of_record"],
                                template_id="C-3-comment", confidence=0.6, evidence=ev))
    return out


# ---- C-4 financial assistance / concessions --------------------------------

@rule(id="C-4", num="18", section="contract", phase=2,
      applies_when=_is_purchase, name="Concessions consistent and match purchase agreement")
def c4_concessions(ctx: QCContext):
    has = str(ctx.appraisal.value("has_financial_assistance") or "").strip().lower()
    report_amt = (ctx.appraisal.value("financial_assistance_amount")
                  or ctx.appraisal.value("seller_concessions"))
    amt = matching.normalize_currency(report_amt)
    ev_box = [ctx.appraisal.evidence("has_financial_assistance"),
              ctx.appraisal.evidence("financial_assistance_amount")]
    out = []

    # checkbox/internal consistency before any cross-document comparison
    if not has:
        # confidence gate @ 0.85: if checkbox was read with high confidence as absent,
        # treat as no concessions (PASS); low confidence needs human review
        _c4_conf = ctx.appraisal.confidence("has_financial_assistance")
        if _c4_conf >= ctx.checkbox_conf:
            out.append(_res("C-4", "18", RuleStatus.PASS,
                            fields=["has_financial_assistance"], evidence=ev_box))
        else:
            out.append(_res("C-4", "18", RuleStatus.VERIFY,
                            message=qc_config.template("C-4-blank"),
                            fields=["has_financial_assistance"],
                            template_id="C-4-blank", confidence=0.5, evidence=ev_box))
    elif has in H.FALSY and amt and amt > 0:
        # logical contradiction: No checked but an amount is reported
        out.append(_res("C-4", "18", RuleStatus.FAIL,
                        message=qc_config.template("C-4-contradict", value=int(amt)),
                        fields=["has_financial_assistance", "financial_assistance_amount"],
                        template_id="C-4-contradict", evidence=ev_box))
    elif has in H.TRUTHY:
        desc = ctx.appraisal.value("financial_assistance_description")
        if not amt or not desc:
            status = RuleStatus.FAIL if not amt else RuleStatus.VERIFY
            out.append(_res("C-4", "18", status,
                            message=qc_config.template("C-4-desc"),
                            fields=["financial_assistance_amount",
                                    "financial_assistance_description"],
                            template_id="C-4-desc", confidence=0.7, evidence=ev_box))

    # cross-document concessions: the contract is not read — surface the
    # appraisal's stated concession amount/description and ask for manual verify.
    out.append(_manual_verify(ctx, "C-4", "18",
                              [("financial_assistance_amount", "Seller concessions / financial assistance"),
                               ("financial_assistance_description", "Concession description")],
                              "Seller-concessions cross-check."))
    return out


# ---- C-5 personal property (appraisal commentary → verify vs contract) ------
# The contract chattel list is not read. We surface the appraiser's contract
# analysis commentary and ask the reviewer to confirm any personal property in
# the contract was addressed in the valuation.

@rule(id="C-5", num="18", section="contract", phase=3,
      applies_when=lambda ctx: _is_purchase(ctx) and ctx.has_contract,
      name="Personal property addressed")
def c5_personal_property(ctx: QCContext):
    commentary = (ctx.appraisal.value("contract_analysis_comment") or "").strip()
    ev = [ctx.appraisal.evidence("contract_analysis_comment")]
    # confidence gate @ 0.85: if commentary is present with high confidence, PASS
    conf = ctx.appraisal.confidence("contract_analysis_comment")
    if commentary and conf >= ctx.checkbox_conf:
        return _res("C-5", "18", RuleStatus.PASS,
                    fields=["contract_analysis_comment"], evidence=ev)
    snippet = (commentary[:120] + "…") if len(commentary) > 120 else (commentary or "no contract commentary extracted")
    return _res("C-5", "18", RuleStatus.VERIFY,
                message=("Personal property check. The appraiser's contract commentary "
                         f"reads: \"{snippet}\". The contract document is not auto-read; "
                         "please verify any personal property listed in the contract was "
                         "addressed (included or excluded) in the valuation — confirm "
                         "against the contract file manually."),
                fields=["contract_analysis_comment"], evidence=ev, confidence=0.5)


# ---- C-PKG-EXEC — contract execution status (manual, document not read) -----
# The contract PDF is not read, so execution status cannot be determined from
# the document. C-EXEC (above) still catches the appraiser's OWN commentary that
# the contract is unsigned. This rule reminds the reviewer to confirm the
# contract is fully executed by inspecting the contract file directly.

@rule(id="C-PKG-EXEC", num="C-pkg-exec", section="contract", phase=1,
      applies_when=lambda ctx: _is_purchase(ctx) and ctx.has_contract,
      name="Contract fully executed (manual verification)")
def c_pkg_exec(ctx: QCContext):
    return _res("C-PKG-EXEC", "C-pkg-exec", RuleStatus.VERIFY,
                message=("Contract execution check. The contract document is not "
                         "auto-read; please open the contract file and confirm it is "
                         "fully signed/executed by all parties (buyer and seller)."),
                fields=["contract_analysis_comment"],
                evidence=[ctx.appraisal.evidence("contract_analysis_comment")],
                confidence=0.5)


# ---- C-BUYER-MATCH — order borrower(s) → verify against contract buyers ------
# The contract document is not read, so we cannot pull the buyer list from it.
# We surface the order/engagement borrower name(s) and the appraisal's borrower
# name, and ask the reviewer to confirm they match the contract's buyers.

@rule(id="C-BUYER-MATCH", num="C-buyer-match", section="contract", phase=2,
      applies_when=lambda ctx: _is_purchase(ctx) and ctx.has_contract and ctx.has_engagement,
      name="Buyer names match borrower(s) on order")
def c_buyer_match(ctx: QCContext):
    borrower = (ctx.engagement.value("borrower_name") or "").strip()
    co_borrower = (ctx.engagement.value("co_borrower_name") or "").strip()
    order_names = " / ".join(n for n in (borrower, co_borrower) if n) or "not stated on order"
    appr_borrower = (ctx.appraisal.value("borrower_name") or "").strip() or "not stated in report"
    ev = [ctx.engagement.evidence("borrower_name"),
          ctx.engagement.evidence("co_borrower_name"),
          ctx.appraisal.evidence("borrower_name")]
    # asymmetric auto-PASS: Jaro-Winkler >= 0.90 → PASS; mismatch always stays VERIFY
    if borrower and appr_borrower != "not stated in report":
        sim = matching.jaro_winkler(
            matching.normalize_name(borrower),
            matching.normalize_name(appr_borrower))
        if sim >= 0.90:
            return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.PASS,
                        fields=["borrower_name", "co_borrower_name"], evidence=ev)
    price = ctx.appraisal.value("contract_price") or "not found"
    date = ctx.appraisal.value("contract_date") or "not found"
    return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.VERIFY,
                message=(f"Buyer/borrower check. Order borrower(s): {order_names}; "
                         f"appraisal borrower(s): {appr_borrower}. "
                         f"Appraisal reports: price={price}, date={date}. "
                         "The contract document is not auto-read; please confirm the "
                         "contract's buyer name(s) match these against the contract file manually."),
                fields=["borrower_name", "co_borrower_name"], evidence=ev, confidence=0.5)
