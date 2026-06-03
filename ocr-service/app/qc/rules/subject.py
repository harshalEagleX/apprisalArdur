"""
Subject section rules (S-1 .. S-12 / checklist C,D,E,F,1-13).

Phase 1 (presence/format) and Phase 2 (cross-document match vs engagement
letter). Authority for address/borrower/lender is the engagement letter.
"""

from __future__ import annotations

from app.qc import helpers as H
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus


# ---- S-1 Property address (cross-document, 4 components) -------------------

@rule(id="S-1", num="C", section="subject", phase=2, name="Property address matches order form")
def s1_address(ctx: QCContext):
    out = [
        H.cross_doc_match(ctx, "S-1", "C", "subject", "property_address", "S-1-address",
                          authority="engagement", kind="address", label="address"),
        H.cross_doc_match(ctx, "S-1", "C", "subject", "city", "S-1-city",
                          authority="engagement", kind="generic", label="city"),
        H.cross_doc_match(ctx, "S-1", "C", "subject", "zip_code", "S-1-zip",
                          authority="engagement", kind="generic", label="zip"),
    ]
    # county is optional but checked when present on both
    if ctx.engagement.value("county") and ctx.appraisal.value("county"):
        out.append(H.cross_doc_match(ctx, "S-1", "C", "subject", "county", "S-1-county",
                                     authority="engagement", kind="generic", label="county"))
    return out


# ---- S-2 Borrower (cross-document + co-borrower + refi/owner) --------------

@rule(id="S-2", num="D", section="subject", phase=2, name="Borrower matches order form")
def s2_borrower(ctx: QCContext):
    out = [H.cross_doc_match(ctx, "S-2", "D", "subject", "borrower_name", "S-2-coborrower",
                             authority="engagement", kind="name", label="borrower")]
    # co-borrower present on engagement/contract but missing on appraisal
    co = ctx.engagement.value("co_borrower_name") or ctx.contract.value("co_borrower_name")
    appr_borrower = (ctx.appraisal.value("borrower_name") or "").lower()
    if co and co.lower() not in appr_borrower:
        out.append(RuleResult(
            rule_id="S-2", checklist_num="D", section="subject",
            status=RuleStatus.VERIFY,
            message=qc_config.template("S-2-coborrower", value=co),
            fields_involved=["co_borrower_name"], template_id="S-2-coborrower",
            confidence=0.6,
            evidence=[ctx.appraisal.evidence("borrower_name"),
                      ctx.engagement.evidence("co_borrower_name")],
        ))
    # refinance + owner != borrower → comment required (VERIFY)
    if ctx.transaction_type == "refinance":
        owner = ctx.appraisal.value("owner_of_public_record")
        borrower = ctx.appraisal.value("borrower_name")
        if owner and borrower:
            from app.qc import matching
            mr = matching.match_text(owner, borrower, kind="name")
            if mr.verdict == "mismatch":
                out.append(RuleResult(
                    rule_id="S-2", checklist_num="1", section="subject",
                    status=RuleStatus.VERIFY,
                    message=qc_config.template("S-2-refi-owner"),
                    fields_involved=["owner_of_public_record", "borrower_name"],
                    template_id="S-2-refi-owner", confidence=0.7,
                    evidence=[ctx.appraisal.evidence("owner_of_public_record"),
                              ctx.appraisal.evidence("borrower_name")],
                ))
    return out


# ---- S-3/S-4 presence (Phase 1) -------------------------------------------

@rule(id="S-3", num="1", section="subject", phase=1, name="Owner of public record present")
def s3_owner(ctx):
    return H.present(ctx, "S-3", "1", "subject", "owner_of_public_record", label="Owner of Public Record")


@rule(id="S-4a", num="2", section="subject", phase=1, name="Legal description present")
def s4_legal(ctx):
    return H.present(ctx, "S-4a", "2", "subject", "legal_description", label="Legal Description")


@rule(id="S-4b", num="3", section="subject", phase=1, name="APN present")
def s4_apn(ctx):
    return H.present(ctx, "S-4b", "3", "subject", "assessors_parcel_number", label="Assessor's Parcel #")


@rule(id="S-4c", num="5", section="subject", phase=1, name="R.E. taxes no decimals")
def s4_taxes(ctx):
    # presence + no-decimal format
    val = ctx.appraisal.value("real_estate_taxes")
    if not val:
        return H.present(ctx, "S-4c", "5", "subject", "real_estate_taxes", label="R.E. Taxes")
    if "." in str(val):
        return H.format_regex(ctx, "S-4c", "5", "subject", "real_estate_taxes",
                              r"^\D*\d{1,3}(,?\d{3})*\D*$", "S-4-taxdecimal", label="R.E. Taxes")
    return H.present(ctx, "S-4c", "5", "subject", "real_estate_taxes", label="R.E. Taxes")


# ---- S-5 Neighborhood name (not blank / not N/A) --------------------------

@rule(id="S-5", num="6", section="subject", phase=1, name="Neighborhood name valid")
def s5_neighborhood(ctx):
    val = (ctx.appraisal.value("neighborhood_name") or "").strip()
    ev = [ctx.appraisal.evidence("neighborhood_name")]
    bad = {"", "n/a", "na", "none", "unknown"}
    if val.lower() in bad:
        return RuleResult(rule_id="S-5", checklist_num="6", section="subject",
                          status=RuleStatus.FAIL,
                          message=qc_config.template("S-5-neighborhood"),
                          fields_involved=["neighborhood_name"], template_id="S-5-neighborhood",
                          evidence=ev)
    return RuleResult(rule_id="S-5", checklist_num="6", section="subject",
                      status=RuleStatus.PASS, fields_involved=["neighborhood_name"], evidence=ev)


# ---- S-6 Census tract format (XXXX.XX) ------------------------------------

@rule(id="S-6", num="8", section="subject", phase=1, name="Census tract format")
def s6_census(ctx):
    return H.format_regex(ctx, "S-6", "8", "subject", "census_tract",
                          r"\d{3,4}\.\d{2}", "S-6-census", label="Census Tract")


# ---- S-8 Special assessments (blank not allowed; 0 if none) ----------------

@rule(id="S-8", num="10", section="subject", phase=1, name="Special assessments not blank")
def s8_assessment(ctx):
    return H.present(ctx, "S-8", "10", "subject", "special_assessments", label="Special Assessments")


# ---- S-9 PUD/HOA (HOA dues > 0 ⇒ PUD must be marked) ----------------------

@rule(id="S-9", num="11", section="subject", phase=3, name="HOA dues imply PUD marked")
def s9_pud(ctx):
    hoa = ctx.appraisal.value("hoa_dues")
    from app.qc import matching
    amt = matching.normalize_currency(hoa)
    ev = [ctx.appraisal.evidence("hoa_dues"), ctx.appraisal.evidence("is_pud_checked")]
    if not amt or amt <= 0:
        return RuleResult(rule_id="S-9", checklist_num="11", section="subject",
                          status=RuleStatus.PASS, fields_involved=["hoa_dues"], evidence=ev)
    pud = str(ctx.appraisal.value("is_pud_checked") or "").lower() in {"true", "yes", "1", "x"}
    if pud:
        return RuleResult(rule_id="S-9", checklist_num="11", section="subject",
                          status=RuleStatus.PASS, fields_involved=["hoa_dues", "is_pud_checked"], evidence=ev)
    status = RuleStatus.VERIFY if ctx.appraisal.confidence("is_pud_checked") < ctx.checkbox_conf else RuleStatus.FAIL
    return RuleResult(rule_id="S-9", checklist_num="11", section="subject",
                      status=status,
                      message=qc_config.template("S-9-pud", value=int(amt)),
                      fields_involved=["hoa_dues", "is_pud_checked"],
                      template_id="S-9-pud", evidence=ev, confidence=0.7)


# ---- S-10 Lender/client name + address (cross-document) -------------------

@rule(id="S-10a", num="E", section="subject", phase=2, name="Lender name matches order form")
def s10_lender_name(ctx):
    return H.cross_doc_match(ctx, "S-10a", "E", "subject", "lender_name", "S-10-lender",
                             authority="engagement", kind="generic", label="lender name")


@rule(id="S-10b", num="F", section="subject", phase=2, name="Lender address matches order form")
def s10_lender_addr(ctx):
    if not ctx.engagement.value("lender_address"):
        return RuleResult(rule_id="S-10b", checklist_num="F", section="subject",
                          status=RuleStatus.SKIPPED, message="lender address not on engagement")
    return H.cross_doc_match(ctx, "S-10b", "F", "subject", "lender_address", "S-10-lender-addr",
                             authority="engagement", kind="address", label="lender address")


# ---- S-12 Prior listing data source (when offered=No, data source required) --

@rule(id="S-12", num="13", section="subject", phase=1, name="Prior-listing data source present")
def s12_datasource(ctx):
    offered = str(ctx.appraisal.value("offered_for_sale_12mo") or "").lower()
    ev = [ctx.appraisal.evidence("offered_for_sale_12mo"), ctx.appraisal.evidence("data_source")]
    ds = ctx.appraisal.value("data_source")
    if ds and str(ds).strip():
        return RuleResult(rule_id="S-12", checklist_num="13", section="subject",
                          status=RuleStatus.PASS, fields_involved=["data_source"], evidence=ev)
    return RuleResult(rule_id="S-12", checklist_num="13", section="subject",
                      status=RuleStatus.FAIL,
                      message=qc_config.template("S-12-datasource"),
                      fields_involved=["data_source"], template_id="S-12-datasource", evidence=ev)
