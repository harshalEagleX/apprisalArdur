"""
rules.helpers — terse builders for T1 deterministic rule bodies (SHALqc.md §5).

Because the engine's needs[] gate already guarantees every needed field is
present and above threshold before a body runs (rules/engine.py), a rule body
is pure comparison. These helpers keep each body one or two lines and route
every comparison through the ONE normalizer (P6) — no rule does its own string
cleanup or its own confidence downgrade.

Verdict mapping is uniform: normalizer verdict match→PASS, review→VERIFY,
mismatch→FAIL, and a FAIL on a below-threshold input is degraded to VERIFY (P4).
"""

from __future__ import annotations

from typing import List, Optional

from app.extraction.schema import schema_loader
from app.normalize import compare as _compare
from app.rules.context import QCContext
from app.rules.verdict import Evidence, Status, Verdict


_VERDICT_STATUS = {"match": Status.PASS, "review": Status.VERIFY, "mismatch": Status.FAIL}


def _field_def(name: str):
    # strip a doc prefix ("engagement.property_address" → "property_address")
    if "." in name:
        _prefix, base = name.split(".", 1)
        name = base
    return schema_loader.get_field(name)


def cross_doc(ctx: QCContext, rule_id: str, need_a: str, need_b: str,
              message_key: str, kind: Optional[str] = None, label: str = "") -> Verdict:
    """Compare two needs across documents via the normalizer, band → verdict.

    Both needs are gate-guaranteed present + above threshold, so this body only
    decides match/review/mismatch — never presence.
    """
    ev_a, ev_b = ctx.resolve(need_a), ctx.resolve(need_b)
    field_def = _field_def(need_a)
    mr = _compare(field_def, ev_a.value, ev_b.value, kind=kind)
    status = _VERDICT_STATUS[mr.verdict]

    # P4: even though the gate cleared both inputs above review_conf, keep the
    # structural guarantee explicit — a FAIL never survives a low-conf input.
    if status == Status.FAIL and min(ev_a.confidence, ev_b.confidence) < ctx.review_conf:
        status = Status.VERIFY

    return Verdict(
        rule_id=rule_id, status=status,
        message_key=None if status == Status.PASS else message_key,
        message="" if status == Status.PASS else f"{label or need_a} does not match across documents.",
        evidence=[ev_a, ev_b], fields_involved=[need_a, need_b],
        confidence=mr.score or 0.5,
    )


def passed(ctx: QCContext, rule_id: str, need: str) -> Verdict:
    """The gate already proved `need` is present + confident; a presence rule
    body therefore just returns PASS with that field's evidence."""
    ev = ctx.resolve(need)
    return Verdict(rule_id=rule_id, status=Status.PASS, evidence=[ev], fields_involved=[need])


def fail(ctx: QCContext, rule_id: str, need: str, message_key: str, message: str,
         confidence: float = 0.9) -> Verdict:
    return Verdict(
        rule_id=rule_id, status=Status.FAIL, message_key=message_key, message=message,
        evidence=[ctx.resolve(need)], fields_involved=[need], confidence=confidence,
    )


def verify(ctx: QCContext, rule_id: str, needs: List[str], message: str,
           confidence: float = 0.6) -> Verdict:
    return Verdict(
        rule_id=rule_id, status=Status.VERIFY, message=message,
        evidence=[ctx.resolve(n) for n in needs], fields_involved=needs, confidence=confidence,
    )
