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

# AUTO_PASS confidence floor: a rejectable item that came back SATISFIED below this
# judge confidence should not let an order auto-complete without a human. Surfaced in
# the summary; the Java roll-up applies it only when auto-pass is enabled.
AUTO_PASS_CONF_FLOOR = 0.8


# ── extraction-gap detection (S-1 / S-2) ──────────────────────────────────────

def _extraction_gap(appraisal_fs, label: str):
    """S-1: a bound label the engine SHOULD have read but didn't — the AUTHORITATIVE
    XML carried the value yet it was suppressed by plausibility (S-2) or read raw and
    nulled. Returns (is_gap, raw_value).

    NOT a gap (so the Ops tab stays signal, not noise):
      * the field was never extracted at all (`get()` is None) — a genuine
        report-missing field;
      * the lost value was a weak PDF/checkbox/acroform GUESS (source != xml) that
        plausibility correctly rejected — that is the system working, and it is also
        how a FEATURE-ABSENT field looks (no basement → "outside entry" checkbox never
        truly set), which is NOT_PRESENT, not an engine miss.
    """
    if appraisal_fs is None:
        return False, None
    ef = appraisal_fs.get(label)
    if ef is None:
        return False, None
    from app.extraction.result import Source
    if getattr(ef, "source", None) not in (Source.XML, Source.XML.value):
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
        reviewer_line=(f"Could you please look at the photos/sketch/map for this one? "
                       f"The check: {item.check_text[:160]}")[:240],
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
    line = ("We couldn't finish the automated judgment for this check — the values "
            "we did read are shown here. Could you please review them and decide?"
            ) if reason == "llm_unavailable" else (
            "We couldn't find any data for this check in the documents — could you "
            "please look it up in the report directly?")
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


_PHOTO_NOTE = "Could you also take a look at the photo(s)/sketch for this check?"


def _mark_photo_verification(jv: JudgeVerdict, item: CompiledItem) -> JudgeVerdict:
    """Flag a judged card whose check ALSO depends on photos/sketch (user directive
    2026-07-18).

    A check can carry both scopes — "verify condition rating matches the photos",
    "photos of all outbuildings are required". Forcing it wholly to `visual` throws
    away a working automated check; leaving it wholly to the judge lets a machine
    assert what an image shows. So the text aspect is judged and reported as
    normal, and the reviewer is told, on the same card, to confirm the image by eye.
    Already-visual items are untouched — their whole card is the instruction.
    """
    from app.language.packet_v2 import _has_photo_aspect

    if item.judgeable == "visual" or not _has_photo_aspect(item):
        return jv
    jv.photo_verification_required = True
    line = (jv.reviewer_line or "").strip()
    if _PHOTO_NOTE.lower() not in line.lower():
        # keep the card inside the validator's 8-240 char reviewer_line contract
        jv.reviewer_line = f"{line} {_PHOTO_NOTE}".strip()[:240] if line else _PHOTO_NOTE
    return jv


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
    # A3 is only for a narrative whose ONLY content is a pointer ("See addendum").
    # If the packet also carries a present, non-pointer STRUCTURED value (e.g. EQ-72's
    # heating grid cells "FWA/Central" for the subject and every comp), the check is
    # judgeable on those — A3 must not pre-empt it to REVIEW. Was a false positive on
    # every order that points its heating/HVAC narrative to an addendum.
    from app.language.hints import _is_nullish
    non_pointer_present = any(
        l not in pointers and str(raw.get(l) or "").strip()
        and not _is_nullish(str(raw.get(l) or ""))
        for l in labels)
    if non_pointer_present:
        return None
    evidence = _located_evidence(packet, {})
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.REVIEW, check_text=item.check_text,
        section=item.section, decided_by="precompiled:a3", guardrails=["narrative_pointer"],
        values=raw, evidence=evidence, primary_location=_primary_location(evidence),
        reviewer_line=("The form points to an addendum for this narrative but we couldn't "
                       "find the matching text — could you please check the addendum pages for it?")[:240],
        **_item_fields(item),
    )


def _empty_packet(packet: Packet) -> bool:
    return (not packet.values and not packet.absent_labels
            and not packet.section_snapshot)


def _trigger_not_fired(packet: Packet) -> bool:
    """P3: a DETERMINISTIC pre-gate for an authored `conditional` check. "Absence is
    a value" (doctrine rule 8): if EVERY condition label is absent or nullish, the
    trigger provably did NOT fire, so the check is NOT_APPLICABLE — decided in code,
    never sent to the LLM (removes the per-order NA/REVIEW inconsistency the judge
    produced on the same trigger). A single present, non-nullish condition value is
    left to the judge (it may be value-conditioned, e.g. 'if Refinance')."""
    if not packet.conditional:
        return False
    cond = packet.conditional.get("condition_labels") or []
    if not cond:
        return False
    from app.language.hints import _is_nullish
    for lbl in cond:
        entry = packet.values.get(lbl)
        if entry is None:
            continue
        v = entry.get("v")
        if v in (None, "") or _is_nullish(v):
            continue
        return False   # a real condition value present → let the judge decide
    return True        # all condition labels absent/nullish → trigger did not fire


def _form_not_applicable(item: CompiledItem, src: Sources) -> bool:
    """Phase 1 form-aware N/A: True iff the detected form is KNOWN to the registry
    AND every label this check binds to is registry-recorded as absent on that form
    (e.g. a `unit_number` check on a 1-unit detached 1004). The registry decides
    applicability, not the LLM. Fail-safe: unknown form, no labels, or any label not
    positively-absent → False (never a guessed N/A)."""
    from app.registry import registry
    form_type = src.appraisal.value("form_type") if src.appraisal is not None else None
    if not form_type or not registry.known_form(str(form_type)):
        return False
    labels = item.all_labels
    if not labels:
        return False
    return all(registry.is_absent_on_form(lbl, str(form_type)) for lbl in labels)


def _transaction_not_applicable(item: CompiledItem, src: Sources) -> bool:
    """Transaction-aware N/A: the CONTRACT section concerns the pending SALE contract
    (price, date, seller-is-owner data source, financial assistance) — a REFINANCE has
    no sale, so every contract-section check is structurally not applicable. Decided in
    code, section-driven (no per-item list to maintain). Fail-safe: unknown/absent
    transaction type → False (never a guessed N/A)."""
    if item.section != "contract":
        return False
    ap = src.appraisal
    if ap is None:
        return False
    tt = ap.value("transaction_type") or ap.value("assignment_type")
    return "refinance" in str(tt or "").lower()


def _transaction_na_card(item: CompiledItem) -> JudgeVerdict:
    """Deterministic NOT_APPLICABLE for a contract-section check on a refinance."""
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.NOT_APPLICABLE, check_text=item.check_text,
        section=item.section, decided_by="precompiled:transaction_gate",
        guardrails=["refinance_no_contract"],
        reviewer_line=("Not applicable — this is a refinance, so there is no sales "
                       "contract for this section to check.")[:240],
        **_item_fields(item),
    )


def _form_na_card(item: CompiledItem, form_type: str) -> JudgeVerdict:
    """Deterministic NOT_APPLICABLE for a check whose field(s) do not exist on the
    detected form — no packet, no LLM."""
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.NOT_APPLICABLE, check_text=item.check_text,
        section=item.section, decided_by="precompiled:form_gate",
        guardrails=["field_absent_on_form"],
        reviewer_line=(f"Not applicable on this form ({form_type}) — the field(s) this "
                       "check needs do not exist on it.")[:240],
        **_item_fields(item),
    )


def _not_applicable_card(item: CompiledItem, packet: Packet) -> JudgeVerdict:
    """P3: the deterministic NOT_APPLICABLE card for a trigger that did not fire —
    packet values (with coordinates) ride along so the reviewer can still see why."""
    evidence = _located_evidence(packet, {})
    cond = ", ".join((packet.conditional or {}).get("condition_labels") or []) or "the trigger"
    return JudgeVerdict(
        item_id=item.item_id, status=StatusV2.NOT_APPLICABLE, check_text=item.check_text,
        section=item.section, decided_by="precompiled:trigger_gate",
        guardrails=["trigger_not_fired"], values=packet.raw_values(),
        evidence=evidence, primary_location=_primary_location(evidence),
        reviewer_line=(f"The condition that would make this check apply ({cond}) is not "
                       "present in the report — not applicable.")[:240],
        **_item_fields(item),
    )


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
        # Phase 1: form-aware N/A — a check whose field(s) don't exist on the
        # detected form is decided by the registry, before any packet/LLM work.
        if _form_not_applicable(item, src):
            results[item.item_id] = _form_na_card(item, str(src.appraisal.value("form_type")))
            continue
        # Transaction-aware N/A — a contract-section check on a refinance has no sale
        # contract to evaluate; decided in code before any packet/LLM work.
        if _transaction_not_applicable(item, src):
            results[item.item_id] = _transaction_na_card(item)
            continue
        packet = build_packet(item, src)
        if _empty_packet(packet):
            results[item.item_id] = _fallback_card(packet, "empty_packet", item)
            logger.warning("language.run: empty packet for %s (S-9)", item.item_id)
            continue
        # P3: deterministic trigger gate — an authored conditional whose condition
        # labels are all absent/nullish provably did NOT fire → NOT_APPLICABLE in
        # code, no LLM call (removes the per-order NA/REVIEW inconsistency).
        if _trigger_not_fired(packet):
            results[item.item_id] = _not_applicable_card(item, packet)
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

    # B3: self-consistency re-judges only decisive auto-outcomes when N>1 (default
    # 1 = a single pass == plain judge_all, no extra cost). Contains gpt-oss-120b's
    # run-to-run flips by forcing any non-unanimous auto-decision to REVIEW.
    from app.config import settings
    verdicts, failed, metas, judge_timing = J.judge_all_consistent(
        client, by_section, n=settings.judge_self_consistency_n)
    item_by_id = {it.item_id: it for it in items}

    for item_id, raw in verdicts.items():
        packet = packet_by_id.get(item_id)
        item = item_by_id.get(item_id)
        if packet is None or item is None:
            continue
        jv = V.validate(raw, packet, item)
        jv = _classify_cannot_evaluate(jv, packet, appraisal_fs)
        jv = _mark_photo_verification(jv, item)
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

    # Per-order token usage: a batch call's tokens are shared by every item in it,
    # so sum over DISTINCT batch metas (by identity) to count each real call once.
    judge_timing["usage"] = _judge_usage(metas)
    return results, interactions, judge_timing


# gpt-oss-120b serverless pricing (Together, 2026): $/1M tokens. Kept here as the
# authoritative source; the Java side mirrors it for the persisted cost column.
_PRICE_IN_PER_MTOK = 0.15
_PRICE_OUT_PER_MTOK = 0.60


def _judge_usage(metas: Dict[str, Any]) -> Dict[str, Any]:
    seen = set()
    prompt = completion = calls = 0
    for meta in metas.values():
        if meta is None or id(meta) in seen:
            continue
        seen.add(id(meta))
        pt = int(meta.get("prompt_tokens", 0) or 0)
        ct = int(meta.get("completion_tokens", 0) or 0)
        if pt or ct:
            calls += 1
        prompt += pt
        completion += ct
    cost = round(prompt / 1_000_000 * _PRICE_IN_PER_MTOK
                 + completion / 1_000_000 * _PRICE_OUT_PER_MTOK, 6)
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion, "billed_calls": calls,
            "cost_usd": cost, "model": _judge_model()}


def _judge_model() -> str:
    try:
        from app.config import settings
        return settings.together_model
    except Exception:
        return ""


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
        # the check also depends on photos/sketch the judge cannot see — the
        # reviewer confirms those by eye (reviewer_line carries the same note).
        "photo_verification_required": jv.photo_verification_required,
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
            # P6 (user direction 2026-07-16): EVERYTHING reviewer-facing — bound AND
            # unbound. There is no admin who reviews the dictionary/checks; admins only
            # set up the platform. So an "unauthored" (unbindable) check is NOT siphoned
            # to a separate backlog — it stays in the reviewer queue as its own group
            # (see verdict_v2.card_group) and still counts as review (blocks auto-pass).
            reviewer.append(jv)

    cards = [_card(jv) for jv in reviewer]
    cards.sort(key=lambda c: (CARD_ORDER.get(c["group"], 9), c["section"], c["item_id"]))
    info_cards = [_card(jv) for jv in informational]
    info_cards.sort(key=lambda c: (c["section"], c["item_id"]))

    # counts reflect the REVIEWER queue only — informational items are excluded so
    # the summary shows what a human must actually act on (PART 1.1).
    counts = {s.value: 0 for s in StatusV2}
    manual_visual = 0
    # P7: system-degradation cards (LLM unavailable / empty packet) — surfaced as a
    # distinct count so the reviewer/UI can section them off, though they remain in
    # `review` above so the order still cannot auto-complete without a human.
    needs_data = 0
    # P6: unbindable checks stay IN the reviewer queue (counted as review) but are
    # surfaced as their own count so the UI can section them as "weakly bound".
    unauthored = 0
    # AUTO_PASS confidence floor (Gap 1 fix): a SATISFIED on a REJECTABLE item decided
    # with low judge confidence is exactly the false-SATISFIED that would auto-complete
    # an order with zero human eyes. Surface the count so the Java roll-up can downgrade
    # AUTO_PASS → TO_VERIFY when auto-pass is enabled. Non-rejectable/high-confidence
    # passes do not arm the floor.
    low_conf_rejectable_pass = 0
    for jv in reviewer:
        counts[jv.status.value] += 1
        if jv.judgeable == "visual":
            manual_visual += 1
        grp = jv.card_group()
        if grp == "needs_data":
            needs_data += 1
        elif grp == "unauthored":
            unauthored += 1
        if (jv.status == StatusV2.SATISFIED and jv.severity == "rejectable"
                and (jv.confidence or 0.0) < AUTO_PASS_CONF_FLOOR):
            low_conf_rejectable_pass += 1

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
            "needs_data": needs_data,
            "extraction_gaps": len(ops),
            "informational": len(info_cards),
            "unauthored": unauthored,
            "rejectable_satisfied_low_conf": low_conf_rejectable_pass,
            # P9 (F10): a single authoritative, self-reconciling count so a report
            # header and this summary can never disagree. INVARIANTS (asserted in
            # tests): the five status counts above sum to `queue_items`; and
            # `total_items` (every checklist item judged) == queue_items +
            # informational + engine-cannot-evaluate items. The status counts are
            # QUEUE-ONLY by design — a section header should quote `total_items`
            # rather than re-derive its own "all checks" figure and disagree.
            "queue_items": len(cards),
            "total_items": len(results),
        },
        "cards": cards,
        "informational_cards": info_cards,
        "extraction_gaps": ops,
        "llm_interactions": interactions or [],
        "location_metric": _location_metric(appraisal_fs),
        # Per-order LLM token usage + $ cost (the reviewer-visible "what did this
        # document cost" figure surfaced in DocStats). Pulled out of timings so
        # it is a first-class report field the Java persist layer maps directly.
        "usage": (timings or {}).get("usage", {}),
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

    usage = timings.get("usage") or {}
    if usage:
        logger.info(
            "language.run %s: LLM usage — %d prompt + %d completion = %d tokens "
            "across %d billed call(s), cost $%.4f (%s)",
            order_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0), usage.get("billed_calls", 0),
            usage.get("cost_usd", 0.0), usage.get("model", ""))

    return build_language_report(order_id, amc_code, results, appraisal_fs, gaps,
                                 degradations=degradations, versions=versions,
                                 interactions=interactions, timings=timings)
