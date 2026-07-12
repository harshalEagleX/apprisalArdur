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
_MISSING_WORDS = re.compile(r"\b(missing|absent|not present|no\s+\w+\s+present|none|blank|empty)\b", re.I)
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


def _synth_line(status: StatusV2, expected: str, found: str) -> str:
    if status == StatusV2.NOT_SATISFIED:
        base = f"Expected {expected or 'the check to be met'}; found {found or 'a discrepancy'}. Recommend reject or override."
    elif status == StatusV2.SATISFIED:
        base = f"Checked: {found or 'the report data'} — looks satisfied."
    elif status == StatusV2.NOT_APPLICABLE:
        base = f"Not applicable: {expected or found or 'precondition absent'}."
    elif status == StatusV2.CANNOT_EVALUATE:
        base = f"The report does not appear to contain the data needed — please check by eye."
    else:
        base = f"Expected {expected or 'a value'}; found {found or 'unclear data'}. Please verify."
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
    label when present. Order: best-located first (exact > region > page > none)."""
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
    rows.sort(key=lambda r: rank.get(r["location_quality"], 3))
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

    # suggested reject wording only survives on a NOT_SATISFIED.
    suggest = raw.get("suggest_reject_wording") or item.reject_text or packet.reject_text
    if status != StatusV2.NOT_SATISFIED:
        suggest = None

    if not _reviewer_line_ok(reviewer_line):
        reviewer_line = _synth_line(status, expected, found)

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
        bound_labels=list(item.bound_labels),
    )


def _leans_on_absent(found: str, expected: str, packet: Packet) -> bool:
    """Rule 3: a NOT_SATISFIED whose reasoning depends on an absent label is capped
    at REVIEW — the engine can't tell 'absent from the report' from 'unread'."""
    if not packet.absent_labels:
        return False
    text = f"{found} {expected}".lower()
    if _MISSING_WORDS.search(text):
        return True
    for lbl in packet.absent_labels:
        if lbl.lower() in text or lbl.replace("_", " ").lower() in text:
            return True
    return False
