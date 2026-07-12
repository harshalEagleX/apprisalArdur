"""
LLM-judged narrative rules (T2) — SHALqc.md §5 Tier 2.

Tier-2 rules judge things a regex genuinely cannot: canned-vs-specific
commentary, substantive-vs-pointer analysis, trend-vs-narrative consistency.
Per SHALqc.md §5, the LLM classifies → deterministic code maps class → verdict,
and the tier's max severity is VERIFY (an LLM-sourced finding never auto-FAILs).

In this build the LLM subsystem (Part 10) is not wired, so these rules never
run their body — the engine degrades every tier-2/3 rule to VERIFY
`llm_unavailable` when no client is configured (rules/engine.py). The rule is
registered here (tier=2) so its checklist item is accounted for and the degrade
path is exercised and tested now; the body is the contract a future
app/llm/judge.py implementation fills in.
"""

from __future__ import annotations

from app.rules.context import QCContext
from app.rules.registry import rule
from app.rules.verdict import Status, Verdict


def _has_narrative(ctx: QCContext) -> bool:
    return bool(ctx.appraisal.value("neighborhood_description")
                or ctx.appraisal.value("market_conditions_commentary"))


@rule(id="N-CANNED", checklist="7", section="neighborhood", version=1, tier=2,
      applies_when=_has_narrative,
      name="Neighborhood commentary is specific, not canned")
def n_canned(ctx: QCContext) -> Verdict:
    """Reached ONLY when a tier-2 client is configured (else the engine degrades
    to VERIFY before this body runs). The judge returns {class, quote}; the
    class → verdict mapping below is CODE, and the max severity is VERIFY — an
    LLM-sourced finding never auto-FAILs (SHALqc.md §5 T2)."""
    from app.llm.judge import classify_narrative

    text = (ctx.appraisal.value("neighborhood_description")
            or ctx.appraisal.value("market_conditions_commentary") or "")
    ev = ctx.appraisal.evidence("neighborhood_description")

    c = classify_narrative(
        ctx.llm_client,
        question="Is this neighborhood commentary specific to the subject market, or generic/canned boilerplate?",
        allowed_classes=["specific", "canned"],
        text=text,
    )
    if c is None:
        # reply unusable → VERIFY, never a blind pass (SHALqc-CORE §4.0)
        return Verdict(rule_id="N-CANNED", status=Status.VERIFY, tier=2, confidence=0.5,
                       message="Could not classify neighborhood commentary — please review.",
                       evidence=[ev], degraded_reason="llm_unusable_reply")

    if c.klass == "specific" and c.grounded:
        return Verdict(rule_id="N-CANNED", status=Status.PASS, tier=2,
                       evidence=[ev], fields_involved=["neighborhood_description"])
    # canned (or ungrounded "specific") → VERIFY, the tier-2 ceiling
    return Verdict(
        rule_id="N-CANNED", status=Status.VERIFY, tier=2, confidence=0.6,
        message_key="N-CANNED.canned_commentary",
        message="Neighborhood commentary reads as generic/canned — please confirm it is market-specific.",
        evidence=[ev], fields_involved=["neighborhood_description"],
    )
