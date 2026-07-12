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
        from app.persistence.models import Finding, Order, Run
        if s.get(Order, order_id) is None:
            s.add(Order(order_id=order_id, amc_code=amc_code))
        run_id = uuid.uuid4().hex
        s.add(Run(run_id=run_id, order_id=order_id, revision_no=revision_no,
                  package_hash=package_hash, fingerprint=fingerprint, amc_code=amc_code,
                  summary_json=report.get("summary", {}), report_json=report))
        for card in report.get("cards", []):
            s.add(Finding(run_id=run_id, rule_id=",".join(card.get("rule_ids", [])),
                          message_key="", root_field=card.get("group", ""),
                          status=card.get("status", ""), message=card.get("what_we_found", "")))
        return run_id
