"""
rules.judge_pass — SHALqc-CORE §0/§4.2/§4.5: the C2 judge pass + guardrail.

This is what turns the deterministic engine into the CORE doctrine: after the
deterministic rules produce provisional verdicts (now treated as *machine
observations*), this pass hands each section's fact packets to the LLM judge
(C2), then VALIDATES the judge's reply and applies the ONE hard guardrail before
believing it:

  A judged FAIL is accepted only if (CORE §0):
    (a) every evidence quote is verbatim-grounded in the packet, AND
    (b) every numeric claim it makes is re-verifiable from packet values, AND
    (c) every field it used is above its confidence threshold.
  Any of the three missing ⇒ degrade FAIL→VERIFY(guardrail:<reason>).
  PASS / VERIFY / NA need only grounding for their quotes.

The judged status REPLACES the provisional one and is stamped judged_by=
"C2:judge_v1" so every status traces to a C2 reply + prompt version (DoD #6).
When the LLM is unavailable the provisional (deterministic) verdict stands —
the order is never blocked on the judge (CORE §4.0).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from app.llm import validate as V
from app.llm.grounding import is_grounded
from app.llm.judge import PROMPT_VERSION, judge_packets
from app.rules.catalog import requirement_for
from app.rules.context import QCContext
from app.rules.packet import build_packet
from app.rules.verdict import Status, Verdict

logger = logging.getLogger(__name__)

__version__ = "jdg-1.0.0"


def _grounding_sources(packet) -> List[str]:
    srcs = [str(f["value"]) for f in packet.fields.values() if f.get("value")]
    srcs += [s.get("text", "") for s in packet.context_snippets]
    return srcs


def _apply_one(provisional: Verdict, judged: dict, packet, ctx: QCContext) -> Verdict:
    """Validate one judge verdict + apply the guardrail; return the final Verdict."""
    raw_status = (judged.get("status") or "").upper()
    if not V.status_in_vocabulary(raw_status):        # CORE §8/§14: vocab gate
        return _keep(provisional, "judge_bad_status")

    status = Status(raw_status)
    quotes = [q.get("quote", "") for q in (judged.get("evidence_quotes") or [])]
    sources = _grounding_sources(packet)
    grounded = all(is_grounded(q, *sources) for q in quotes if q)
    reason_plain = judged.get("reason_plain", "") or ""

    # Grounding gate for any exception verdict (FAIL/VERIFY must cite grounded text)
    if status in (Status.FAIL, Status.VERIFY) and quotes and not grounded:
        status = Status.VERIFY
        degraded = "ungrounded"
    else:
        degraded = None

    # The ONE guardrail — a FAIL must clear grounding + numeric + threshold.
    if status == Status.FAIL:
        reason = _guardrail_fail_reason(judged, packet, ctx, grounded, quotes)
        if reason:
            status = Status.VERIFY
            degraded = f"guardrail:{reason}"

    final = Verdict(
        rule_id=provisional.rule_id, status=status, section=provisional.section,
        checklist_num=provisional.checklist_num,
        message_key=judged.get("message_key") if status != Status.PASS else None,
        message=reason_plain or provisional.message,
        reason_plain=reason_plain,
        evidence=provisional.evidence, fields_involved=provisional.fields_involved,
        confidence=float(judged.get("confidence", provisional.confidence) or 0.5),
        tier=provisional.tier, degraded_reason=degraded,
        judged_by=f"C2:{PROMPT_VERSION}",
    )
    # reviewer-facing quality gate (CORE §14) — if reason_plain is unusable, keep
    # the deterministic message but still credit the judge for the status.
    if not V.reason_plain_ok(final.reason_plain):
        final.message = provisional.message or final.reason_plain
    return final


def _guardrail_fail_reason(judged, packet, ctx, grounded, quotes) -> str:
    """Return a guardrail reason to degrade a FAIL, or '' to accept it."""
    # (a) grounding
    if quotes and not grounded:
        return "ungrounded"
    if not quotes:
        return "no_evidence_quote"
    # (c) threshold: every field used must be above review conf
    for fu in (judged.get("fields_used") or []):
        f = packet.fields.get(fu)
        if f is not None and float(f.get("confidence", 1.0)) < ctx.review_conf:
            return "low_confidence_input"
    # (b) numeric claims must be re-verifiable from packet values
    for nc in (judged.get("numeric_claims") or []):
        val = nc.get("value")
        if val is None:
            continue
        if not _numeric_supported(val, packet):
            return "math_unverified"
    return ""


def _numeric_supported(claimed, packet) -> bool:
    """Conservative numeric re-check (CORE §4.5): the claimed number must appear
    in / be derivable from packet field values (±0.5%). Without a per-claim
    formula we accept only claims corroborated by a packet value, else the FAIL
    is degraded (P4 — never FAIL on an unverifiable number)."""
    try:
        c = float(claimed)
    except (TypeError, ValueError):
        return False
    for f in packet.fields.values():
        raw = str(f.get("value") or "")
        for tok in _numbers(raw):
            if tok == 0:
                if abs(c) < 1e-9:
                    return True
            elif abs(c - tok) / abs(tok) * 100.0 <= 0.5:
                return True
    return False


def _numbers(text: str) -> List[float]:
    import re
    out = []
    for m in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _keep(provisional: Verdict, reason: str) -> Verdict:
    provisional.degraded_reason = (provisional.degraded_reason or "") + f"|{reason}"
    return provisional


def run_judge_pass(provisional: List[Verdict], ctx: QCContext, llm_client) -> List[Verdict]:
    """CORE §4.2: re-judge deterministic verdicts through the C2 LLM, batched per
    section. Returns the final verdict list. LLM unavailable ⇒ provisional stands."""
    if llm_client is None or not getattr(llm_client, "available", False):
        return provisional

    by_section: Dict[str, List[Verdict]] = defaultdict(list)
    for v in provisional:
        # NOT_APPLICABLE / gate-missing verdicts are not sent to the judge — the
        # judge decides real checks, not intake gating (keeps calls + budget down).
        if v.status == Status.NOT_APPLICABLE or v.tier != 1:
            by_section["_skip"].append(v)
        else:
            by_section[v.section or "other"].append(v)

    final: List[Verdict] = list(by_section.pop("_skip", []))
    amc_notes = ""
    if ctx.profile is not None:
        amc_notes = f"amc={ctx.profile.amc_code}"

    for section, vs in by_section.items():
        packets = [build_packet(v, ctx, requirement=requirement_for(v.rule_id), amc_notes=amc_notes)
                   for v in vs]
        judged = judge_packets(llm_client, packets)
        pmap = {p.rule_id: p for p in packets}
        for v in vs:
            jr = judged.get(v.rule_id)
            if jr is None:
                # judge didn't return this rule → keep provisional (deterministic)
                final.append(v)
            else:
                final.append(_apply_one(v, jr, pmap[v.rule_id], ctx))
    return final
