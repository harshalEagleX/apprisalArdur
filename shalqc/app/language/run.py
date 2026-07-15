"""
language.run (lang-run-1.0.0) — the JUDGE_MODE=language orchestration (§2, §5, §7).

Runtime flow (final_shalqccore.md §2):
  bind checklist to labels (precompiled) → build packets → judge concurrently →
  validate replies → EVERY item becomes a reviewer card → extraction gaps to Ops.

This module is the §7 scenario matrix wired as code paths — every path has a
defined outcome, none crash, none silently pass:
  S-1  absent label the engine should have read (XML had it)  → extraction_gaps (Ops)
  S-2  junk value (plausibility already suppressed it)        → routes as S-1
  S-3  needs engagement/contract that's absent                → judge NA/REVIEW (source_notes)
  S-6  LLM unavailable / batch failed                         → REVIEW llm_unavailable, packet attached
  S-9  empty packet (no values/absent/snapshot)               → forced REVIEW empty_packet
  visual items                                                → constant Manual-visual card, no LLM
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.language import judge_v2 as J
from app.language import narrative as NAR
from app.language import validate_v2 as V
from app.language.packet_v2 import Packet, Sources, build_packet
from app.language.spec import CompiledItem
from app.language.validate_v2 import _located_evidence, _primary_location
from app.language.verdict_v2 import CARD_ORDER, JudgeVerdict, StatusV2

logger = logging.getLogger(__name__)

__version__ = "lang-run-1.0.0"


# ── extraction-gap detection (S-1 / S-2) ──────────────────────────────────────

def _extraction_gap(appraisal_fs, label: str):
    """A bound label the engine SHOULD have read but didn't: the field exists but
    was suppressed by plausibility (S-2) or read raw yet lost its value. Returns
    (is_gap, raw_value) — a genuine 'report-missing' field is NOT a gap."""
    if appraisal_fs is None:
        return False, None
    ef = appraisal_fs.get(label)
    if ef is None:
        return False, None
    if getattr(ef, "suppressed", False):
        return True, ef.raw_value or ef.value
    if ef.value is None and getattr(ef, "raw_value", None):
        return True, ef.raw_value
    return False, None


def _collect_gaps(packets: List[Packet], appraisal_fs) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    seen = set()
    for p in packets:
        for lbl in p.absent_labels:
            if lbl in seen:
                continue
            is_gap, raw = _extraction_gap(appraisal_fs, lbl)
            if is_gap:
                seen.add(lbl)
                gaps.append({"item_id": p.item_id, "label": lbl,
                             "raw": (str(raw)[:120] if raw else None),
                             "reason": "unread_or_suppressed"})
    return gaps


# ── fallbacks / precompiled cards ─────────────────────────────────────────────

def _item_fields(item: CompiledItem) -> Dict[str, Any]:
    """Shared reviewer/provenance fields every card carries, LLM-judged or not."""
    return {
        "item_name": item.item_name, "reject_text": item.reject_text,
        "bound_by": item.bound_by, "binder_confidence": item.binder_confidence,
        "bound_labels": list(item.bound_labels), "severity": item.severity,
    }


def _visual_card(item: CompiledItem) -> JudgeVerdict:
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.REVIEW, check_text=item.check_text,
        section=item.section, judgeable="visual", decided_by="precompiled",
        reviewer_line=(f"Manual visual check: {item.check_text[:180]}"
                       " — review the photos/sketch/map by eye.")[:240],
        **_item_fields(item),
    )


def _packet_fields(packet: Packet) -> Dict[str, Any]:
    """Fallback reviewer/provenance fields when only a packet is available."""
    return {"item_name": "", "reject_text": packet.reject_text,
            "bound_by": "", "binder_confidence": 0.0, "bound_labels": []}


def _fallback_card(packet: Packet, reason: str,
                   item: Optional[CompiledItem] = None) -> JudgeVerdict:
    """S-6 / S-9: never SATISFIED. Packet values (WITH coordinates) ride along so
    the reviewer can still judge by eye and the document can still auto-scroll."""
    line = ("Automated judgment was unavailable for this check — please review the "
            "values shown.") if reason == "llm_unavailable" else (
            "This check produced no data to judge — please review manually.")
    evidence = _located_evidence(packet, {})
    return JudgeVerdict(
        item_id=packet.item_id, status=StatusV2.REVIEW,
        check_text=(item.check_text if item else packet.check_text),
        section=(item.section if item else packet.scope),
        reviewer_line=line, guardrails=[reason],
        decided_by=f"fallback:{reason}", values=packet.raw_values(),
        evidence=evidence, primary_location=_primary_location(evidence),
        **(_item_fields(item) if item else _packet_fields(packet)),
    )


def _narrative_pointer_card(item: CompiledItem, packet: Packet):
    """A-3: return a REVIEW card iff this is a narrative check whose narrative
    value(s) are all pointers/junk and none is usable prose. Otherwise None."""
    if not (item.scope == "narrative" or NAR.is_narrative_check(item.check_text)):
        return None
    raw = packet.raw_values()
    labels = list(raw.keys())
    pointers = NAR.pointer_labels(raw, labels)
    if not pointers:
        return None
    has_prose = any(NAR.is_narrative_label(l) and NAR.is_usable_prose(str(raw.get(l) or ""))
                    for l in labels)
    if has_prose:
        return None
    evidence = _located_evidence(packet, {})
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.REVIEW, check_text=item.check_text,
        section=item.section, decided_by="precompiled:a3", guardrails=["narrative_pointer"],
        values=raw, evidence=evidence, primary_location=_primary_location(evidence),
        reviewer_line=("The form points to an addendum for this narrative but I could not "
                       "find the matching text — please check the addendum pages by eye.")[:240],
        **_item_fields(item),
    )


def _empty_packet(packet: Packet) -> bool:
    return (not packet.values and not packet.absent_labels
            and not packet.section_snapshot)


def _classify_cannot_evaluate(jv: JudgeVerdict, packet: Packet, appraisal_fs) -> JudgeVerdict:
    """§5 / S-1: a CANNOT_EVALUATE is source=engine (Ops tab, never blames the
    appraiser) when the missing data is one the engine failed to read; else
    source=report (reviewer checks by eye)."""
    if jv.status != StatusV2.CANNOT_EVALUATE:
        return jv
    for lbl in packet.absent_labels:
        is_gap, _raw = _extraction_gap(appraisal_fs, lbl)
        if is_gap:
            jv.source = "engine"
            return jv
    jv.source = "report"
    return jv


# ── the run ───────────────────────────────────────────────────────────────────

def _interaction(item_id: str, packet: Optional[Packet], response: Optional[dict],
                 meta: Optional[dict]) -> Dict[str, Any]:
    """One stored LLM exchange for one item: the request packet we sent, the parsed
    response, the raw model text, and the call metadata — everything needed to
    replay or audit the judgment. `id` links it from the reviewer card."""
    meta = meta or {}
    return {
        "id": uuid.uuid4().hex,
        "item_id": item_id,
        "call_type": meta.get("call_type", ""),
        "prompt_version": meta.get("prompt_version", ""),
        "batch_id": meta.get("batch_id", ""),
        "provider": meta.get("provider", ""),
        "model": meta.get("model", ""),
        "ms": meta.get("ms", 0.0),
        "cached": meta.get("cached", False),
        "request": packet.to_json() if packet is not None else None,
        "response": response,
        "raw_response": meta.get("raw_response"),
        "error": meta.get("error"),
    }


def judge_items(items: List[CompiledItem], src: Sources, appraisal_fs,
                client) -> Tuple[Dict[str, JudgeVerdict], List[Dict[str, Any]], Dict[str, Any]]:
    """Bind→packet→judge→validate for a list of compiled items. Returns
    (item_id → validated JudgeVerdict, list of stored LLM interactions, judge
    timing ledger). Visual + fallback cards are included; every judged/failed
    item gets an interaction."""
    results: Dict[str, JudgeVerdict] = {}
    interactions: List[Dict[str, Any]] = []
    packets: List[Packet] = []
    packet_by_id: Dict[str, Packet] = {}

    for item in items:
        if item.judgeable == "visual" or item.scope == "visual":
            results[item.item_id] = _visual_card(item)
            continue
        packet = build_packet(item, src)
        if _empty_packet(packet):
            results[item.item_id] = _fallback_card(packet, "empty_packet", item)
            logger.warning("language.run: empty packet for %s (S-9)", item.item_id)
            continue
        # AnnexB Part 3 A-3: a narrative check whose only value is a pointer /
        # header-grab / truncation and no coherent prose anywhere → REVIEW card,
        # never a NOT_SATISFIED against the appraiser, never sent to the judge.
        a3 = _narrative_pointer_card(item, packet)
        if a3 is not None:
            results[item.item_id] = a3
            continue
        packets.append(packet)
        packet_by_id[item.item_id] = packet

    # batch by scope/section for the concurrent judge (§8).
    by_section: Dict[str, List[Packet]] = {}
    for p in packets:
        by_section.setdefault(p.scope or "other", []).append(p)

    verdicts, failed, metas, judge_timing = J.judge_all(client, by_section)
    item_by_id = {it.item_id: it for it in items}

    for item_id, raw in verdicts.items():
        packet = packet_by_id.get(item_id)
        item = item_by_id.get(item_id)
        if packet is None or item is None:
            continue
        jv = V.validate(raw, packet, item)
        jv = _classify_cannot_evaluate(jv, packet, appraisal_fs)
        rec = _interaction(item_id, packet, raw, metas.get(item_id))
        jv.llm_interaction_id = rec["id"]
        interactions.append(rec)
        results[item_id] = jv

    for item_id in failed:
        if item_id in results:
            continue
        packet = packet_by_id.get(item_id)
        item = item_by_id.get(item_id)
        if packet is not None:
            jv = _fallback_card(packet, "llm_unavailable", item)
            # store the failed exchange too (raw model text + error) for audit.
            rec = _interaction(item_id, packet, None, metas.get(item_id))
            jv.llm_interaction_id = rec["id"]
            interactions.append(rec)
            results[item_id] = jv

    return results, interactions, judge_timing


def _card(jv: JudgeVerdict) -> Dict[str, Any]:
    return {
        "item_id": jv.item_id,
        "group": jv.card_group(),
        "section": jv.section,
        "status": jv.status.value,
        "item_name": jv.item_name,
        "check_text": jv.check_text,
        "description": jv.check_text,          # alias: the full check in the AMC's words
        "reject_text": jv.reject_text,
        "headline": _headline(jv),
        "expected": jv.expected,
        "found": jv.found,
        "reviewer_line": jv.reviewer_line,
        "evidence": jv.evidence,               # each row carries page/bbox for auto-scroll
        "primary_location": jv.primary_location,
        "values": jv.values,
        "suggested_wording": jv.suggest_reject_wording,
        "confidence": jv.confidence,
        "judgeable": jv.judgeable,
        "guardrails": jv.guardrails,
        "decided_by": jv.decided_by,
        "bound_by": jv.bound_by,
        "binder_confidence": jv.binder_confidence,
        "bound_labels": jv.bound_labels,
        "severity": jv.severity,
        "llm_interaction_id": jv.llm_interaction_id,
    }


def _headline(jv: JudgeVerdict) -> str:
    name = jv.check_text[:80]
    if jv.status == StatusV2.NOT_SATISFIED:
        return f"Recommended reject — {name}"
    if jv.status == StatusV2.REVIEW:
        return f"Please verify — {name}"
    if jv.judgeable == "visual":
        return f"Manual visual check — {name}"
    return name


def _location_metric(appraisal_fs) -> Dict[str, Any]:
    hist = {"exact": 0, "region": 0, "page": 0, "none": 0}
    total = 0
    if appraisal_fs is not None:
        for _n, ef in appraisal_fs:
            if ef.found:
                total += 1
                hist[ef.location_quality or "none"] = hist.get(ef.location_quality or "none", 0) + 1
    exact_pct = round(hist["exact"] / total * 100.0, 1) if total else 0.0
    return {"exact_pct": exact_pct, "located": hist, "total_fields": total}


def build_language_report(order_id: str, amc_code: str,
                          results: Dict[str, JudgeVerdict], appraisal_fs,
                          gaps: List[Dict[str, Any]],
                          degradations: Optional[List[str]] = None,
                          versions: Optional[Dict[str, Any]] = None,
                          interactions: Optional[List[Dict[str, Any]]] = None,
                          timings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """§5: EVERY item → a reviewer card, grouped + severity-sorted; engine gaps go
    to the Ops tab (extraction_gaps), never the reviewer queue."""
    reviewer: List[JudgeVerdict] = []
    informational: List[JudgeVerdict] = []
    ops: List[Dict[str, Any]] = list(gaps)

    for jv in results.values():
        grp = jv.card_group()
        if grp == "ops":
            ops.append({"item_id": jv.item_id, "label": None,
                        "raw": None, "reason": "cannot_evaluate_engine",
                        "check_text": jv.check_text})
        elif grp == "informational":
            # PART 1.1: no reject authority → kept for audit, never in the queue.
            informational.append(jv)
        else:
            reviewer.append(jv)

    cards = [_card(jv) for jv in reviewer]
    cards.sort(key=lambda c: (CARD_ORDER.get(c["group"], 9), c["section"], c["item_id"]))
    info_cards = [_card(jv) for jv in informational]
    info_cards.sort(key=lambda c: (c["section"], c["item_id"]))

    # counts reflect the REVIEWER queue only — informational items are excluded so
    # the summary shows what a human must actually act on (PART 1.1).
    counts = {s.value: 0 for s in StatusV2}
    manual_visual = 0
    for jv in reviewer:
        counts[jv.status.value] += 1
        if jv.judgeable == "visual":
            manual_visual += 1

    return {
        "order_id": order_id,
        "amc_code": amc_code,
        "status": "OK",
        "verdict_vocab": "v2",
        "summary": {
            "satisfied": counts[StatusV2.SATISFIED.value],
            "not_satisfied": counts[StatusV2.NOT_SATISFIED.value],
            "review": counts[StatusV2.REVIEW.value],
            "not_applicable": counts[StatusV2.NOT_APPLICABLE.value],
            "cannot_evaluate": counts[StatusV2.CANNOT_EVALUATE.value],
            "manual_visual": manual_visual,
            "extraction_gaps": len(ops),
            "informational": len(info_cards),
        },
        "cards": cards,
        "informational_cards": info_cards,
        "extraction_gaps": ops,
        "llm_interactions": interactions or [],
        "location_metric": _location_metric(appraisal_fs),
        "degradations": degradations or [],
        "versions": versions or {},
        "timings": timings or {},
    }


def run_language(order_id: str, amc_code: str, appraisal_fs, engagement_fs,
                 contract_fs, compiled_items: List[CompiledItem], client,
                 degradations: Optional[List[str]] = None,
                 versions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full language-mode judgment for one order → reviewer report."""
    import time as _time

    src = Sources.of(appraisal_fs, engagement_fs, contract_fs)
    t0 = _time.perf_counter()
    results, interactions, judge_timing = judge_items(compiled_items, src, appraisal_fs, client)
    judge_and_packet_s = _time.perf_counter() - t0

    # gaps: recompute over the packets we actually built (absent + engine-unread).
    t1 = _time.perf_counter()
    packets = [build_packet(it, src) for it in compiled_items
               if it.judgeable != "visual" and it.scope != "visual"]
    gaps = _collect_gaps(packets, appraisal_fs)
    packet_s = _time.perf_counter() - t1

    # judge_and_packet_s includes packet-building inside judge_items (bind→
    # packet→judge→validate is one pass) — judge_wall_s (from judge_all) is
    # the LLM-only portion; the remainder is packet/bind/validate overhead.
    timings = dict(judge_timing)
    timings["packet_s"] = round(packet_s, 2)
    timings["judge_and_packet_s"] = round(judge_and_packet_s, 2)

    # 2026-07-13 perf work order §3: the ledger is a release gate, not just a
    # debug tool — alert (log, for now; wire to real alerting when it exists)
    # on the two signals that mean "speed regressed" or "provider trouble",
    # rather than waiting to notice wall time crept up over a month.
    wall = timings.get("judge_wall_s", 0.0)
    slowest = timings.get("judge_slowest_call_s", 0.0)
    if slowest and wall > 2 * slowest:
        logger.warning(
            "language.run %s: judge_wall_s=%.1f > 2x judge_slowest_call_s=%.1f — "
            "concurrency/queueing regression (batches=%d, lanes may be saturated)",
            order_id, wall, slowest, timings.get("batches", 0))
    if timings.get("s6_count", 0) > 0:
        logger.warning(
            "language.run %s: %d item(s) fell back to llm_unavailable — provider trouble, "
            "not extraction/binding (retries=%d)",
            order_id, timings["s6_count"], timings.get("retries", 0))

    return build_language_report(order_id, amc_code, results, appraisal_fs, gaps,
                                 degradations=degradations, versions=versions,
                                 interactions=interactions, timings=timings)
