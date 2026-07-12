"""
Deterministic cross-document rules (T1) — SHALqc.md §5.

Lender identity across the appraisal report and the engagement letter. Company
names normalize through the ONE normalizer, so "Extreme Loans" ==
"Extreme Loans, LLC" (corporate-designator difference) never false-FAILs; any
residual core-name difference is capped at VERIFY (§4 company rule).
"""

from __future__ import annotations

from app.rules import helpers as H
from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Verdict


@rule(id="S-10a", checklist="E", section="cross_document", version=1,
      needs=["lender_name", "engagement.lender_name"],
      name="Lender name matches order form")
def s10_lender_name(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-10a", "lender_name", "engagement.lender_name",
                       message_key="S-10.lender_mismatch", kind="company", label="Lender name")


@rule(id="S-10b", checklist="F", section="cross_document", version=1,
      needs=["lender_address", "engagement.lender_address"],
      name="Lender address matches order form")
def s10_lender_addr(ctx: QCContext) -> Verdict:
    return H.cross_doc(ctx, "S-10b", "lender_address", "engagement.lender_address",
                       message_key="S-10.lender_addr_mismatch", kind="address",
                       label="Lender address")
