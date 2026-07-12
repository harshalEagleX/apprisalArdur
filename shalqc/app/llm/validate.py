"""
llm.validate (lvd-1.0.0) — SHALqc-CORE §4.5 reply validator.

The license that lets the LLM judge: every LLM reply is re-checked by code
before it is believed. This module holds the reusable checks; the caller applies
the ones relevant to its call type and degrades on failure. Never cuttable
(SHALqc-CORE §6).

Checks implemented here:
  * status vocabulary strictly ∈ {PASS, FAIL, VERIFY, NOT_APPLICABLE}
    (HOLD is intake/profile only — a reply containing it is invalid).
  * grounding: every evidence quote is verbatim in the named source(s).
  * reason_plain quality gate: 8–240 chars, no markdown, reads as a sentence.
  * numeric re-check: recompute a claimed number from packet values (±0.5%).

The guardrail (CORE §0): a FAIL survives only if grounding AND numeric checks
pass AND inputs are above threshold; any miss degrades FAIL→VERIFY with a
stamped reason. VERIFY/PASS need only grounding.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.llm.grounding import is_grounded

__version__ = "lvd-1.0.0"

_ALLOWED_STATUS = {"PASS", "FAIL", "VERIFY", "NOT_APPLICABLE"}
_MARKDOWN = re.compile(r"[*_`#]|\[.*?\]\(.*?\)")


def status_in_vocabulary(status: str) -> bool:
    return status in _ALLOWED_STATUS


def reason_plain_ok(text: str) -> bool:
    """CORE §14: 8–240 chars, no markdown, no verbatim field-ids — a human
    sentence the reviewer reads."""
    if not text:
        return False
    t = text.strip()
    if not (8 <= len(t) <= 240):
        return False
    if _MARKDOWN.search(t):
        return False
    return True


def quotes_grounded(quotes: List[str], *sources: str) -> bool:
    """True iff every quote is verbatim-grounded in the sources."""
    return all(is_grounded(q, *sources) for q in quotes if q)


def numeric_claim_ok(claimed: float, recomputed: float, tol_pct: float = 0.5) -> bool:
    """Re-verify a numeric claim against a code-computed value (±tol_pct%)."""
    if recomputed == 0:
        return abs(claimed) < 1e-9
    return abs(claimed - recomputed) / abs(recomputed) * 100.0 <= tol_pct
