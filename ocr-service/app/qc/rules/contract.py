"""
Contract section rules (C-1 .. C-4 / checklist 14-18).

Applies only to PURCHASE transactions. For refinance, the section must be blank
(C-1 fires a FAIL if populated). Contract price/date/concessions are matched
against the sales contract document.
"""

from __future__ import annotations

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_CONTRACT_FIELDS = ["contract_price", "contract_date", "did_analyze_contract",
                    "has_financial_assistance", "financial_assistance_amount"]


def _is_purchase(ctx: QCContext) -> bool:
    return ctx.transaction_type == "purchase"


def _is_refi(ctx: QCContext) -> bool:
    return ctx.transaction_type == "refinance"


# ---- C-1 contract analysis / refinance-must-be-blank ----------------------

@rule(id="C-1", num="14", section="contract", phase=2,
      name="Contract section blank on refinance / analyzed on purchase")
def c1_analyze(ctx: QCContext):
    if _is_refi(ctx):
        populated = [f for f in _CONTRACT_FIELDS if ctx.appraisal.value(f)]
        if populated:
            return RuleResult(rule_id="C-1", checklist_num="14", section="contract",
                              status=RuleStatus.FAIL,
                              message=qc_config.template("C-1-refi-blank"),
                              fields_involved=populated, template_id="C-1-refi-blank",
                              evidence=[ctx.appraisal.evidence(f) for f in populated[:3]])
        return RuleResult(rule_id="C-1", checklist_num="14", section="contract",
                          status=RuleStatus.PASS, fields_involved=["assignment_type"])
    if _is_purchase(ctx):
        # contract must be analyzed
        return H.boolean_is(ctx, "C-1", "14", "contract", "did_analyze_contract",
                            expected=True, template_id="C-1-refi-blank", label="Did analyze contract")
    return RuleResult(rule_id="C-1", checklist_num="14", section="contract",
                      status=RuleStatus.NOT_APPLICABLE,
                      message="Transaction type not purchase/refinance.")


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
    return H.cross_doc_match(ctx, "C-2b", "16", "contract", "contract_date", "C-2-date",
                             authority=auth, kind="generic", label="contract date")


# ---- C-3 owner-of-record data source --------------------------------------

@rule(id="C-3", num="17", section="contract", phase=1,
      applies_when=_is_purchase, name="Owner-of-record data source present")
def c3_datasource(ctx: QCContext):
    seller_owner = ctx.appraisal.value("is_seller_owner_of_record")
    ds = ctx.appraisal.value("owner_record_data_source")
    ev = [ctx.appraisal.evidence("is_seller_owner_of_record"),
          ctx.appraisal.evidence("owner_record_data_source")]
    if ds and str(ds).strip():
        return RuleResult(rule_id="C-3", checklist_num="17", section="contract",
                          status=RuleStatus.PASS, fields_involved=["owner_record_data_source"], evidence=ev)
    return RuleResult(rule_id="C-3", checklist_num="17", section="contract",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("C-3-datasource"),
                      fields_involved=["owner_record_data_source"],
                      template_id="C-3-datasource", evidence=ev)


# ---- C-4 financial assistance / concessions (cross-document) --------------

@rule(id="C-4", num="18", section="contract", phase=2,
      applies_when=_is_purchase, name="Concessions match purchase agreement")
def c4_concessions(ctx: QCContext):
    report_amt = ctx.appraisal.value("financial_assistance_amount") or ctx.appraisal.value("seller_concessions")
    contract_amt = ctx.contract.value("concessions_amount")
    ev = [ctx.appraisal.evidence("financial_assistance_amount"),
          ctx.contract.evidence("concessions_amount")]
    if contract_amt is None:
        return RuleResult(rule_id="C-4", checklist_num="18", section="contract",
                          status=RuleStatus.SKIPPED, message="concession not extracted from contract",
                          fields_involved=["concessions_amount"], evidence=ev)
    from app.qc import matching
    mr = matching.match_currency(report_amt, contract_amt)
    if mr.verdict == "match":
        return RuleResult(rule_id="C-4", checklist_num="18", section="contract",
                          status=RuleStatus.PASS, fields_involved=["financial_assistance_amount"], evidence=ev)
    return RuleResult(rule_id="C-4", checklist_num="18", section="contract",
                      status=RuleStatus.VERIFY,
                      message=qc_config.template("C-4-concession", a=report_amt or "0", b=contract_amt),
                      fields_involved=["financial_assistance_amount", "concessions_amount"],
                      template_id="C-4-concession", evidence=ev, confidence=0.6)
