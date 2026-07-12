"""
rules.engine — SHALqc.md §5 rule engine.

Runs every registered rule against a QCContext and returns the list of Verdicts.
The engine, not the rule body, enforces the guardrails so every rule stays a
pure comparison (P3, P4):

  1. applies_when(ctx) false            → NOT_APPLICABLE (rule skipped)
  2. profile turned the rule off        → skipped entirely (Part 6 binding)
  3. needs[] gate (before the body):
       - a needed doc is absent         → NOT_APPLICABLE
       - a needed field missing/blank   → VERIFY  (§3.3: FAIL only on *proven*
                                          absence, which needs the back-locator —
                                          out of scope, so missing ⇒ VERIFY)
       - a needed field below review conf→ VERIFY  (P4: low conf can't FAIL)
  4. otherwise the body runs on trusted, above-threshold data and returns
     PASS/FAIL/VERIFY/NA.
  5. tier-2/3 (LLM) rules with no client configured degrade to VERIFY
     `llm_unavailable` — an order NEVER auto-passes or auto-fails blind
     (SHALqc-CORE §4.0 C2 fallback).

A rule body may return one Verdict or a list; the engine flattens. A crashing
rule becomes a single VERIFY (P6 — one rule's failure never sinks the run).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.rules.context import QCContext
from app.rules.registry import RuleSpec, all_rules
from app.rules.verdict import Evidence, Status, Verdict, degrade_to_verify

logger = logging.getLogger(__name__)

__version__ = "rul-1.0.0"


def _gate(spec: RuleSpec, ctx: QCContext) -> Optional[Verdict]:
    """Apply the needs[] pre-body gate. Returns a short-circuit Verdict, or
    None to let the body run."""
    for need in spec.needs:
        doc_label, name = QCContext._split_need(need)
        view = ctx.doc(doc_label)
        if not view.present:
            return Verdict(
                rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                status=Status.NOT_APPLICABLE, tier=spec.tier,
                message=f"The {doc_label} document was not provided; {spec.rule_id} cannot be evaluated.",
                fields_involved=[need],
            )
    # second pass: present docs, but missing / low-confidence fields. A missing
    # field is NOT a blanket VERIFY — the significance resolver decides whether
    # the blank is expected (PASS), informational (NA), an engine extraction gap
    # (engine-health), or a real reviewer VERIFY (SHALqc significance layer).
    for need in spec.needs:
        ev = ctx.resolve(need)
        if ev.value is None or not str(ev.value).strip():
            from app.rules.semantics import gate_verdict
            _doc, name = QCContext._split_need(need)
            return gate_verdict(spec, name, ctx, Verdict, Status)
        if ev.confidence < ctx.review_conf:
            return Verdict(
                rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                status=Status.VERIFY, tier=spec.tier, confidence=round(ev.confidence, 3),
                message=f"{need} was read with low confidence — please confirm.",
                evidence=[ev], fields_involved=[need],
                degraded_reason="low_confidence_input",
            )
    return None


def _flatten(result) -> List[Verdict]:
    if result is None:
        return []
    if isinstance(result, Verdict):
        return [result]
    return [v for v in result if isinstance(v, Verdict)]


def _profile_allows(spec: RuleSpec, ctx: QCContext) -> bool:
    """Part 6 binding: an AMC profile may switch a rule off. Absent profile ⇒
    every rule runs (the `_base` default is `rules.default: on`)."""
    profile = ctx.profile
    if profile is None:
        return True
    off = getattr(profile, "rules_on", None)
    if isinstance(off, dict) and spec.rule_id in off:
        return bool(off[spec.rule_id])
    return True


def run_rules(ctx: QCContext, rules: Optional[List[RuleSpec]] = None,
              llm_client=None, judge_mode: bool = False) -> List[Verdict]:
    """Evaluate all applicable rules against ctx. `llm_client` is the Part-10
    client for tier-2/3 rules; None ⇒ those rules degrade to VERIFY.

    `judge_mode` (SHALqc-CORE §0/§4.2): when True and an LLM client is present,
    the deterministic verdicts are treated as *machine observations* and
    RE-JUDGED by the C2 LLM (validated + guardrailed) so every status traces to
    a C2 reply (DoD #6). Default False keeps the fast deterministic path
    (SHALqc.md §5) — the two are output-compatible; judge_mode adds the CORE
    doctrine as the production path without changing rule bodies."""
    specs = rules if rules is not None else all_rules()
    verdicts: List[Verdict] = []
    # expose the client to tier-2/3 rule bodies (they read ctx.llm_client)
    ctx.llm_client = llm_client

    for spec in specs:
        if not _profile_allows(spec, ctx):
            continue
        if not spec.applicable(ctx):
            verdicts.append(Verdict(
                rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                status=Status.NOT_APPLICABLE, tier=spec.tier,
                message=f"{spec.rule_id} does not apply to this order.",
            ))
            continue

        gate = _gate(spec, ctx)
        if gate is not None:
            verdicts.append(gate)
            continue

        # tier-2/3 rules need the LLM; with no client they cannot render a
        # verdict, so they degrade to VERIFY rather than guess (SHALqc-CORE §4.0).
        if spec.tier in (2, 3) and llm_client is None:
            verdicts.append(Verdict(
                rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                status=Status.VERIFY, tier=spec.tier, confidence=0.5,
                message=f"{spec.name}: needs LLM judgment (not configured) — please review.",
                degraded_reason="llm_unavailable",
            ))
            continue

        try:
            body_result = spec.fn(ctx)
        except Exception as exc:
            logger.warning("rule %s crashed: %s", spec.rule_id, exc)
            verdicts.append(Verdict(
                rule_id=spec.rule_id, section=spec.section, checklist_num=spec.checklist_num,
                status=Status.VERIFY, tier=spec.tier, confidence=0.4,
                message=f"{spec.rule_id} could not be evaluated due to an internal error — please review.",
                degraded_reason="rule_error",
            ))
            continue

        for v in _flatten(body_result):
            # stamp identity/section defaults so rule bodies stay terse
            v.rule_id = v.rule_id or spec.rule_id
            v.section = v.section or spec.section
            v.checklist_num = v.checklist_num or spec.checklist_num
            v.tier = v.tier or spec.tier
            verdicts.append(v)

    # CORE §4.2 C2: re-judge the deterministic verdicts through the LLM when
    # requested (and a client exists). Deterministic verdicts become machine
    # observations; the judged status (validated + guardrailed) replaces them.
    if judge_mode and llm_client is not None:
        from app.rules.judge_pass import run_judge_pass
        verdicts = run_judge_pass(verdicts, ctx, llm_client)

    return verdicts


def counts(verdicts: List[Verdict]) -> dict:
    c = {s.value: 0 for s in Status}
    for v in verdicts:
        c[v.status.value] += 1
    return c
