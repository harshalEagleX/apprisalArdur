"""
Commentary analysis — deterministic canned/specificity checks.

The QC checklist requires narrative sections to be property-specific (no canned
text), to use section headers, and to actually explain WHY not just WHAT. The
fast, deterministic signals are computed here: presence of known canned phrases,
"see 1004MC"-style deferrals, and minimum length. These power VERIFY findings
(advisory) — a reviewer confirms. A future LLM pass (mistral) can add the
"why not what" judgement on top of these signals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

# Quality-related terms whose presence in the sales-comparison commentary is a
# fast PASS for the SCA-14 quality-commentary check (avoids an LLM call).
_QUALITY_TERMS = re.compile(r"\b(quality|construction|workmanship|q[1-6]|finishes?|materials?)\b", re.I)


def quality_addressed(text) -> Optional[bool]:
    """True when the commentary plausibly addresses comparable construction
    QUALITY. Keyword fast-path first; otherwise an LLM evaluative check catches
    paraphrases ("comparables are similar in construction"). Returns None when
    there is no SUBSTANTIVE commentary to judge (blank or a stub header) — the
    caller skips rather than emitting a noise VERIFY for an extraction gap."""
    s = (text or "").strip()
    if len(s) < 40:
        return None
    if _QUALITY_TERMS.search(s):
        return True
    try:
        from app.extraction.llm_groq import assess_text
        res = assess_text(
            s,
            "Does this appraisal sales-comparison commentary address or justify the "
            "CONSTRUCTION QUALITY of the comparables — e.g. that they are similar in "
            "quality to the subject, or why no quality adjustment was warranted?",
        )
    except Exception:
        res = None
    return bool(res)

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "qc_canned_phrases.yaml"


class _CannedConfig:
    def __init__(self):
        self.reload()

    def reload(self):
        data = yaml.safe_load(open(_CONFIG)) if _CONFIG.exists() else {}
        self.canned = [p.lower() for p in data.get("canned_phrases", [])]
        self.recon_forbidden = [p.lower() for p in data.get("reconciliation_forbidden", [])]
        self.min_chars = data.get("min_commentary_chars", 40)


canned_config = _CannedConfig()


@dataclass
class CommentaryAnalysis:
    text: str
    blank: bool
    too_short: bool
    canned_hits: List[str] = field(default_factory=list)
    defers_to_form: bool = False    # "see 1004MC" / "see addendum"

    @property
    def is_clean(self) -> bool:
        return not (self.blank or self.too_short or self.canned_hits or self.defers_to_form)


def analyze_commentary(text) -> CommentaryAnalysis:
    s = (text or "").strip()
    low = s.lower()
    if not s:
        return CommentaryAnalysis(text="", blank=True, too_short=True)
    hits = [p for p in canned_config.canned if p in low]
    defers = any(d in low for d in ("see 1004mc", "see the 1004mc", "see addendum", "see attached"))
    return CommentaryAnalysis(
        text=s,
        blank=False,
        too_short=len(s) < canned_config.min_chars,
        canned_hits=hits,
        defers_to_form=defers,
    )


def reconciliation_forbidden_terms(text) -> List[str]:
    low = (text or "").lower()
    return [t for t in canned_config.recon_forbidden if t in low]


# Commentary quality is judged deterministically above (canned-phrase + specificity
# checks). An earlier optional local-LLM "why not what" judge was removed — it had
# no callers and the deterministic checks are the source of truth.
