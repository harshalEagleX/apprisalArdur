"""Tests for the Stage-2 LLM comprehension pass (app/qc/llm_comprehension.py).

The LLM call is always stubbed — these pin the DETERMINISTIC guardrails that make
the pass safe, and prove the rules consume the grounded facts:

  * grounding     — a fact whose quote is not literally in the narrative is dropped
  * strict schema — bad enum / bad type coerces to "drop", never a bogus field
  * no-op         — disabled, or no provider, or nothing grounded → rs unchanged
  * rule wiring   — a grounded llm_updates_described="yes" suppresses XF-AGE-UPDATES;
                    a grounded llm_trend_property_values suppresses the N-2 artifact
"""

from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc import llm_comprehension as lc


# ── narrative fixtures ────────────────────────────────────────────────────────
_MARKET = ("Property values in the neighborhood have remained stable over the past "
           "twelve months, while mortgage financing rates have increased sharply.")
_UPDATES = ("Kitchen was updated 11-15 years ago; updates include new flooring, "
            "paint, hot water heater and furnace.")


def _rs(**fields) -> ExtractionResultSet:
    rs = ExtractionResultSet(document_path="t.pdf", document_type="appraisal_report")
    for name, val in fields.items():
        rs.add(ExtractionResult(canonical_name=name, document_type="appraisal_report",
                                value=val, confidence=0.9, extraction_method="xml",
                                source_page=1))
    rs.finalize()
    return rs


# ── grounding ────────────────────────────────────────────────────────────────
def test_grounded_accepts_reformatted_substring():
    # contiguous phrase, only case/whitespace differ from the narrative
    assert lc._grounded("have REMAINED   stable", _MARKET) is True


def test_grounded_rejects_absent_quote():
    assert lc._grounded("values are declining rapidly", _MARKET) is False


def test_grounded_rejects_too_short_quote():
    assert lc._grounded("stable", _MARKET) is False  # < _MIN_QUOTE, unrelibale


# ── elided ("...") quotes — the ESMI-0048569 grounding fix ────────────────────
_LONG = ("Market values have increased gradually over the past several years in "
         "most areas ranging from 10-25% and now appear to be stabilizing.")


def test_grounded_accepts_faithful_ellipsis_elision():
    # The model elides the middle of a long span; every fragment is still on the page.
    assert lc._grounded(
        "Market values have increased gradually over the past several years ... "
        "and now appear to be stabilizing", _LONG) is True
    assert lc._grounded("Market values have increased … now appear to be stabilizing",
                        _LONG) is True


def test_grounded_rejects_ellipsis_with_hallucinated_fragment():
    # One fragment is faithful, the other is invented → still dropped (guarantee held).
    assert lc._grounded(
        "Market values have increased gradually ... and values are now collapsing",
        _LONG) is False


# ── schema coercion ──────────────────────────────────────────────────────────
def test_parse_trend_separates_value_from_rate():
    facts = lc._parse_trend({
        "property_value_trend": "stable", "property_value_quote": "remained stable",
        "financing_rate_trend": "increasing", "financing_rate_quote": "rates have increased",
        "explicit_stable_values_statement": True, "stable_values_quote": "remained stable",
    })
    assert facts["llm_trend_property_values"][0] == "stable"
    assert facts["llm_trend_financing_rates"][0] == "increasing"
    assert facts["llm_stable_values_stated"][0] == "yes"


def test_parse_trend_drops_unknown_and_bad_enum():
    facts = lc._parse_trend({
        "property_value_trend": "unknown", "financing_rate_trend": "sideways-ish",
        "explicit_stable_values_statement": False,
    })
    assert facts == {}


def test_parse_updates_emits_only_grounded_yes():
    assert lc._parse_updates({"updates_described": False, "updates_quote": ""}) == {}
    facts = lc._parse_updates({"updates_described": "true", "updates_quote": "Kitchen was updated",
                               "update_items": "flooring, paint", "update_recency": "11-15 yrs ago"})
    assert facts["llm_updates_described"][0] == "yes"
    assert facts["llm_update_recency"][0] == "11-15 yrs ago"


# ── comprehend() no-op paths ──────────────────────────────────────────────────
def test_comprehend_noop_when_disabled(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "LLM_COMPREHENSION_ENABLED", False, raising=False)
    rs = _rs(market_conditions_commentary=_MARKET)
    assert lc.comprehend(rs) is rs


def _enable(monkeypatch, chat_return):
    """Enable the pass and stub the provider + LLM call to return `chat_return`."""
    from app import config
    from app.extraction import llm_groq
    monkeypatch.setattr(config, "LLM_COMPREHENSION_ENABLED", True, raising=False)
    monkeypatch.setattr(llm_groq, "together_extraction_available", lambda: True)
    monkeypatch.setattr(llm_groq, "groq_extraction_available", lambda: False)
    calls = {"n": 0}

    def _chat(messages, **kw):
        calls["n"] += 1
        # concern id is not passed; disambiguate by which narrative is in the prompt
        user = messages[1]["content"]
        return chat_return(user)
    monkeypatch.setattr(llm_groq, "chat_json", _chat)
    return calls


def test_comprehend_emits_grounded_facts(monkeypatch):
    def _reply(user):
        if "financing" in user or "market" in user.lower() or "stable" in user.lower():
            pass
        if "Kitchen" in user:
            return {"updates_described": True, "updates_quote": "Kitchen was updated",
                    "update_items": "flooring", "update_recency": "11-15 years ago"}
        return {"property_value_trend": "stable", "property_value_quote": "remained stable",
                "financing_rate_trend": "increasing", "financing_rate_quote": "rates have increased",
                "explicit_stable_values_statement": True, "stable_values_quote": "remained stable"}
    _enable(monkeypatch, _reply)
    rs = _rs(market_conditions_commentary=_MARKET, condition_comments=_UPDATES)
    out = lc.comprehend(rs)
    assert out is not rs
    assert out.value("llm_trend_property_values") == "stable"
    assert out.value("llm_trend_financing_rates") == "increasing"
    assert out.value("llm_updates_described") == "yes"


def test_comprehend_drops_ungrounded_hallucination(monkeypatch):
    # Model claims "declining" but that phrase is NOT in the narrative → dropped.
    def _reply(user):
        return {"property_value_trend": "declining",
                "property_value_quote": "values are falling fast",
                "financing_rate_trend": "unknown",
                "explicit_stable_values_statement": False}
    _enable(monkeypatch, _reply)
    rs = _rs(market_conditions_commentary=_MARKET)
    out = lc.comprehend(rs)
    # nothing survived grounding → strict no-op (same object back)
    assert out is rs


# ── rule consumption ─────────────────────────────────────────────────────────
def test_age_updates_suppressed_by_grounded_fact():
    from app.qc.context import QCContext
    from app.qc.rules.cross_field import xf_age_updates
    from app.qc.result import RuleResult
    # eff-age far below actual, NO keyword update text, but grounded LLM says updated.
    rs = _rs(year_built="1985", effective_date="2024-06-01", effective_age="8",
             condition_comments="Overall condition is average.",
             llm_updates_described="yes")
    out = xf_age_updates(QCContext(transaction_id="t", appraisal=rs))
    statuses = [r.status.name for r in (out or []) if isinstance(r, RuleResult)]
    assert statuses == []  # suppressed — no VERIFY
