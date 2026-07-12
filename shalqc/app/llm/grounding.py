"""
llm.grounding (lvd-1.0.0) — SHALqc.md §10 / SHALqc-CORE §4.5 grounding gate.

Every LLM-cited quote must be a verbatim substring of the source page/snippet,
compared on whitespace-normalized text (so line-wrap/spacing differences don't
sink a real quote). Ungrounded quotes are dropped; a FAIL/VERIFY that loses all
its quotes is degraded (the caller does the degrade). This is the fraud-check on
the judge — the single reason "the LLM judges everything" is allowed to coexist
with "a hallucination can never reject an appraisal" (CORE §0).
"""

from __future__ import annotations

import re

__version__ = "lvd-1.0.0"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def is_grounded(quote: str, *sources: str) -> bool:
    """True iff `quote` appears verbatim (whitespace-normalized) in any source."""
    q = _norm(quote)
    if not q:
        return False
    return any(q in _norm(s) for s in sources if s)
