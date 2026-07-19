"""
language.narrative (nas-guard-1.0.0) — AnnexB Part 3 Stage A + the A-3 failure
ladder, as a focused guard (NOT the full addendum assembler).

The full Narrative Assembler (parse addendum pages → link blocks → assemble
canonical value with parts[]) is a separate build block. What ships here is the
part that prevents the concrete harm: judging a POINTER or a HEADER-GRAB as if it
were the narrative. When a narrative check's only value is a link/junk and no
coherent prose exists anywhere, the engine emits the A-3 REVIEW card ("the form
says 'see attached addenda' but I could not find the matching text") instead of a
NOT_SATISFIED against the appraiser.

XML-first (AnnexB Part 3 §3.1) means most orders already carry the full narrative
from MISMO, so this guard rarely fires — but it is the honest floor when it must.
"""

from __future__ import annotations

import re
from typing import List

_POINTER_RX = re.compile(
    r"\b(see\s+(attached\s+)?adden|see\s+addendum|see\s+comment|see\s+attach|"
    r"continued\s+(on|in)|refer\s+to\s+adden|as\s+per\s+adden)\w*", re.I)
_TRUNCATION_TAIL = re.compile(r"[a-z,]\s*$")  # ends mid-word/clause, no terminal punctuation
_HEADER_TOKENS = re.compile(r"^[A-Z][A-Z\s]{2,}\d{3,}", re.I)  # ALLCAPS name + street number grab
_NARRATIVE_NAME = re.compile(
    r"(comment|description|narrative|commentary|analysis|summary|boundaries|"
    r"remarks|explanation|reconcil)", re.I)
_NARRATIVE_CHECK = re.compile(
    r"(describe|description|narrative|commentary|comment|specific|substantive|"
    r"boilerplate|canned|analysis|explain|discuss|meaningful|not\s+merely)", re.I)

_MIN_PROSE = 80  # AnnexB: narrative min length; below → not usable prose


def is_narrative_label(label: str) -> bool:
    return bool(_NARRATIVE_NAME.search(label or ""))


def is_narrative_check(check_text: str) -> bool:
    return bool(_NARRATIVE_CHECK.search(check_text or ""))


def classify(text: str) -> str:
    """pointer | header_grab | truncation | prose | empty."""
    t = (text or "").strip()
    if not t:
        return "empty"
    if _POINTER_RX.search(t):
        # 2026-07-18: a "pointer" is text that is ONLY a pointer — the value stands
        # in place of the narrative. `.search()` matched ANYWHERE, so a complete
        # narrative that merely ends with the appraiser's usual courtesy
        # cross-reference ("…analyzed in the report. See attached addendum.") was
        # classified as a pointer. A-3 then short-circuited the check BEFORE the
        # judge and told the reviewer "I could not find the matching text" about
        # 1093 characters sitting right in front of them. Measured on ESMD-0002883:
        # sales_comparison_summary 1093 chars and market_conditions_commentary 264
        # chars, both real prose — EQ-87/EQ-118/EQ-120 hedged on 12/15, 9/15, 9/15
        # orders. Judge what remains once the cross-reference is removed: still
        # substantial ⇒ it is prose that happens to cite an addendum.
        residue = _POINTER_RX.sub(" ", t).strip(" .,;:—-\n\t")
        if len(residue) < _MIN_PROSE:
            return "pointer"
    if _HEADER_TOKENS.match(t) and len(t) < 60:
        return "header_grab"
    if len(t) < _MIN_PROSE and _TRUNCATION_TAIL.search(t):
        return "truncation"
    return "prose"


def is_usable_prose(text: str) -> bool:
    return classify(text) == "prose" and len((text or "").strip()) >= _MIN_PROSE


def pointer_labels(values: dict, labels: List[str]) -> List[str]:
    """Narrative labels whose value is a link/junk (pointer/header_grab/trunc)."""
    out = []
    for lbl in labels:
        if not is_narrative_label(lbl):
            continue
        v = values.get(lbl)
        if v is not None and classify(str(v)) in ("pointer", "header_grab", "truncation"):
            out.append(lbl)
    return out
