"""Stage-2 LLM comprehension pass — reads narrative PROSE into STRUCTURED FACTS.

This runs between extraction/overlays and QCContext construction (transaction.py).
For each narrative concern it asks the LLM one question that converts prose into a
small, fixed JSON object of *facts* (never verdicts), then writes each grounded
fact as a new ``llm_*`` canonical field the rules read. It exists to fix readings
the keyword regexes cannot: separating "financing RATES increased" from "property
VALUES increased", or recognising a paraphrased "kitchen was gutted in 2019" as a
described update.

Four guardrails keep it safe (CLAUDE.md §17 — the LLM never decides; P-14a — LLM
output is worthless unless validated back against the source text):

  1. Grounding    — every fact must cite a ``quote`` that literally appears in the
                    source narrative; a fact whose quote is not found is discarded.
  2. Strict JSON  — the model must return the exact schema/enum; malformed → dropped,
                    the field stays absent and the rule uses its keyword path.
  3. Confidence   — "unknown" / unquotable facts are not emitted, so the rule falls
                    back (→ VERIFY) rather than being silently PASSed.
  4. Determinism  — reasoning_effort=low + the existing content-hash cache in
                    llm_groq.chat_json, so the same report yields the same reading.

The pass emits ONLY ``llm_*`` fact fields — never a RuleStatus. It is a strict
no-op when ``LLM_COMPREHENSION_ENABLED`` is off or no provider is configured, so
behaviour then is identical to today's deterministic keyword path (P-6/P-7).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A grounded fact is emitted at this confidence — high enough for a rule to prefer
# it over the keyword guess, low enough that it never reaches an auto-accept gate.
_CONF = 0.6
_METHOD = "llm_comprehension"
_MIN_NARRATIVE = 40      # chars — below this there is nothing worth a model call
_MIN_QUOTE = 8           # chars — a quote shorter than this cannot ground anything

# A validated fact: the normalized value to store, and the verbatim quote that must
# be found in the source narrative for the fact to survive grounding.
Fact = Tuple[str, str]


# ── grounding ────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """Lowercase and collapse whitespace/punctuation so a model quote can be matched
    against the narrative even after trivial reformatting (quotes never survive OCR
    verbatim, but their words do)."""
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", (s or "").lower())).strip()


def _grounded(quote: str, narrative: str) -> bool:
    """True when `quote` is found — verbatim — in `narrative` (both normalized).
    This is the P-14a check: an LLM claim the model cannot quote from the page is
    a hallucination and is thrown away.

    A quote that elides a long span with an ellipsis ("Market values have increased
    ... and now appear to be stabilizing") is a normal, faithful model behaviour, but
    it is not a *contiguous* substring — so we split on the ellipsis and require EACH
    substantive fragment to appear on the page. This grounds a faithful multi-span
    quote (fixing correct facts silently dropped on long narratives, e.g. ESMI-0048569)
    while a hallucinated fragment still fails — the guarantee is unchanged, only the
    contiguity assumption is relaxed."""
    hay = _norm(narrative)
    # Fragments long enough to verify (short connectives were never trusted — see
    # _MIN_QUOTE); at least one such fragment must exist and every one must ground.
    fragments = [_norm(f) for f in re.split(r"\.{2,}|…", quote or "")]
    checked = [f for f in fragments if len(f) >= _MIN_QUOTE]
    if not checked:
        return False
    return all(f in hay for f in checked)


def _as_enum(v, allowed: Tuple[str, ...]) -> str:
    """Coerce a model value to one of `allowed`, else '' (dropped)."""
    s = str(v or "").strip().lower()
    return s if s in allowed else ""


def _as_bool(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    return None


# ── concern definitions ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Concern:
    id: str
    source_fields: Tuple[str, ...]
    system: str
    user: Callable[[str], str]          # narrative -> user prompt
    parse: Callable[[dict], Dict[str, Fact]]  # model json -> {field: (value, quote)}


_TREND_ENUM = ("increasing", "stable", "declining", "unknown")


def _parse_trend(data: dict) -> Dict[str, Fact]:
    out: Dict[str, Fact] = {}
    pv = _as_enum(data.get("property_value_trend"), _TREND_ENUM)
    if pv and pv != "unknown":
        out["llm_trend_property_values"] = (pv, str(data.get("property_value_quote") or ""))
    fr = _as_enum(data.get("financing_rate_trend"), _TREND_ENUM)
    if fr and fr != "unknown":
        out["llm_trend_financing_rates"] = (fr, str(data.get("financing_rate_quote") or ""))
    if _as_bool(data.get("explicit_stable_values_statement")) is True:
        out["llm_stable_values_stated"] = ("yes", str(data.get("stable_values_quote") or ""))
    return out


def _parse_updates(data: dict) -> Dict[str, Fact]:
    out: Dict[str, Fact] = {}
    # Only a grounded YES is emitted — it SUPPRESSES a false "no-updates" VERIFY.
    # A NO/unknown is intentionally not emitted: the rule's default already VERIFYs
    # when its keyword scan finds nothing, which is the correct conservative outcome.
    if _as_bool(data.get("updates_described")) is True:
        quote = str(data.get("updates_quote") or "")
        out["llm_updates_described"] = ("yes", quote)
        items = str(data.get("update_items") or "").strip()
        if items:
            out["llm_update_items"] = (items, quote)
        recency = str(data.get("update_recency") or "").strip()
        if recency:
            out["llm_update_recency"] = (recency, quote)
    return out


_CONCERNS: List[_Concern] = [
    _Concern(
        id="market_trend",
        source_fields=("market_conditions_commentary", "neighborhood_description", "addendum_text"),
        system=(
            "You read one appraisal market-conditions narrative and report FACTS about "
            "it as JSON. You never judge quality or pass/fail. Distinguish the trend in "
            "property VALUES from the trend in mortgage/financing RATES — they are often "
            'opposite. Return ONLY this JSON: {"property_value_trend": '
            '"increasing|stable|declining|unknown", "property_value_quote": "<verbatim '
            'phrase from the narrative, or empty>", "financing_rate_trend": '
            '"increasing|stable|declining|unknown", "financing_rate_quote": "<verbatim>", '
            '"explicit_stable_values_statement": true|false, "stable_values_quote": '
            '"<verbatim>"}. Every non-unknown value MUST include a short quote copied '
            "verbatim from the narrative. If the narrative does not state something, use "
            '"unknown"/false and an empty quote. Invent nothing.'
        ),
        user=lambda n: f"Narrative:\n{n[:4000]}\n\nReturn the JSON.",
        parse=_parse_trend,
    ),
    _Concern(
        id="updates",
        source_fields=("condition_comments", "improvements_comments",
                       "addendum_text", "sales_comparison_summary"),
        system=(
            "You read appraisal condition/improvements narrative and report FACTS as "
            "JSON. You never judge quality or pass/fail. Decide whether the appraiser "
            "DESCRIBES updates/renovations/remodeling to the subject (kitchen, bath, "
            "roof, HVAC, flooring, windows, etc.), even if paraphrased. Return ONLY this "
            'JSON: {"updates_described": true|false, "updates_quote": "<verbatim phrase '
            'naming the update, or empty>", "update_items": "<short list, or empty>", '
            '"update_recency": "<e.g. \'11-15 yrs ago\', or empty>"}. If updates_described '
            "is true it MUST include a verbatim quote from the narrative. Invent nothing."
        ),
        user=lambda n: f"Narrative:\n{n[:4000]}\n\nReturn the JSON.",
        parse=_parse_updates,
    ),
]


# ── entry point ──────────────────────────────────────────────────────────────
def comprehend(rs, dtype: str = "appraisal_report"):
    """Augment an ExtractionResultSet with grounded ``llm_*`` fact fields.

    Returns `rs` unchanged (no-op) when disabled, when no LLM provider is
    configured, or when nothing survives grounding — so a rule that reads an
    ``llm_*`` field simply sees it absent and uses its deterministic fallback."""
    from app import config
    if not getattr(config, "LLM_COMPREHENSION_ENABLED", False):
        return rs
    from app.extraction import llm_groq
    if not (llm_groq.together_extraction_available() or llm_groq.groq_extraction_available()):
        logger.debug("LLM comprehension skipped — no provider configured")
        return rs

    from app.core.result import ExtractionResult, ExtractionResultSet

    existing = {name: r for name, r in rs}

    def _val(name: str) -> str:
        r = existing.get(name)
        return str(r.value) if (r is not None and r.value) else ""

    emitted: Dict[str, str] = {}
    for concern in _CONCERNS:
        narrative = " ".join(_val(f) for f in concern.source_fields).strip()
        if len(narrative) < _MIN_NARRATIVE:
            continue
        try:
            data = llm_groq.chat_json(
                [{"role": "system", "content": concern.system},
                 {"role": "user", "content": concern.user(narrative)}],
                reasoning_effort="low", max_tokens=500,
            )
        except Exception as exc:  # P-6: any failure degrades to the keyword path
            logger.debug("LLM comprehension '%s' failed (%s)", concern.id, exc)
            continue
        if not isinstance(data, dict):
            continue
        try:
            facts = concern.parse(data)
        except Exception as exc:
            logger.debug("LLM comprehension '%s' parse failed (%s)", concern.id, exc)
            continue
        for field_name, (value, quote) in facts.items():
            if not value:
                continue
            if not _grounded(quote, narrative):
                logger.debug("LLM comprehension dropped ungrounded fact %s=%r (concern %s)",
                             field_name, value, concern.id)
                continue
            existing[field_name] = ExtractionResult(
                canonical_name=field_name, document_type=dtype, value=value,
                raw_source_text=quote, extraction_method=_METHOD, confidence=_CONF,
                source_page=0, normalization_applied=[_METHOD], hallucination_flag=False,
            )
            emitted[field_name] = value

    if not emitted:
        return rs
    logger.info("LLM comprehension emitted %d grounded fact(s): %s",
                len(emitted), {k: emitted[k] for k in sorted(emitted)})
    merged = ExtractionResultSet(
        document_path=rs.document_path, document_type=dtype,
        total_pages=rs.total_pages, ocr_method=rs.ocr_method,
    )
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged
