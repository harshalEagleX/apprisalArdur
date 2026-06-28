"""
Contract section rules (C-1 .. C-5 / checklist 14-18).

Applies only to PURCHASE transactions. For refinance, the section must be blank
(C-1 fires a FAIL if populated). Contract price/date/concessions are matched
against the sales contract document; the personal-property check (C-5) pairs the
contract's chattel scan with an LLM read of the appraiser's commentary.
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
        populated = [f for f in _REFI_BLANK_FIELDS if ctx.appraisal.value(f)]
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
        # neither extracted — extraction gap, a reviewer confirms
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


# ---- C-2 contract price + date (cross-document vs contract) ---------------

@rule(id="C-2a", num="15", section="contract", phase=2,
      applies_when=_is_purchase, name="Contract price matches purchase agreement")
def c2_price(ctx: QCContext):
    if not ctx.has_contract:
        # compare appraisal vs engagement contract_price as fallback authority
        return H.cross_doc_match(ctx, "C-2a", "15", "contract", "contract_price", "C-2-price",
                                 authority="engagement", kind="currency", label="contract price")
    return H.cross_doc_match(ctx, "C-2a", "15", "contract", "contract_price", "C-2-price",
                             authority="contract", kind="currency", label="contract price")


@rule(id="C-2b", num="16", section="contract", phase=2,
      applies_when=_is_purchase, name="Contract date matches purchase agreement")
def c2_date(ctx: QCContext):
    auth = "contract" if ctx.has_contract else "engagement"
    # dates are identifiers: exact-day equality, never fuzzy string similarity
    # (Jaro-Winkler would call 04/27/2026 vs 04/29/2026 a match)
    return H.cross_doc_match(ctx, "C-2b", "16", "contract", "contract_date", "C-2-date",
                             authority=auth, kind="date", label="contract date")


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

    # cross-document: report amount vs purchase-agreement amount
    contract_amt = ctx.contract.value("concessions_amount")
    ev = [ctx.appraisal.evidence("financial_assistance_amount"),
          ctx.contract.evidence("concessions_amount")]
    if not ctx.has_contract:
        out.append(_res("C-4", "18", RuleStatus.VERIFY,
                        message="The purchase contract was not provided; please verify the "
                                "reported concessions against the agreement manually.",
                        fields=["concessions_amount"], evidence=ev, confidence=0.5))
        return out
    if contract_amt is None:
        # nothing labelled a concession in the contract; only flag when the
        # report claims one
        if amt and amt > 0:
            out.append(_res("C-4", "18", RuleStatus.VERIFY,
                            message="The concession amount could not be read from the contract; please verify it matches the appraisal.",
                            fields=["concessions_amount"], evidence=ev, confidence=0.5))
        else:
            out.append(_res("C-4", "18", RuleStatus.PASS,
                            fields=["financial_assistance_amount"], evidence=ev))
        return out
    mr = matching.match_currency(report_amt, contract_amt)
    if mr.verdict == "match":
        out.append(_res("C-4", "18", RuleStatus.PASS,
                        fields=["financial_assistance_amount"], evidence=ev))
    else:
        out.append(_res("C-4", "18", RuleStatus.VERIFY,
                        message=qc_config.template("C-4-concession",
                                                   a=report_amt or "0", b=contract_amt),
                        fields=["financial_assistance_amount", "concessions_amount"],
                        template_id="C-4-concession", evidence=ev, confidence=0.6))
    return out


# ---- C-5 personal property (contract chattel → commentary required) --------

@rule(id="C-5", num="18", section="contract", phase=3,
      applies_when=_is_purchase, name="Personal property addressed")
def c5_personal_property(ctx: QCContext):
    items = (ctx.contract.value("personal_property_items") or "").strip()
    if not ctx.has_contract or not items:
        return _res("C-5", "18", RuleStatus.NOT_APPLICABLE,
                    message="No personal property identified in the purchase contract.")
    commentary = (ctx.appraisal.value("contract_analysis_comment") or "").strip()
    ev = [ctx.contract.evidence("personal_property_items"),
          ctx.appraisal.evidence("contract_analysis_comment")]
    if commentary:
        addressed = None
        try:
            from app.extraction.llm_groq import assess_text
            addressed = assess_text(
                commentary,
                "Does this appraisal contract-analysis commentary address whether the "
                f"personal property items in the sale ({items}) contribute to or were "
                "excluded from the appraised value?",
            )
        except Exception:
            addressed = None
        if addressed:
            return _res("C-5", "18", RuleStatus.PASS,
                        fields=["personal_property_items"], evidence=ev)
        return _res("C-5", "18", RuleStatus.VERIFY,
                    message=qc_config.template("C-5-personal", value=items),
                    fields=["personal_property_items", "contract_analysis_comment"],
                    template_id="C-5-personal", confidence=0.6, evidence=ev)
    # no commentary extracted at all → reviewer confirms (an extraction gap is
    # indistinguishable from genuinely missing commentary)
    return _res("C-5", "18", RuleStatus.VERIFY,
                message=qc_config.template("C-5-personal", value=items),
                fields=["personal_property_items"], template_id="C-5-personal",
                confidence=0.5, evidence=ev)


# ---- C-PKG-UNEXEC — document-level execution status from ContractPackage ----
# C-EXEC (above) checks the appraiser's OWN written commentary about execution
# status.  C-PKG-UNEXEC is a complementary, independent check that reads the
# execution signals from the contract PDF itself via ContractPackage, so both
# the appraiser's claim AND the document evidence are evaluated.

@rule(id="C-PKG-UNEXEC", num="C-pkg-unexec", section="contract", phase=1,
      applies_when=_is_purchase, name="Contract package execution status (document-level)")
def c_pkg_unexec(ctx: QCContext):
    # Require a contract document to be present and parsed.
    if not ctx.has_contract:
        return _res("C-PKG-UNEXEC", "C-pkg-unexec", RuleStatus.NOT_APPLICABLE,
                    message="No purchase contract document provided; document-level "
                            "execution check cannot run.")

    # Read the ContractPackage attached by the transaction runner (Task 5).
    pkg = getattr(ctx, "contract_package", None)
    if pkg is None:
        # Package was not built (extraction failure, old code path, or test) —
        # gracefully skip rather than crash; C-EXEC still covers commentary.
        return _res("C-PKG-UNEXEC", "C-pkg-unexec", RuleStatus.SKIPPED,
                    message="ContractPackage not available for this transaction; "
                            "document-level execution check skipped.",
                    fields=["contract_package"])

    ev = [ctx.contract.evidence("buyer_names"),
          ctx.contract.evidence("concessions_amount")]

    if not pkg.documents:
        return _res("C-PKG-UNEXEC", "C-pkg-unexec", RuleStatus.SKIPPED,
                    message="ContractPackage has no documents; document-level "
                            "execution check skipped.",
                    evidence=ev)

    if pkg.resolved_execution_status:
        return _res("C-PKG-UNEXEC", "C-pkg-unexec", RuleStatus.PASS,
                    message="The contract document(s) appear to be fully executed.",
                    evidence=ev)

    return _res("C-PKG-UNEXEC", "C-pkg-unexec", RuleStatus.HOLD,
                message=qc_config.template("C-EXEC-unsigned"),
                fields=["contract_package"],
                template_id="C-EXEC-unsigned", evidence=ev)


# ---- C-BUYER-MATCH — buyer names on contract vs borrower on engagement ------
# When both documents are available, verify that every borrower named on the
# engagement letter (order form) appears somewhere in the contract buyer list.
# A mismatch does not automatically fail — the order may be in the buyer's
# entity name, the buyer may be an LLC, or there may be a legitimate co-buyer
# not yet on the order.  VERIFY surfaces it for human judgment.

@rule(id="C-BUYER-MATCH", num="C-buyer-match", section="contract", phase=2,
      applies_when=lambda ctx: _is_purchase(ctx) and ctx.has_contract and ctx.has_engagement,
      name="Buyer names on contract match borrower(s) on engagement")
def c_buyer_match(ctx: QCContext):
    # Collect buyer name string from the contract extractor.
    contract_buyers_raw = (ctx.contract.value("buyer_names") or "").strip()
    ev = [ctx.contract.evidence("buyer_names"),
          ctx.engagement.evidence("borrower_name"),
          ctx.engagement.evidence("co_borrower_name")]

    if not contract_buyers_raw:
        # Extraction did not find buyer names — cannot compare; skip silently.
        return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.SKIPPED,
                    message="Buyer name(s) could not be extracted from the contract; "
                            "borrower-name comparison skipped.",
                    fields=["buyer_names"], evidence=ev)

    # Collect borrower names from the engagement letter.
    borrower = (ctx.engagement.value("borrower_name") or "").strip()
    co_borrower = (ctx.engagement.value("co_borrower_name") or "").strip()
    order_names = [n for n in (borrower, co_borrower) if n]

    if not order_names:
        return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.SKIPPED,
                    message="Borrower name(s) could not be extracted from the engagement "
                            "letter; borrower-name comparison skipped.",
                    fields=["borrower_name"], evidence=ev)

    # Fuzzy token match: every engagement borrower name token should appear in
    # the contract buyer string.  We compare lowercase token sets so "John A.
    # Smith" matches "JOHN SMITH" — middle initials are ignored when absent.
    contract_buyers_lower = contract_buyers_raw.lower()

    def _name_present(name: str) -> bool:
        """True if all significant tokens of `name` appear in the buyer string."""
        tokens = [t for t in re.split(r"[\s,&.]+", name.lower()) if len(t) > 1]
        return all(tok in contract_buyers_lower for tok in tokens)

    mismatched = [n for n in order_names if not _name_present(n)]

    if not mismatched:
        return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.PASS,
                    fields=["buyer_names", "borrower_name"], evidence=ev)

    order_label = " / ".join(order_names)
    return _res("C-BUYER-MATCH", "C-buyer-match", RuleStatus.VERIFY,
                message=qc_config.template(
                    "C-BUYER-MATCH",
                    contract_buyers=contract_buyers_raw,
                    order_borrowers=order_label,
                ),
                fields=["buyer_names", "borrower_name"],
                template_id="C-BUYER-MATCH", evidence=ev, confidence=0.7)
