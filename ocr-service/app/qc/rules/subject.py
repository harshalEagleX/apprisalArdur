"""
Subject section rules (S-1 .. S-12 / checklist C,D,E,F,1-13).

Phase 1 (presence/format/content) and Phase 2 (cross-document match vs the
engagement letter — the authority for address/borrower/lender). Address and
borrower comparisons are component/token level, never whole-string equality.
USPS address verification is intentionally NOT used.
"""

from __future__ import annotations

import re

from app.qc import helpers as H
from app.qc import matching
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleStatus


_res = H.section_result("subject")


# ---- S-1 Property address (cross-document, 5 components) -------------------

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
    # state: exact two-letter code match (full names normalized to codes first)
    a_state, e_state = ctx.appraisal.value("state"), ctx.engagement.value("state")
    if ctx.has_engagement and a_state and e_state:
        na, ne = matching.normalize_state(a_state), matching.normalize_state(e_state)
        ev = [ctx.appraisal.evidence("state"), ctx.engagement.evidence("state")]
        if na and ne:
            ok = na == ne
            status = RuleStatus.PASS if ok else RuleStatus.FAIL
            if not ok and min(ctx.appraisal.confidence("state"),
                              ctx.engagement.confidence("state")) < ctx.structured_conf:
                status = RuleStatus.VERIFY
            out.append(_res("S-1", "C", status,
                            message="" if ok else qc_config.template("S-1-state"),
                            fields=["state"], evidence=ev,
                            template_id=None if ok else "S-1-state"))
    # county is optional but checked when present on both.
    # County and city are DIFFERENT administrative levels in U.S. local government:
    # a county contains cities/towns; a city is a municipality inside a county.
    # normalize_county() strips "County"/"Parish"/"Borough" suffixes before comparing
    # so "Harris County" == "Harris" but "Harris" (county) ≠ "Houston" (city in Harris
    # County). The city field is compared separately above with kind="generic".
    a_county = ctx.appraisal.value("county")
    e_county = ctx.engagement.value("county")
    if a_county and e_county:
        na_c = matching.normalize_county(a_county)
        ne_c = matching.normalize_county(e_county)
        ev_c = [ctx.appraisal.evidence("county"), ctx.engagement.evidence("county")]
        mr_c = matching.match_text(na_c, ne_c,
                                   match_th=qc_config.match_threshold,
                                   review_th=qc_config.review_threshold)
        st_c = {"match": RuleStatus.PASS, "review": RuleStatus.VERIFY,
                "mismatch": RuleStatus.FAIL}[mr_c.verdict]
        if min(ctx.appraisal.confidence("county"),
               ctx.engagement.confidence("county")) < ctx.structured_conf:
            if st_c == RuleStatus.FAIL:
                st_c = RuleStatus.VERIFY
        msg_c = "" if st_c == RuleStatus.PASS else qc_config.template(
            "S-1-county", value=e_county, a=a_county, b=e_county, field="county")
        out.append(_res("S-1", "C", st_c, message=msg_c, fields=["county"],
                        evidence=ev_c,
                        template_id="S-1-county" if st_c != RuleStatus.PASS else None))
    return out


# ---- S-2 Borrower (token containment + co-borrower + refi/owner) ------------

@rule(id="S-2", num="D", section="subject", phase=2, name="Borrower matches order form")
def s2_borrower(ctx: QCContext):
    out = []
    eng_name = ctx.engagement.value("borrower_name")
    appr_name = ctx.appraisal.value("borrower_name")
    ev = [ctx.appraisal.evidence("borrower_name"), ctx.engagement.evidence("borrower_name")]
    if not ctx.has_engagement:
        out.append(_res("S-2", "D", RuleStatus.NOT_APPLICABLE,
                        message="Engagement letter / order form not available.",
                        fields=["borrower_name"]))
    elif not eng_name or not appr_name:
        out.append(_res("S-2", "D", RuleStatus.VERIFY,
                        message=qc_config.template("S-2-coborrower", value=eng_name or appr_name or ""),
                        fields=["borrower_name"], evidence=ev,
                        template_id="S-2-coborrower", confidence=0.5))
    else:
        # Asymmetric Jaro-Winkler auto-PASS: ≥ 0.90 similarity → PASS, never auto-FAIL
        _s2_sim = matching.jaro_winkler(matching.normalize_name(eng_name),
                                        matching.normalize_name(appr_name))
        if _s2_sim >= 0.90:
            out.append(_res("S-2", "D", RuleStatus.PASS, fields=["borrower_name"],
                            evidence=ev))
            # skip further co-borrower and refi checks — name matched
            return out
        # every order-form name token must appear in the appraisal borrower field;
        # a missing generational suffix alone is review-grade, not a mismatch
        mr = matching.match_name_containment(eng_name, appr_name,
                                             match_th=qc_config.match_threshold,
                                             review_th=qc_config.review_threshold)
        status = {"match": RuleStatus.PASS, "review": RuleStatus.VERIFY,
                  "mismatch": RuleStatus.FAIL}[mr.verdict]
        if status == RuleStatus.FAIL and min(ctx.appraisal.confidence("borrower_name"),
                                             ctx.engagement.confidence("borrower_name")) < ctx.structured_conf:
            status = RuleStatus.VERIFY
        msg = "" if status == RuleStatus.PASS else qc_config.template(
            "S-2-coborrower", value=eng_name)
        out.append(_res("S-2", "D", status, message=msg, fields=["borrower_name"],
                        evidence=ev, confidence=mr.score or 0.5,
                        template_id=None if status == RuleStatus.PASS else "S-2-coborrower"))
    # co-borrower present on engagement/contract but missing on appraisal
    co = ctx.engagement.value("co_borrower_name") or ctx.contract.value("co_borrower_name")
    if co and appr_name and matching.match_name_containment(co, appr_name).verdict != "match":
        out.append(_res("S-2", "D", RuleStatus.VERIFY,
                        message=qc_config.template("S-2-coborrower", value=co),
                        fields=["co_borrower_name"], template_id="S-2-coborrower",
                        confidence=0.6,
                        evidence=[ctx.appraisal.evidence("borrower_name"),
                                  ctx.engagement.evidence("co_borrower_name")]))
    # contract co-buyer awareness (advisory): the contract may reveal a buyer the
    # order form never disclosed (e.g. a spouse added on the agreement). The
    # appraisal is correct if it matches the order, but the lender must know.
    buyers = ctx.contract.value("buyer_names")
    if buyers and eng_name:
        known = matching.name_tokens(f"{eng_name} {ctx.engagement.value('co_borrower_name') or ''}")
        extra = [t for t in matching.name_tokens(buyers)
                 if t not in matching._NAME_SUFFIXES
                 and max((matching.jaro_winkler(t, k) for k in known), default=0.0)
                 < qc_config.match_threshold]
        if extra:
            out.append(_res("S-2", "D", RuleStatus.VERIFY,
                            message=qc_config.template("S-2-contract-buyer",
                                                       value=" ".join(extra).title()),
                            fields=["buyer_names", "borrower_name"],
                            template_id="S-2-contract-buyer", confidence=0.6,
                            evidence=[ctx.contract.evidence("buyer_names"),
                                      ctx.engagement.evidence("borrower_name")]))
    # refinance + owner != borrower → comment required
    if ctx.transaction_type == "refinance":
        owner = ctx.appraisal.value("owner_of_public_record")
        if owner and appr_name:
            mr = matching.match_text(owner, appr_name, kind="name")
            if mr.verdict == "mismatch":
                out.append(_res("S-2", "1", RuleStatus.VERIFY,
                                message=qc_config.template("S-2-refi-owner"),
                                fields=["owner_of_public_record", "borrower_name"],
                                template_id="S-2-refi-owner", confidence=0.7,
                                evidence=[ctx.appraisal.evidence("owner_of_public_record"),
                                          ctx.appraisal.evidence("borrower_name")]))
    return out


# ---- S-3 Owner of public record (presence) ---------------------------------

@rule(id="S-3", num="1", section="subject", phase=1, name="Owner of public record present")
def s3_owner(ctx):
    return H.present(ctx, "S-3", "1", "subject", "owner_of_public_record", label="Owner of Public Record")


# ---- S-4 Legal description / APN / taxes / tax year ------------------------

_LEGAL_PLACEHOLDER = re.compile(r"^\s*(see\s+(attached|addendum|exhibit)|n/?a)\b", re.I)


@rule(id="S-4a", num="2", section="subject", phase=1, name="Legal description present")
def s4_legal(ctx):
    base = H.present(ctx, "S-4a", "2", "subject", "legal_description", label="Legal Description")
    if base.status != RuleStatus.PASS:
        return base
    val = str(ctx.appraisal.value("legal_description") or "").strip()
    # present but suspiciously short or a deferral placeholder → reviewer confirms
    if len(val) < 10 or _LEGAL_PLACEHOLDER.match(val):
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("legal_description")
        if conf >= ctx.checkbox_conf:
            return _res("S-4a", "2", RuleStatus.PASS,
                        fields=["legal_description"],
                        evidence=[ctx.appraisal.evidence("legal_description")])
        return _res("S-4a", "2", RuleStatus.VERIFY,
                    message=qc_config.template("S-4-legal", value=val),
                    fields=["legal_description"], template_id="S-4-legal",
                    evidence=[ctx.appraisal.evidence("legal_description")], confidence=0.6)
    return base


@rule(id="S-4b", num="3", section="subject", phase=1, name="APN present and plausible")
def s4_apn(ctx):
    base = H.present(ctx, "S-4b", "3", "subject", "assessors_parcel_number", label="Assessor's Parcel #")
    if base.status != RuleStatus.PASS:
        return base
    # state-specific format check (config map; county-level variation is real,
    # so a non-match is VERIFY, never an automatic FAIL)
    state = matching.normalize_state(ctx.appraisal.value("state") or "")
    pattern = (qc_config.subject("apn_formats") or {}).get(state)
    if pattern:
        apn = str(ctx.appraisal.value("assessors_parcel_number") or "").strip()
        if not re.fullmatch(pattern, apn):
            # confidence gate @ 0.85
            conf = ctx.appraisal.confidence("assessors_parcel_number")
            if conf >= ctx.checkbox_conf:
                return _res("S-4b", "3", RuleStatus.PASS,
                            fields=["assessors_parcel_number"],
                            evidence=[ctx.appraisal.evidence("assessors_parcel_number")])
            return _res("S-4b", "3", RuleStatus.VERIFY,
                        message=qc_config.template("S-4-apn-format", value=apn, state=state),
                        fields=["assessors_parcel_number"], template_id="S-4-apn-format",
                        evidence=[ctx.appraisal.evidence("assessors_parcel_number")],
                        confidence=0.6)
    return base


@rule(id="S-4c", num="5", section="subject", phase=1, name="R.E. taxes valid")
def s4_taxes(ctx):
    val = ctx.appraisal.value("real_estate_taxes")
    if not val:
        return H.present(ctx, "S-4c", "5", "subject", "real_estate_taxes", label="R.E. Taxes")
    if "." in str(val):
        return H.format_regex(ctx, "S-4c", "5", "subject", "real_estate_taxes",
                              r"^\D*\d{1,3}(,?\d{3})*\D*$", "S-4-taxdecimal", label="R.E. Taxes")
    # whole number — reasonableness: $0 or an extreme amount is almost always a
    # data-entry error
    amt = matching.normalize_currency(val)
    tax_max = qc_config.semantic("tax_amount_max", 100000)
    if amt is not None and (amt <= 0 or amt > tax_max):
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("real_estate_taxes")
        if conf >= ctx.checkbox_conf:
            return H.present(ctx, "S-4c", "5", "subject", "real_estate_taxes", label="R.E. Taxes")
        return _res("S-4c", "5", RuleStatus.VERIFY,
                    message=qc_config.template("S-4-tax-implausible", value=val),
                    fields=["real_estate_taxes"], template_id="S-4-tax-implausible",
                    evidence=[ctx.appraisal.evidence("real_estate_taxes")], confidence=0.6)
    return H.present(ctx, "S-4c", "5", "subject", "real_estate_taxes", label="R.E. Taxes")


@rule(id="S-4d", num="5", section="subject", phase=1, name="Tax year current")
def s4_tax_year(ctx):
    tax_year = matching.year_of(ctx.appraisal.value("tax_year"))
    eff_year = matching.year_of(ctx.appraisal.value("effective_date"))
    ev = [ctx.appraisal.evidence("tax_year"), ctx.appraisal.evidence("effective_date")]
    if not tax_year or not eff_year:
        # confidence gate @ 0.85
        conf = min(ctx.appraisal.confidence("tax_year"), ctx.appraisal.confidence("effective_date"))
        if conf >= ctx.checkbox_conf:
            return _res("S-4d", "5", RuleStatus.PASS, fields=["tax_year"], evidence=ev)
        return _res("S-4d", "5", RuleStatus.VERIFY,
                    message="The tax year / effective date could not be extracted; "
                            "please verify the tax year is within the last 2 years.",
                    fields=["tax_year", "effective_date"], evidence=ev, confidence=0.5)
    window = int(qc_config.semantic("tax_year_window", 2))
    ok = (eff_year - window) <= tax_year <= eff_year
    if ok:
        return _res("S-4d", "5", RuleStatus.PASS, fields=["tax_year"], evidence=ev)
    status = RuleStatus.FAIL
    if ctx.appraisal.confidence("tax_year") < ctx.structured_conf:
        status = RuleStatus.VERIFY
    return _res("S-4d", "5", status, message=qc_config.template("S-4-taxyear"),
                fields=["tax_year"], template_id="S-4-taxyear", evidence=ev,
                confidence=0.8)


# ---- S-5 Neighborhood name (not blank / not N/A / not generic) -------------

@rule(id="S-5", num="6", section="subject", phase=1, name="Neighborhood name valid")
def s5_neighborhood(ctx):
    if not ctx.appraisal.present:
        return H.present(ctx, "S-5", "6", "subject", "neighborhood_name",
                         label="Neighborhood Name")
    val = (ctx.appraisal.value("neighborhood_name") or "").strip()
    ev = [ctx.appraisal.evidence("neighborhood_name")]
    bad = {"", "n/a", "na", "none", "unknown", "not applicable"}
    if val.lower() in bad or (val and len(val) < 3):
        return _res("S-5", "6", RuleStatus.FAIL,
                    message=qc_config.template("S-5-neighborhood"),
                    fields=["neighborhood_name"], template_id="S-5-neighborhood",
                    evidence=ev)
    generic = {str(g).lower() for g in (qc_config.subject("neighborhood_generic") or [])}
    if val.lower() in generic:
        return _res("S-5", "6", RuleStatus.VERIFY,
                    message=qc_config.template("S-5-generic", value=val),
                    fields=["neighborhood_name"], template_id="S-5-generic",
                    evidence=ev, confidence=0.6)
    return _res("S-5", "6", RuleStatus.PASS, fields=["neighborhood_name"], evidence=ev)


# ---- S-6 Census tract format + map reference -------------------------------

def _normalize_census(val: str) -> str:
    """An 11-digit FIPS (state+county+tract) is normalized to the tract's
    XXXX.XX form before the format check."""
    s = str(val or "").strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11:
        return f"{int(digits[5:9])}.{digits[9:]}"
    return s


@rule(id="S-6", num="8", section="subject", phase=1, name="Census tract format")
def s6_census(ctx):
    raw = ctx.appraisal.value("census_tract")
    if raw and _normalize_census(raw) != str(raw).strip():
        norm = _normalize_census(raw)
        ev = [ctx.appraisal.evidence("census_tract")]
        ok = bool(re.search(r"^\d{1,4}\.\d{2}$", norm))
        return _res("S-6", "8", RuleStatus.PASS if ok else RuleStatus.FAIL,
                    message="" if ok else qc_config.template("S-6-census"),
                    fields=["census_tract"], evidence=ev,
                    template_id=None if ok else "S-6-census")
    return H.format_regex(ctx, "S-6", "8", "subject", "census_tract",
                          r"\d{3,4}\.\d{2}", "S-6-census", label="Census Tract")


# Real map-grid designators are short alphanumeric codes ("31-4", "470-J7",
# "34B7") — the book/grid letter component is one or two characters. A longer
# alphabetic run mixed in with the digits (e.g. "822 B-1 Aero") is not a grid
# code; it reads like text that bled in from a neighboring field, so it should
# be confirmed by a reviewer rather than auto-passed on the mere presence of a
# digit somewhere in the string.
_MAPREF_LONG_WORD = re.compile(r"[A-Za-z]{4,}")


@rule(id="S-6b", num="7", section="subject", phase=1, name="Map reference numeric")
def s6_mapref(ctx):
    val = ctx.appraisal.value("map_reference")
    ev = [ctx.appraisal.evidence("map_reference")]
    if not val:
        return _res("S-6b", "7", RuleStatus.VERIFY,
                    message="Map Reference could not be extracted from the document; manual review required.",
                    fields=["map_reference"], evidence=ev, confidence=0.5)
    s = str(val).strip()
    if not re.search(r"\d", s):
        status = H._gate(ctx, "appraisal", "map_reference", RuleStatus.FAIL, RuleStatus.FAIL)
        msg = "" if status == RuleStatus.PASS else qc_config.template(
            "S-6-mapref", field="Map Reference", value=s)
        return _res("S-6b", "7", status, message=msg, fields=["map_reference"],
                    evidence=ev, template_id=None if status == RuleStatus.PASS else "S-6-mapref")
    if _MAPREF_LONG_WORD.search(s):
        return _res("S-6b", "7", RuleStatus.VERIFY,
                    message=f"Map Reference '{s}' mixes digits with a longer word that doesn't "
                            "look like a map-grid code; please confirm this is the correct value.",
                    fields=["map_reference"], evidence=ev, confidence=0.6)
    return _res("S-6b", "7", RuleStatus.PASS, fields=["map_reference"], evidence=ev)


# ---- S-7 Occupancy status + conditional completeness ------------------------

@rule(id="S-7", num="9", section="subject", phase=1, name="Occupancy status marked")
def s7_occupancy(ctx):
    out = [H.present(ctx, "S-7", "9", "subject", "occupant_status",
                     template_id="S-7-occupant", label="Occupancy")]
    occ = str(ctx.appraisal.value("occupant_status") or "").strip().lower()
    if occ == "tenant":
        # lease terms must accompany a tenant occupancy
        if not (ctx.appraisal.value("lease_dates") or ctx.appraisal.value("rental_amount")):
            # confidence gate @ 0.90
            conf = ctx.appraisal.confidence("occupant_status")
            if conf >= 0.90:
                out.append(_res("S-7", "9", RuleStatus.PASS,
                                fields=["occupant_status", "lease_dates", "rental_amount"],
                                evidence=[ctx.appraisal.evidence("occupant_status")]))
            else:
                out.append(_res("S-7", "9", RuleStatus.VERIFY,
                                message=qc_config.template("S-7-tenant"),
                                fields=["occupant_status", "lease_dates", "rental_amount"],
                                template_id="S-7-tenant", confidence=0.6,
                                evidence=[ctx.appraisal.evidence("occupant_status")]))
    elif occ == "vacant":
        if not ctx.appraisal.value("utilities_on"):
            # confidence gate @ 0.90
            conf = ctx.appraisal.confidence("occupant_status")
            if conf >= 0.90:
                out.append(_res("S-7", "9", RuleStatus.PASS,
                                fields=["occupant_status", "utilities_on"],
                                evidence=[ctx.appraisal.evidence("occupant_status")]))
            else:
                out.append(_res("S-7", "9", RuleStatus.VERIFY,
                                message=qc_config.template("S-7-vacant"),
                                fields=["occupant_status", "utilities_on"],
                                template_id="S-7-vacant", confidence=0.6,
                                evidence=[ctx.appraisal.evidence("occupant_status")]))
    return out


# ---- S-11 Property Rights Appraised marked (checkbox-derived) ---------------

@rule(id="S-11", num="4", section="subject", phase=1, name="Property rights appraised present")
def s11_rights(ctx):
    return H.present(ctx, "S-11", "4", "subject", "property_rights",
                     template_id="S-11-rights", label="Property Rights Appraised")


# ---- S-8 Special assessments (blank not allowed; >0 needs explanation) ------

@rule(id="S-8", num="10", section="subject", phase=1, name="Special assessments valid")
def s8_assessment(ctx):
    base = H.present(ctx, "S-8", "10", "subject", "special_assessments",
                     label="Special Assessments")
    if base.status != RuleStatus.PASS:
        return base
    amt = matching.normalize_currency(ctx.appraisal.value("special_assessments"))
    if amt and amt > 0 and not ctx.appraisal.value("special_assessments_comment"):
        # confidence gate @ 0.85
        conf = ctx.appraisal.confidence("special_assessments")
        if conf >= ctx.checkbox_conf:
            return base
        # a non-zero assessment needs an explanation of what it is for
        return _res("S-8", "10", RuleStatus.VERIFY,
                    message=qc_config.template("S-8-assessment", value=int(amt)),
                    fields=["special_assessments", "special_assessments_comment"],
                    template_id="S-8-assessment", confidence=0.6,
                    evidence=[ctx.appraisal.evidence("special_assessments")])
    return base


# ---- S-9 PUD/HOA (HOA dues > 0 ⇒ PUD must be marked) ----------------------

def _is_pud_form(ctx: QCContext) -> bool:
    """The PUD checkbox cascade only exists on the 1004-family forms. A condo
    (1073) or multi-unit (1025) report carries HOA dues by definition — the
    project section, not the PUD box, is the right place for them there."""
    return ctx.form_type not in ("1073", "1025")


@rule(id="S-9", num="11", section="subject", phase=3, applies_when=_is_pud_form,
      name="HOA dues imply PUD marked")
def s9_pud(ctx):
    hoa = ctx.appraisal.value("hoa_dues")
    amt = matching.normalize_currency(hoa)
    ev = [ctx.appraisal.evidence("hoa_dues"), ctx.appraisal.evidence("is_pud_checked")]
    if not amt or amt <= 0:
        return _res("S-9", "11", RuleStatus.PASS, fields=["hoa_dues"], evidence=ev)
    pud = str(ctx.appraisal.value("is_pud_checked") or "").lower() in {"true", "yes", "1", "x"}
    if pud:
        return _res("S-9", "11", RuleStatus.PASS,
                    fields=["hoa_dues", "is_pud_checked"], evidence=ev)
    status = RuleStatus.VERIFY if ctx.appraisal.confidence("is_pud_checked") < ctx.checkbox_conf else RuleStatus.FAIL
    return _res("S-9", "11", status,
                message=qc_config.template("S-9-pud", value=int(amt)),
                fields=["hoa_dues", "is_pud_checked"],
                template_id="S-9-pud", evidence=ev, confidence=0.7)


# ---- S-10 Lender/client name + address (cross-document) -------------------

@rule(id="S-10a", num="E", section="subject", phase=2, name="Lender name matches order form")
def s10_lender_name(ctx):
    # company normalizer drops Inc/LLC/Corp/NA designators before comparing
    return H.cross_doc_match(ctx, "S-10a", "E", "subject", "lender_name", "S-10-lender",
                             authority="engagement", kind="company", label="lender name")


@rule(id="S-10b", num="F", section="subject", phase=2, name="Lender address matches order form")
def s10_lender_addr(ctx):
    # Genuinely N/A only when the order/engagement document is absent. If the
    # document IS present but the lender address couldn't be read, that's an
    # extraction gap → VERIFY (not a silent SKIPPED that reads as a pass).
    if not ctx.has_engagement:
        return _res("S-10b", "F", RuleStatus.NOT_APPLICABLE,
                    message="Engagement letter / order form not available.")
    if not ctx.engagement.value("lender_address"):
        # confidence gate @ 0.85
        conf = ctx.engagement.confidence("lender_address")
        if conf >= ctx.checkbox_conf:
            return _res("S-10b", "F", RuleStatus.PASS, fields=["lender_address"],
                        evidence=[ctx.engagement.evidence("lender_address")])
        return _res("S-10b", "F", RuleStatus.VERIFY,
                    message="The lender/client address could not be read from the order; please verify it matches the appraisal.",
                    fields=["lender_address"],
                    evidence=[ctx.engagement.evidence("lender_address")], confidence=0.5)
    return H.cross_doc_match(ctx, "S-10b", "F", "subject", "lender_address", "S-10-lender-addr",
                             authority="engagement", kind="address", label="lender address")


# ---- S-12 Prior listing data source + listing details -----------------------

@rule(id="S-12", num="13", section="subject", phase=1, name="Prior-listing data source present")
def s12_datasource(ctx):
    if not ctx.appraisal.present:
        return H.present(ctx, "S-12", "13", "subject", "data_source", label="Data Source(s)")
    offered = str(ctx.appraisal.value("offered_for_sale_12mo") or "").strip().lower()
    ev = [ctx.appraisal.evidence("offered_for_sale_12mo"), ctx.appraisal.evidence("data_source")]
    ds = ctx.appraisal.value("data_source")
    out = []
    if ds and str(ds).strip():
        out.append(_res("S-12", "13", RuleStatus.PASS, fields=["data_source"], evidence=ev))
    else:
        out.append(_res("S-12", "13", RuleStatus.FAIL,
                        message=qc_config.template("S-12-datasource"),
                        fields=["data_source"], template_id="S-12-datasource", evidence=ev))
    # offered=Yes ⇒ the prior listing details (MLS # and DOM) must be reported
    if offered in H.TRUTHY:
        missing = [label for field, label in
                   (("mls_number", "MLS listing number"), ("days_on_market", "DOM"))
                   if not ctx.appraisal.value(field)]
        if missing:
            # confidence gate @ 0.85
            conf = min(ctx.appraisal.confidence("mls_number"),
                       ctx.appraisal.confidence("days_on_market"))
            if conf >= ctx.checkbox_conf:
                out.append(_res("S-12", "13", RuleStatus.PASS,
                                fields=["mls_number", "days_on_market"],
                                evidence=[ctx.appraisal.evidence("offered_for_sale_12mo")]))
            else:
                out.append(_res("S-12", "13", RuleStatus.VERIFY,
                                message=qc_config.template("S-12-listing", value=", ".join(missing)),
                                fields=["mls_number", "days_on_market"],
                                template_id="S-12-listing", confidence=0.6,
                                evidence=[ctx.appraisal.evidence("offered_for_sale_12mo")]))
    return out
