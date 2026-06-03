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

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

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


# ---------------------------------------------------------------------------
# Optional LLM "why not what" judgement (opt-in, NOT in the hot QC path).
# Run as an enrichment step or on reviewer demand — never per-rule inline, so a
# slow/unavailable Ollama never blocks the engine. Returns None if unavailable.
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = (
    "You are an appraisal QC assistant. Assess the following narrative from an "
    "appraisal report. Decide two things: (1) is it SPECIFIC to this particular "
    "property/area rather than generic boilerplate, and (2) does it EXPLAIN WHY "
    "(give reasoning/causation) rather than only stating WHAT was done.\n"
    "Reply with ONLY a compact JSON object: "
    '{"specific": true|false, "explains_why": true|false, "reason": "<=20 words"}.\n\n'
    "Narrative:\n{text}\n"
)


@dataclass
class LLMJudgement:
    specific: bool
    explains_why: bool
    reason: str

    @property
    def acceptable(self) -> bool:
        return self.specific and self.explains_why


def llm_commentary_judgement(text):
    """Ask the local text model to judge specificity + 'why not what'.
    Returns an LLMJudgement, or None if the text is trivial or Ollama is down."""
    s = (text or "").strip()
    if len(s) < canned_config.min_chars:
        return None
    try:
        from app.extraction.llm_resilience import resilient_ollama_call
        raw = resilient_ollama_call(_JUDGE_PROMPT.format(text=s[:1500]), s[:1500])
    except Exception:
        return None
    if not raw:
        return None
    import json
    import re
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return LLMJudgement(
            specific=bool(d.get("specific")),
            explains_why=bool(d.get("explains_why")),
            reason=str(d.get("reason", ""))[:120],
        )
    except (ValueError, TypeError):
        return None
