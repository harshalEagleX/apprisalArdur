"""
persistence.repo (persist-1.0.0) — SHALqc.md §15 persistence + revision diff.

Graceful no-DB path (SHALqc.md P6): when DATABASE_URL is unset or the database
is unreachable, every function is a safe no-op — the QC pipeline still runs and
returns its report; it just doesn't persist or dedup. So a laptop-less device
(the .env note: "Postgres lives on the LAPTOP") degrades cleanly instead of
crashing.

Revision handling (§15): the same order_id resubmitted with a DIFFERENT
package_hash ⇒ revision_no += 1. An IDENTICAL package_hash (same order + config
fingerprint) ⇒ the stored run is returned (`cached_run: true`, §14 G-3) without
reprocessing. `diff_findings` labels each finding new | still_open | resolved by
the (rule_id, message_key, root_field) key — a PURE function, testable without a DB.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from app.config import settings

__version__ = "persist-1.0.0"

logger = logging.getLogger(__name__)

_engine = None
_engine_ready = False
_Session = None


def _get_engine():
    """Lazy engine. Returns None (no-op mode) when no URL / DB unreachable."""
    global _engine, _engine_ready, _Session
    if _engine_ready:
        return _engine
    _engine_ready = True
    url = settings.database_url
    if not url:
        logger.info("persistence: DATABASE_URL unset — running without persistence (no-op).")
        return None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.persistence.models import Base
        # connect_timeout is a psycopg2/Postgres arg — only pass it for Postgres
        # so a SQLite/other backend (tests, dev) still connects.
        connect_args = {"connect_timeout": 2} if url.startswith("postgresql") else {}
        eng = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        Base.metadata.create_all(eng)   # JPA-style: create tables if absent (no migration runner)
        _engine = eng
        _Session = sessionmaker(bind=eng, expire_on_commit=False)
        logger.info("persistence: connected (%s)", url.split("@")[-1])
    except Exception as exc:
        logger.warning("persistence: DB unavailable (%s) — running without persistence.", exc)
        _engine = None
    return _engine


@contextmanager
def _session():
    if _get_engine() is None or _Session is None:
        yield None
        return
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def available() -> bool:
    return _get_engine() is not None


# ── revision diff (pure — no DB) ────────────────────────────────────────────

def _finding_key(f: dict) -> tuple:
    return (f.get("rule_id", ""), f.get("message_key") or "", f.get("root_field") or "")


def diff_findings(prev: List[dict], curr: List[dict]) -> Dict[str, List[dict]]:
    """Label current findings vs the prior run (§15 rpt-1.1.0).

    Returns {"new": [...], "still_open": [...], "resolved": [...]} keyed by
    (rule_id, message_key, root_field). `resolved` items come from `prev`
    (they are gone in `curr`); `new`/`still_open` come from `curr`.
    """
    prev_keys = {_finding_key(f) for f in prev}
    curr_keys = {_finding_key(f) for f in curr}
    new = [f for f in curr if _finding_key(f) not in prev_keys]
    still = [f for f in curr if _finding_key(f) in prev_keys]
    resolved = [f for f in prev if _finding_key(f) not in curr_keys]
    return {"new": new, "still_open": still, "resolved": resolved}


# ── run lookup / save (§14 G-3 + §15) ───────────────────────────────────────

def get_cached_run(order_id: str, package_hash: str) -> Optional[dict]:
    """§14 G-3: identical package (order_id + hash) already processed ⇒ return
    its stored report. None when absent or persistence is off."""
    with _session() as s:
        if s is None:
            return None
        from app.persistence.models import Run
        row = s.query(Run).filter_by(order_id=order_id, package_hash=package_hash).one_or_none()
        if row is None:
            return None
        report = dict(row.report_json or {})
        report["cached_run"] = True
        report["revision_no"] = row.revision_no
        return report


def next_revision_no(order_id: str) -> int:
    with _session() as s:
        if s is None:
            return 0
        from app.persistence.models import Run
        n = s.query(Run).filter_by(order_id=order_id).count()
        return n


def save_run(order_id: str, amc_code: str, package_hash: str, fingerprint: str,
             revision_no: int, report: dict) -> Optional[str]:
    """Persist an order+run+findings. Returns run_id, or None in no-op mode."""
    with _session() as s:
        if s is None:
            return None
        from app.persistence.models import (Finding, ItemVerdict, LLMInteraction,
                                            Order, Run)
        if s.get(Order, order_id) is None:
            s.add(Order(order_id=order_id, amc_code=amc_code))
        run_id = uuid.uuid4().hex
        s.add(Run(run_id=run_id, order_id=order_id, revision_no=revision_no,
                  package_hash=package_hash, fingerprint=fingerprint, amc_code=amc_code,
                  summary_json=report.get("summary", {}), report_json=report))

        # Store the raw LLM exchanges FIRST (item_verdicts reference them).
        for it in report.get("llm_interactions", []):
            iid = it.get("id")
            if not iid:
                continue
            s.add(LLMInteraction(
                id=iid, run_id=run_id, order_id=order_id, item_id=it.get("item_id", ""),
                call_type=it.get("call_type", ""), prompt_version=it.get("prompt_version", ""),
                batch_id=it.get("batch_id", ""), provider=it.get("provider", ""),
                model=it.get("model", ""), ms=float(it.get("ms") or 0.0),
                cached=bool(it.get("cached")), request_json=it.get("request") or {},
                response_json=it.get("response") or {}, raw_response=(it.get("raw_response") or "")[:20000]))

        for card in report.get("cards", []):
            # Language cards are per-item (have item_id) → rich ItemVerdict rows.
            if card.get("item_id"):
                s.add(ItemVerdict(
                    run_id=run_id, order_id=order_id, item_id=card["item_id"],
                    section=card.get("section", ""), card_group=card.get("group", ""),
                    status=card.get("status", ""), item_name=card.get("item_name", "") or "",
                    check_text=card.get("check_text", "") or "",
                    reject_text=card.get("reject_text") or "",
                    expected=card.get("expected", "") or "", found=card.get("found", "") or "",
                    reviewer_line=card.get("reviewer_line", "") or "",
                    suggested_wording=card.get("suggested_wording") or "",
                    confidence=float(card.get("confidence") or 0.0),
                    decided_by=card.get("decided_by", "") or "",
                    bound_by=card.get("bound_by", "") or "",
                    binder_confidence=float(card.get("binder_confidence") or 0.0),
                    evidence_json=card.get("evidence") or [],
                    primary_location=card.get("primary_location") or {},
                    llm_interaction_id=card.get("llm_interaction_id")))
            # Legacy rules-mode cards (rule_ids) keep the Finding row for the diff.
            elif card.get("rule_ids") is not None:
                s.add(Finding(run_id=run_id, rule_id=",".join(card.get("rule_ids", [])),
                              message_key="", root_field=card.get("group", ""),
                              status=card.get("status", ""), message=card.get("what_we_found", "")))
        return run_id


def get_item_verdicts(run_id: str) -> List[dict]:
    """Every per-item verdict for a run (for the Java reviewer view), each with its
    coordinates and a link to the stored LLM interaction."""
    with _session() as s:
        if s is None:
            return []
        from app.persistence.models import ItemVerdict
        rows = s.query(ItemVerdict).filter_by(run_id=run_id).all()
        return [{
            "item_id": r.item_id, "section": r.section, "group": r.card_group,
            "status": r.status, "item_name": r.item_name, "check_text": r.check_text,
            "reject_text": r.reject_text, "expected": r.expected, "found": r.found,
            "reviewer_line": r.reviewer_line, "suggested_wording": r.suggested_wording,
            "confidence": r.confidence, "decided_by": r.decided_by, "bound_by": r.bound_by,
            "binder_confidence": r.binder_confidence, "evidence": r.evidence_json,
            "primary_location": r.primary_location, "llm_interaction_id": r.llm_interaction_id,
        } for r in rows]


def get_llm_interaction(interaction_id: str) -> Optional[dict]:
    """The stored raw LLM exchange for one item (reviewer drill-in / replay)."""
    with _session() as s:
        if s is None:
            return None
        from app.persistence.models import LLMInteraction
        r = s.get(LLMInteraction, interaction_id)
        if r is None:
            return None
        return {
            "id": r.id, "run_id": r.run_id, "order_id": r.order_id, "item_id": r.item_id,
            "call_type": r.call_type, "prompt_version": r.prompt_version, "batch_id": r.batch_id,
            "provider": r.provider, "model": r.model, "ms": r.ms, "cached": r.cached,
            "request": r.request_json, "response": r.response_json, "raw_response": r.raw_response,
        }
