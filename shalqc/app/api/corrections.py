"""
api.corrections (api-1.0.0) — SHALqc.md §8/§9 reviewer feedback.

Reviewer decisions post back here and are stored per rule per field (feeds
normalizer/threshold tuning later — the learning LOOP itself is deferred, §19).
Graceful no-op when persistence is off (returns stored:false).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

__version__ = "api-1.0.0"

router = APIRouter(prefix="/corrections", tags=["corrections"])


class Correction(BaseModel):
    run_id: str
    rule_id: str
    field: str = ""
    reviewer_decision: str = ""     # accept | reject | override
    corrected_value: str = ""


@router.post("")
def post_correction(c: Correction):
    from app.persistence import repo
    from app.persistence.models import Correction as Row

    with repo._session() as s:  # noqa: SLF001 (repo-internal session, intentional)
        if s is None:
            return {"stored": False, "reason": "persistence disabled"}
        s.add(Row(run_id=c.run_id, rule_id=c.rule_id, field=c.field,
                  reviewer_decision=c.reviewer_decision, corrected_value=c.corrected_value))
    return {"stored": True}
