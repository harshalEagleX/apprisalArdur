"""
Deterministic order-level rules (T1) — SHALqc.md §5 / catalog items A–B.

Cross-document checks that the report matches what was ORDERED. Form-type is a
clean, unambiguous match (report 1004 vs ordered 1004); it runs through the ONE
normalizer like every other cross-doc check, so "1004 FHA" vs "1004" resolves
on the shared 1004 token rather than false-failing on the FHA suffix.
"""

from __future__ import annotations

import re

from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Status, Verdict


def _form_family(raw: str) -> str:
    """Reduce a form string to its UAD family token (1004/1073/1025/2055/…)."""
    m = re.search(r"\b(1004mc|1004|1073|1025|1007|2055|216)\b", (raw or "").lower())
    return m.group(1) if m else ""


@rule(id="ORD-FORM-MATCH", checklist="A", section="order", version=1,
      needs=["form_type", "engagement.form_type"],
      name="Report form matches the ordered form")
def ord_form_match(ctx: QCContext) -> Verdict:
    a = _form_family(ctx.appraisal.value("form_type"))
    e = _form_family(ctx.engagement.value("form_type"))
    ev = [ctx.appraisal.evidence("form_type"), ctx.engagement.evidence("form_type")]
    if not a or not e:
        # one side has no recognizable family token → can't assert a mismatch
        return Verdict(rule_id="ORD-FORM-MATCH", status=Status.VERIFY, confidence=0.5,
                       message="Could not read the form type on both documents — please confirm.",
                       evidence=ev, fields_involved=["form_type", "engagement.form_type"])
    if a == e:
        return Verdict(rule_id="ORD-FORM-MATCH", status=Status.PASS, evidence=ev,
                       fields_involved=["form_type"])
    return Verdict(rule_id="ORD-FORM-MATCH", status=Status.FAIL, confidence=0.85,
                   message_key="ORD-FORM-MATCH.form_mismatch",
                   message=f"Report form ({a}) does not match the ordered form ({e}).",
                   evidence=ev, fields_involved=["form_type", "engagement.form_type"])
