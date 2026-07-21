"""
language.validate_v2 (lvd-2.0.0) — the tightened reply validator (§4.4).

Every judge reply is re-checked by code before it is believed — the license that
lets the LLM judge. Each row of the §4.4 table is one `if`; a breach DEGRADES the
verdict (never silently trusts it) and stamps a `guardrail:` on the card so judge
quality is measurable per week. The conf-0 / ungrounded FAILs from the last run
become structurally impossible here.

Degrade ladder (only a consequential NOT_SATISFIED can be blocked):
  ungrounded quote, no surviving quote  → REVIEW (ungrounded)
  a number in `found` not backed by a packet value / hint (±0.5%) → REVIEW (math_mismatch)
  confidence < 0.6                      → REVIEW (low_judge_confidence)
  reasoning leans on an absent_label    → REVIEW (absent_data)
  status not in vocabulary              → REVIEW (bad_status)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.language.packet_v2 import Packet
from app.language.spec import CompiledItem
from app.language.verdict_v2 import ALLOWED_STATUSES, JudgeVerdict, StatusV2
from app.llm.grounding import is_grounded

_MARKDOWN = re.compile(r"[*_`#]|\[.*?\]\(.*?\)")
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")
# The vocabulary of an ABSENCE claim — "the data isn't there" — as opposed to a
# substantive finding ("28% exceeds the 25% limit"). Widened 2026-07-18: the old
# pattern only caught "no <word> present", so real judge output like "no comment
# field supplied" and "no corresponding grid entry is present" slipped through and
# became appraiser-facing rejects. Deliberately does NOT include bare "does not
# match" / "exceeds" / "outside" — those are contradictions between values we DID
# read, which are genuine rejects.
_ABSENCE_VERBS = r"(present|provided|supplied|given|found|stated|available|shown|listed|documented|entered|attached)"
_MISSING_WORDS = re.compile(
    r"\b(missing|absent|blank|empty|none|unavailable|unreadable|lack(s|ing)?"
    rf"|no\s+(?:\w+\s+){{0,4}}{_ABSENCE_VERBS}"
    rf"|not\s+(?:\w+\s+){{0,2}}{_ABSENCE_VERBS}"
    r"|could\s+not\s+(?:be\s+)?(?:find|found|locate[d]?|read))\b", re.I)
_CONF_FLOOR = 0.6


def _numbers(text: str) -> List[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _reviewer_line_ok(text: str) -> bool:
    t = (text or "").strip()
    return bool(8 <= len(t) <= 240 and not _MARKDOWN.search(t))


# §4 role contract: the LLM reports FINDINGS, it does not issue the reviewer's
# DECISION or direct the appraiser. Any reviewer_line that tells the appraiser to
# revise/correct/add a comment, or that pronounces a reject, is neutralized to the
# system-composed finding line. The reject WORDING lives in the rule-authored
# reject_text (surfaced only after the human clicks Confirm) — never LLM prose.
_DIRECTIVE_RX = re.compile(
    r"\b(recommend(?:s|ing)?\s+(?:a\s+)?reject|reject(?:s|ing|ion)?\b|"
    r"revise|correct(?:s|ed|ion)?\b|resubmit|amend|"
    r"add\s+(?:a\s+)?(?:comment|rejection|note)|provide\s+(?:a|the)|"
    r"appraiser\s+(?:must|should|needs?\s+to)|must\s+be\s+corrected|"
    r"please\s+(?:revise|correct|add|fix|provide)|fix\s+the)\b", re.I)


def _has_directive(text: str) -> bool:
    return bool(_DIRECTIVE_RX.search(text or ""))


def _human_label(label: str) -> str:
    return (label or "").replace("_", " ").strip()


def _missing_summary(packet: Packet, item: CompiledItem) -> str:
    """Name WHAT could not be read, so the reviewer knows what to go look for
    instead of being told a bare 'verify'."""
    labels = [_human_label(l) for l in (packet.absent_labels or [])[:3] if l]
    if labels:
        return ", ".join(labels)
    name = (item.item_name or "").strip()
    return name or "the value this check needs"


def _synth_line(status: StatusV2, expected: str, found: str,
                packet: Packet, item: CompiledItem) -> str:
    """The system-composed finding line. Tone contract (user directive
    2026-07-20): soft, asking language that names WHAT to verify — never a bare
    'please verify' / 'check manually' the reviewer can't act on."""
    if status == StatusV2.NOT_SATISFIED:
        # NEUTRAL finding — states expected vs found, leaves the decision to the
        # reviewer (the card's reject_text carries the reject wording, used only
        # after Confirm). No imperative, no "reject" pronounced by the LLM layer.
        base = (f"Expected {expected or 'the check to be met'}; the report shows "
                f"{found or 'something different'}. Could you please take a look and decide?")
    elif status == StatusV2.SATISFIED:
        base = f"Checked: {found or 'the report data'} — this looks in order."
    elif status == StatusV2.NOT_APPLICABLE:
        base = f"Not applicable: {expected or found or 'precondition absent'}."
    elif status == StatusV2.CANNOT_EVALUATE:
        base = (f"We couldn't find {_missing_summary(packet, item)} in the report — "
                "could you please look it up in the document and confirm?")
    else:
        base = (f"Expected {expected or 'a value'}; found {found or 'unclear data'}. "
                "Could you please double-check this one?")
    return base[:240]


def _packet_value_strings(packet: Packet) -> List[str]:
    return [str(v.get("v")) for v in packet.values.values() if v.get("v") is not None]


# SHALqc-CORE §5: human-facing badge for where a value came from (mirrors
# report.builder._SOURCE_BADGE; kept here so the language card is self-describing).
_SOURCE_BADGE = {
    "xml": "XML", "pdf_digital": "Report", "pdf_scanned": "Report", "grid": "Report",
    "checkbox": "Report", "acroform": "Report", "engagement": "Order form",
    "llm": "AI-read", "contract": "Contract",
}


def _badge(source: Optional[str]) -> str:
    if not source:
        return ""
    key = source.split(".")[-1].lower() if source else ""
    return _SOURCE_BADGE.get(key, "Report")


def _located_evidence(packet: Packet, quotes_by_label: Dict[str, str]) -> List[Dict[str, Any]]:
    """One evidence row per bound packet value, carrying coordinates so the
    frontend can auto-scroll the document. A grounded LLM quote is attached to its
    label when present. Order: the value the judge actually CITED first (that is
    the one the reviewer should be scrolled to), then best-located
    (exact > region > page > none)."""
    rank = {"exact": 0, "region": 1, "page": 2, "none": 3}
    rows: List[Dict[str, Any]] = []
    for label, entry in packet.values.items():
        if entry.get("v") is None:
            continue
        rows.append({
            "label": label,
            "value": entry.get("v"),
            "quote": quotes_by_label.get(label),
            "page": entry.get("page"),
            "bbox": entry.get("bbox"),
            "location_quality": entry.get("lq") or "none",
            "source": entry.get("source"),
            "source_badge": _badge(entry.get("source")),
            "confidence": round(float(entry.get("confidence") or 0.0), 3),
        })
    rows.sort(key=lambda r: (0 if r["quote"] else 1,
                             rank.get(r["location_quality"], 3)))
    return rows


def _primary_location(evidence: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The single best {page, bbox} to jump the document to on card click — the
    first located evidence row that actually has a page."""
    for e in evidence:
        if e.get("page") is not None:
            return {"page": e["page"], "bbox": e.get("bbox"),
                    "label": e.get("label"), "location_quality": e.get("location_quality")}
    return None


def _hint_values(packet: Packet) -> List[float]:
    out: List[float] = []
    for h in packet.computed_hints:
        val = h.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append(float(val))
    return out


def _num_supported(n: float, sources_nums: List[float]) -> bool:
    for tok in sources_nums:
        if tok == 0:
            if abs(n) < 1e-9:
                return True
        elif abs(n - tok) / abs(tok) * 100.0 <= 0.5:
            return True
    return False


def validate(raw: Dict[str, Any], packet: Packet, item: CompiledItem) -> JudgeVerdict:
    """Validate one raw judge verdict against its packet → a stamped JudgeVerdict."""
    guardrails: List[str] = []
    raw_status = str(raw.get("status", "")).upper()
    if raw_status not in ALLOWED_STATUSES:
        raw_status = "REVIEW"
        guardrails.append("bad_status")
    status = StatusV2(raw_status)

    # B3: a verdict the self-consistency pass found flip-prone is already downgraded
    # to REVIEW upstream; stamp the reason as a guardrail so it stays visible/measurable
    # on the card even when the reviewer_line is re-synthesized below (judge quality is
    # tracked via guardrails, not prose).
    _ju = raw.get("judge_unstable")
    if isinstance(_ju, dict) and _ju.get("samples"):
        from collections import Counter
        _tally = ",".join(f"{s}x{c}" for s, c in Counter(_ju["samples"]).most_common())
        guardrails.append(f"judge_unstable:{_tally}")

    expected = str(raw.get("expected", "") or "")[:400]
    found = str(raw.get("found", "") or "")[:400]
    reviewer_line = str(raw.get("reviewer_line", "") or "")
    try:
        confidence = float(raw.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    # --- grounding: keep only quotes that are verbatim in a packet VALUE --------
    value_strings = _packet_value_strings(packet)
    quotes_by_label: Dict[str, str] = {}
    for e in (raw.get("evidence") or []):
        if not isinstance(e, dict):
            continue
        quote = str(e.get("quote", "") or "")
        if quote and is_grounded(quote, *value_strings):
            lbl = e.get("label")
            if lbl and lbl not in quotes_by_label:
                quotes_by_label[str(lbl)] = quote
    # Evidence rows carry COORDINATES (page/bbox) for the document auto-scroll —
    # every bound value, with the grounded LLM quote attached to its label.
    grounded_ev = _located_evidence(packet, quotes_by_label)

    # never_reject is an ITEM-LEVEL policy — this check can never be a hard reject,
    # whatever the evidence looks like — so it is settled BEFORE the degrade ladder
    # reasons about reject quality. Ordering matters only for the audit label: once
    # the widened absence guard (2026-07-18) started catching more NOT_SATISFIEDs,
    # a never_reject item was being stamped `absent_data` instead of `never_reject`,
    # which hides WHY the card can't reject. Same status either way.
    if getattr(item, "never_reject", False) and status == StatusV2.NOT_SATISFIED:
        status, suggest_override = StatusV2.REVIEW, True
        guardrails.append("never_reject")
    else:
        suggest_override = False

    # --- the degrade ladder, only for the consequential NOT_SATISFIED ----------
    if status == StatusV2.NOT_SATISFIED:
        if not quotes_by_label:
            status, reason = StatusV2.REVIEW, "ungrounded"
            guardrails.append(reason)
        elif confidence < _CONF_FLOOR:
            status = StatusV2.REVIEW
            guardrails.append("low_judge_confidence")
        elif _leans_on_absent(found, expected, packet):
            status = StatusV2.REVIEW
            guardrails.append("absent_data")
        else:
            hint_and_value_nums = _hint_values(packet) + [
                n for s in value_strings for n in _numbers(s)]
            bad = [n for n in _numbers(found) if not _num_supported(n, hint_and_value_nums)]
            if bad:
                status = StatusV2.REVIEW
                guardrails.append("math_mismatch")

    # suggested reject wording only survives on a NOT_SATISFIED. Multi-reject: the
    # judge's suggest_reject_wording IS the fired branch's reject_text with {slots}
    # filled — prefer it; fall back to the single reject_text.
    suggest = raw.get("suggest_reject_wording") or item.reject_text or packet.reject_text
    if status != StatusV2.NOT_SATISFIED:
        suggest = None

    # never_reject, second half: the status was already capped to REVIEW above (it
    # is an item-level policy, settled before the degrade ladder); here we drop the
    # appraiser-facing reject wording that would otherwise ride along. The card
    # still goes to the reviewer as a VERIFY — never_reject removes the ability to
    # REJECT, it does not remove the finding.
    if suggest_override:
        suggest = None

    # hold (EQ-30 illegal zoning / EQ-31 H&BU=No): a fired trigger means ESCALATE to
    # the AMC, NOT an appraiser reject — keep it actionable but emit no reject text.
    # hold escalation can be item-level (the WHOLE check escalates, e.g. EQ-31
    # H&BU=No) OR branch-level (only ONE fail-mode escalates while the item's other
    # branches reject normally, e.g. EQ-30 illegal-zoning among legal-nonconforming
    # branches). Both mean: keep the finding actionable but emit no appraiser reject.
    fb = raw.get("fired_branch")
    branches = getattr(item, "reject_branches", None) or []
    branch_hold = (isinstance(fb, int) and 0 <= fb < len(branches)
                   and bool(branches[fb].get("hold")))
    if (getattr(item, "hold", False) or branch_hold) and status == StatusV2.NOT_SATISFIED:
        suggest = None
        guardrails.append("hold_escalate")
    # record which fail-branch fired (audit / provenance), if any.
    if fb is not None and status == StatusV2.NOT_SATISFIED:
        guardrails.append(f"branch:{fb}")

    # §4: neutralize a malformed OR a directive/verdict-issuing reviewer_line into
    # the system-composed finding line — the LLM never gets to phrase the decision.
    if not _reviewer_line_ok(reviewer_line):
        reviewer_line = _synth_line(status, expected, found, packet, item)
    elif _has_directive(reviewer_line):
        reviewer_line = _synth_line(status, expected, found, packet, item)
        guardrails.append("directive_language")

    return JudgeVerdict(
        item_id=item.item_id, status=status, check_text=item.check_text,
        section=item.section, item_name=item.item_name, reject_text=item.reject_text,
        expected=expected, found=found,
        reviewer_line=reviewer_line, evidence=grounded_ev,
        primary_location=_primary_location(grounded_ev),
        suggest_reject_wording=suggest, confidence=round(confidence, 3),
        judgeable=item.judgeable, guardrails=guardrails, decided_by="judge_v2",
        values=packet.raw_values(),
        bound_by=item.bound_by, binder_confidence=item.binder_confidence,
        bound_labels=list(item.bound_labels), severity=item.severity,
    )


def _leans_on_absent(found: str, expected: str, packet: Packet) -> bool:
    """Rule 3: a NOT_SATISFIED whose reasoning depends on missing data is capped at
    REVIEW — the engine cannot tell 'absent from the report' from 'never read'.

    2026-07-18: this used to require `packet.absent_labels` to be non-empty, which
    missed the commonest case — the judge rejecting over data that was never BOUND
    at all, so it appears in no absent_labels list. Measured on the 7-order
    baseline, rejects rose 3.7 → 5.1/order once previously-unjudged items started
    being judged, and the repeat offenders were exactly this shape:
        EQ-22  "land_use_other=5 (no comment field supplied)"      → NOT_SATISFIED
        EQ-75  "Porch is marked ... but no corresponding grid
                entry is present"                                  → NOT_SATISFIED
    Neither is evidence the report is wrong; both are evidence we did not read
    something. So the guard now keys on the CLAIM: any NOT_SATISFIED justified by
    absence is capped at REVIEW, whether or not a bound label happens to be listed
    absent. A human then confirms — which is the honest outcome, and far cheaper
    than a false rejection sent back to an appraiser.
    """
    text = f"{found} {expected}".lower()
    if _MISSING_WORDS.search(text):
        return True
    for lbl in (packet.absent_labels or []):
        if lbl.lower() in text or lbl.replace("_", " ").lower() in text:
            return True
    return False
