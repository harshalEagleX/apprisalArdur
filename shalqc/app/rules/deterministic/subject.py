"""
Deterministic subject-section rules (T1) — SHALqc.md §5.

Each cross-document check is its own @rule so the needs[] gate can clear it
independently: a missing zip must not block the address check. Every comparison
goes through the ONE normalizer (P6), so "Mdw Ct"=="Meadow Ct", "Texas"=="TX",
"Owner"=="OwnerOccupied" never false-FAIL — that work lives in Part 4, not here.

The engagement letter is the authority for address/borrower/lender; the
appraisal report is compared against it.
"""

from __future__ import annotations

from app.rules import helpers as H
from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Status, Verdict


# ── S-1 Property address (5 components, each gated independently) ────────────

@rule(id="S-1", checklist="C", section="subject", version=1,
      needs=["property_address", "engagement.property_address"],
      name="Property address matches order form")
def s1_address(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-1", "property_address", "engagement.property_address",
                       message_key="S-1.address_mismatch", kind="address", label="Property address")


@rule(id="S-1b", checklist="C", section="subject", version=1,
      needs=["city", "engagement.city"], name="Subject city matches order form")
def s1_city(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-1b", "city", "engagement.city",
                       message_key="S-1.city_mismatch", kind="generic", label="City")


@rule(id="S-1c", checklist="C", section="subject", version=1,
      needs=["state", "engagement.state"], name="Subject state matches order form")
def s1_state(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-1c", "state", "engagement.state",
                       message_key="S-1.state_mismatch", label="State")


@rule(id="S-1d", checklist="C", section="subject", version=1,
      needs=["zip_code", "engagement.zip_code"], name="Subject zip matches order form")
def s1_zip(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-1d", "zip_code", "engagement.zip_code",
                       message_key="S-1.zip_mismatch", label="Zip")


@rule(id="S-1e", checklist="C", section="subject", version=1,
      needs=["county", "engagement.county"], name="Subject county matches order form")
def s1_county(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-1e", "county", "engagement.county",
                       message_key="S-1.county_mismatch", label="County")


# ── S-2 Borrower (order-form name must be contained in the appraisal name) ───

@rule(id="S-2", checklist="D", section="subject", version=1,
      needs=["borrower_name", "engagement.borrower_name"],
      name="Borrower matches order form")
def s2_borrower(ctx: QCContext) -> Verdict:
    # name_containment: every order-form token must appear in the appraisal name;
    # a missing generational suffix alone is "review", not "mismatch" (§4 names).
    return H.cross_doc(ctx, "S-2", "engagement.borrower_name", "borrower_name",
                       message_key="S-2.borrower_mismatch", kind="name_containment",
                       label="Borrower name")


# ── S-3 Owner of public record present ──────────────────────────────────────

@rule(id="S-3", checklist="1", section="subject", version=1,
      needs=["owner_of_public_record"], name="Owner of public record present")
def s3_owner(ctx: QCContext) -> Verdict:
    # gate proved presence; on a REFINANCE, owner ≠ borrower additionally
    # requires a comment (catalog S-3 same_section). Layout-independent.
    base = H.passed(ctx, "S-3", "owner_of_public_record")
    if ctx.transaction_type != "refinance":
        return base
    owner = ctx.appraisal.value("owner_of_public_record")
    borrower = ctx.appraisal.value("borrower_name")
    if not owner or not borrower:
        return base
    from app.normalize import compare as _compare
    if _compare(None, owner, borrower, kind="name_containment").verdict == "match":
        return base
    if (ctx.appraisal.value("subject_comments") or "").strip():
        return base   # a comment explains the difference → PASS
    return [base, Verdict(
        rule_id="S-3", status=Status.VERIFY, section="subject", confidence=0.7,
        message_key="S-3.refi_owner_diff",
        message="Refinance: owner of record differs from the borrower and no explanatory comment was found.",
        evidence=[ctx.appraisal.evidence("owner_of_public_record"),
                  ctx.appraisal.evidence("borrower_name")],
        fields_involved=["owner_of_public_record", "borrower_name"])]


# ── S-4a Legal description present ──────────────────────────────────────────

@rule(id="S-4a", checklist="2", section="subject", version=1,
      needs=["legal_description"], name="Legal description present")
def s4_legal(ctx: QCContext) -> Verdict:
    return H.passed(ctx, "S-4a", "legal_description")


# ── S-5 Neighborhood name valid (present, not a placeholder) ────────────────

_BAD_NEIGHBORHOOD = {"n/a", "na", "none", "unknown", "not applicable"}


@rule(id="S-5", checklist="6", section="subject", version=1,
      needs=["neighborhood_name"], name="Neighborhood name valid")
def s5_neighborhood(ctx: QCContext) -> Verdict:
    val = (ctx.appraisal.value("neighborhood_name") or "").strip()
    if val.lower() in _BAD_NEIGHBORHOOD or len(val) < 3:
        return H.fail(ctx, "S-5", "neighborhood_name",
                      message_key="S-5.neighborhood_invalid",
                      message="Neighborhood name is blank or a placeholder.")
    return H.passed(ctx, "S-5", "neighborhood_name")


# ── S-11 Property rights appraised present ──────────────────────────────────

@rule(id="S-11", checklist="4", section="subject", version=1,
      needs=["property_rights"], name="Property rights appraised present")
def s11_rights(ctx: QCContext) -> Verdict:
    return H.passed(ctx, "S-11", "property_rights")
