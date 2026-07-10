"""
Regression tests for the cross-field contradiction rules (XF-* / cross_field.py).

Each rule was proven unreachable on 5077_E_Camelback_Loop by a per-defect
execution trace; these tests pin the rule to fire on a 5077-shaped context and,
just as importantly, to stay silent on the clean / already-owned cases so it adds
no false positives:

  XF-AGE-UPDATES     eff-age 15 vs actual 37 (gap 22) + "minor repairs" narrative,
                     subject condition NOT a UAD C1-C3 code (I-9 can't reach it).
  XF-TREND-NARRATIVE property-values checkbox "Stable" vs narrative "increasing".
  XF-GRID-BLANK-ADJ  comp GLA differs from subject but the adjustment cell is BLANK
                     (comp_N_gla_adj_blank="True") rather than an explicit $0.

The tests call the rule functions directly against a synthetic QCContext, so they
pin behavior without the full extraction pipeline.
"""

from app.core.result import ExtractionResult, ExtractionResultSet
from app.qc.context import QCContext
from app.qc.result import RuleResult, RuleStatus
from app.qc.rules.cross_field import (
    xf_age_updates, xf_grid_blank_adj, xf_trend_narrative,
)


def _ctx(**fields) -> QCContext:
    """Build an appraisal-only QCContext. Each value is a (value, confidence) pair,
    or a bare string (confidence defaults to 0.97 — a clean structured read)."""
    rs = ExtractionResultSet(document_path="t.pdf", document_type="appraisal_report")
    for name, spec in fields.items():
        val, conf = spec if isinstance(spec, tuple) else (spec, 0.97)
        rs.add(ExtractionResult(
            canonical_name=name, document_type="appraisal_report",
            value=val, confidence=conf, extraction_method="llm_inference", source_page=1))
    return QCContext(transaction_id="t", appraisal=rs)


def _statuses(out):
    results = out if isinstance(out, list) else [out]
    return [r.status for r in results if isinstance(r, RuleResult)]


# ---- XF-AGE-UPDATES -------------------------------------------------------

def test_age_updates_fires_on_5077():
    """eff 15 vs actual 37, gap 22, non-UAD condition, no update narrative → VERIFY."""
    ctx = _ctx(
        year_built="1989", effective_date="07/02/2026", effective_age="15",
        subject_grid_condition_rating="Average",
        addendum_text="Subject required only minor repairs at inspection.",
    )
    out = xf_age_updates(ctx)
    assert _statuses(out) == [RuleStatus.VERIFY]
    assert "22 years" in out.message


def test_age_updates_fires_when_condition_only_in_grid():
    """The real MISMO shape: condition lives ONLY in the grid (C3), the improvements
    condition_rating is unmapped. I-9's eff-age branch (which reads the improvements
    field) can't run, so XF must NOT stand down — it owns the gap. Regression test
    for the I-9/XF hand-off leak reproduced on ESMI-0048528 (gap 26)."""
    ctx = _ctx(
        year_built="1985", effective_date="07/02/2026", effective_age="15",
        subject_grid_condition_rating="C3",  # grid populated; condition_rating absent
        addendum_text="Subject in average condition; only minor repairs noted.",
    )
    out = xf_age_updates(ctx)
    assert _statuses(out) == [RuleStatus.VERIFY]
    assert "26 years" in out.message


def test_age_updates_stands_down_only_on_improvements_field():
    """XF stands down only when the improvements condition_rating (I-9's own gate
    field) is a UAD C1-C3 — i.e. only when I-9 can actually run. A clean C2 there
    is I-9's job, so XF must not double-flag."""
    ctx = _ctx(
        year_built="1989", effective_date="07/02/2026", effective_age="15",
        condition_rating="C2",
        addendum_text="Subject required only minor repairs at inspection.",
    )
    assert xf_age_updates(ctx) == []


def test_age_updates_silent_when_updates_described():
    """A described renovation justifies the low effective age → no finding."""
    ctx = _ctx(
        year_built="1989", effective_date="07/02/2026", effective_age="15",
        subject_grid_condition_rating="Average",
        addendum_text="Kitchen and baths were fully renovated in 2022.",
    )
    assert xf_age_updates(ctx) == []


def test_age_updates_silent_when_gap_small():
    """A 4-year gap (below the 10-year threshold) is normal → no finding."""
    ctx = _ctx(
        year_built="1989", effective_date="07/02/2026", effective_age="33",
        subject_grid_condition_rating="Average", addendum_text="No updates noted.",
    )
    assert xf_age_updates(ctx) == []


# ---- XF-TREND-NARRATIVE ---------------------------------------------------

def test_trend_narrative_fires_on_stable_vs_increasing():
    ctx = _ctx(
        property_values="Stable",
        market_conditions_commentary="Neighborhood market values are increasing steadily.",
    )
    out = xf_trend_narrative(ctx)
    assert _statuses(out) == [RuleStatus.VERIFY]


def test_trend_narrative_silent_when_consistent():
    ctx = _ctx(
        property_values="Increasing",
        market_conditions_commentary="Market prices are rising across the area.",
    )
    assert xf_trend_narrative(ctx) == []


def test_trend_narrative_no_false_positive_on_improvements_prose():
    """'recent improvements to the home' is NOT a market trend — must not fire."""
    ctx = _ctx(
        property_values="Stable",
        market_conditions_commentary="The home has had recent improvements to the kitchen.",
        neighborhood_description="A stable, established residential neighborhood.",
    )
    assert xf_trend_narrative(ctx) == []


def test_trend_narrative_ignores_financing_rate_increase():
    """A financing-RATE increase in a 'stable property values' report must NOT read
    as a value uptrend. Regression test for the ESMI-0048541 false VERIFY."""
    ctx = _ctx(
        property_values="Stable",
        market_conditions_commentary=(
            "Local MLS data indicates mostly stable comparable property values "
            "within the past twelve months. Conventional, FHA, and VA financing "
            "rates have increased in recent months, slowing market activity."),
    )
    assert xf_trend_narrative(ctx) == []


def test_trend_narrative_ignores_historical_uptrend():
    """'After several years of increasing property values …' is historical framing,
    not the current trend — must not contradict a current 'Stable' checkbox (569)."""
    ctx = _ctx(
        property_values="Stable",
        market_conditions_commentary=(
            "After several years of increasing property values and inventory "
            "shortages, the market has stabilized over the last quarter."),
    )
    assert xf_trend_narrative(ctx) == []


def test_trend_narrative_suppressed_when_narrative_agrees():
    """When the narrative explicitly states the checkbox's own direction, there is
    no contradiction even if another direction word appears elsewhere."""
    ctx = _ctx(
        property_values="Stable",
        market_conditions_commentary="Property values have remained stable this year.",
    )
    assert xf_trend_narrative(ctx) == []


# ---- XF-GRID-BLANK-ADJ ----------------------------------------------------

def test_grid_blank_adj_fires_on_blank_cell():
    """Comp GLA differs from subject and the adjustment cell is BLANK → VERIFY."""
    ctx = _ctx(
        gla="1,736", comp_1_sale_price="500,000",
        comp_1_gla="1,768", comp_1_gla_adj_blank="True",
    )
    out = xf_grid_blank_adj(ctx)
    assert _statuses(out) == [RuleStatus.VERIFY]
    assert "Comp 1" in out[0].message


def test_grid_blank_adj_passes_on_explicit_zero():
    """An explicit $0 adjustment is a deliberate 'no adjustment' → PASS, not VERIFY."""
    ctx = _ctx(
        gla="1,736", comp_1_sale_price="500,000",
        comp_1_gla="1,768", comp_1_gla_adj="0",
    )
    out = xf_grid_blank_adj(ctx)
    assert _statuses(out) == [RuleStatus.PASS]


def test_grid_blank_adj_silent_when_diff_below_threshold():
    """A 10-sqft difference (below the 25-sqft threshold) is de-minimis → PASS."""
    ctx = _ctx(
        gla="1,736", comp_1_sale_price="500,000",
        comp_1_gla="1,746", comp_1_gla_adj_blank="True",
    )
    out = xf_grid_blank_adj(ctx)
    assert _statuses(out) == [RuleStatus.PASS]
