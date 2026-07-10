"""
Cross-field contradiction rules (XF-* series).

Every other rule module checks ONE field for presence/format. These rules compare
field A against field B (often across sections) — the false-negative class that
single-field checks structurally cannot see. Each was proven unreachable on
5077_E_Camelback_Loop by a per-defect execution trace:

  XF-AGE-UPDATES     effective-age-vs-actual-age gap with a "no updates" narrative.
                     I-9 (improvements.py) already checks this, but ONLY when the
                     subject condition is a clean UAD C1-C3 code. When the condition
                     is missing or non-UAD (e.g. "Average", which the plausibility
                     gate nulls), I-9's guard is False and the gap is never examined.
                     XF-AGE-UPDATES fills exactly that gap — it fires only when I-9
                     cannot, so the two never double-flag.

  XF-TREND-NARRATIVE the page-1 property-values trend checkbox vs the trend the
                     narrative actually asserts. N-2 (neighborhood.py) compares the
                     checkbox against mca_trend_* fields that NO extraction layer
                     populates (a dead wire), and never reads the narrative where
                     "increasing"/"declining" actually lives.

  XF-GRID-BLANK-ADJ  a comp whose GLA differs from the subject but whose GLA
                     adjustment cell is BLANK (not $0). xml_extractor._set_amount
                     now records that blank state on comp_N_gla_adj_blank instead of
                     collapsing "blank" / "not extracted" / "$0" into one NOT_FOUND.

All three:
  • may only emit PASS or VERIFY (judgment-adjacent — never an autonomous FAIL);
  • read every threshold from qc_config.semantic() (P-4);
  • are additive — they touch no existing rule and no existing extracted field, so
    they cannot regress the current PASS/FAIL/VERIFY counts, only add VERIFYs.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.qc import matching
from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.registry import rule
from app.qc.result import RuleResult, RuleStatus

_MAX_COMPS = 9

# Subject condition ratings I-9 already owns the effective-age check for. When the
# subject condition is one of these, XF-AGE-UPDATES stands down so the two rules
# never both flag the same file (I-9 keeps the richer C1-C3 reasoning).
_I9_OWNED_CONDITIONS = {"C1", "C2", "C3"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _num(val) -> Optional[float]:
    """Parse a numeric string ('1,768', '$32', '1736 sf') to float, else None."""
    if val is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(val))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _int(val) -> Optional[int]:
    n = _num(val)
    return int(n) if n is not None else None


def _res(rule_id: str, num: str, section: str, status: RuleStatus, **kw) -> RuleResult:
    return RuleResult(rule_id=rule_id, checklist_num=num, section=section,
                      status=status, **kw)


def _i9_owned_condition(ctx: QCContext) -> str:
    """The condition field I-9's effective-age branch ACTUALLY gates on — the
    improvements-section `condition_rating`, NOT the grid column. XF-AGE-UPDATES
    stands down only when this is a clean UAD C1-C3 code, i.e. exactly when I-9 can
    run, so the two never both stand down.

    Why this field and not the grid: the MISMO XML populates only
    `subject_grid_condition_rating`, never the improvements `condition_rating`. If
    XF deferred on the grid field (which reads "C3") while I-9 gates on the
    improvements field (which reads ""), both stand down and a real effective-age
    gap goes unflagged (reproduced on ESMI-0048528 gap 26 / ESMI-0048541 gap 18).
    Matching I-9's own gate field closes that hand-off leak: on XML reports XF —
    the grid-aware rule — correctly owns the check."""
    return (ctx.appraisal.value("condition_rating") or "").strip().upper()


def _narrative_blob(ctx: QCContext, fields) -> str:
    return " ".join(str(ctx.appraisal.value(f) or "") for f in fields).lower()


# ---------------------------------------------------------------------------
# XF-AGE-UPDATES — effective age far below actual age, narrative shows no updates
# ---------------------------------------------------------------------------

_UPDATE_SIGNAL = re.compile(
    r"remodel|renovat|updat|upgrad|gutted|replaced|rehab|refurbish|modern|"
    r"new\s+(kitchen|bath|roof|hvac|floor|window|appliance)",
    re.I)

_AGE_NARRATIVE_FIELDS = (
    "addendum_text", "market_conditions_commentary", "sales_comparison_summary",
    "neighborhood_description", "condition_comments", "improvements_comments",
)


@rule(id="XF-AGE-UPDATES", num="XF-age-updates", section="improvements", phase=4,
      severity="advisory", name="Effective age vs actual age vs update narrative")
def xf_age_updates(ctx: QCContext):
    """VERIFY when the effective age is well below the actual age (implying updates)
    but the narrative describes none — and I-9 could not examine it because the
    subject condition is not a clean UAD C1-C3 code."""
    if not ctx.appraisal.present:
        return []
    if _i9_owned_condition(ctx) in _I9_OWNED_CONDITIONS:
        return []  # I-9 can run on this case — stand down to avoid a double flag

    yb = matching.year_of(ctx.appraisal.value("year_built"))
    eff_year = matching.year_of(ctx.appraisal.value("effective_date"))
    eff_age = _int(ctx.appraisal.value("effective_age"))
    if not (yb and eff_year and eff_age is not None):
        return []
    actual = eff_year - yb
    gap = actual - eff_age
    min_gap = int(qc_config.semantic("xf_effage_gap_years", 10))
    if actual <= 5 or gap < min_gap:
        return []

    # Stage-2 comprehension: a grounded "updates described" fact (recognises
    # paraphrased updates the keyword regex misses) justifies the low effective
    # age. Absent (LLM off / ungrounded) → falls through to the keyword scan below.
    if (ctx.appraisal.value("llm_updates_described") or "").lower() == "yes":
        return []

    narrative = _narrative_blob(ctx, _AGE_NARRATIVE_FIELDS)
    if _UPDATE_SIGNAL.search(narrative):
        return []  # the low effective age is justified by described updates

    return _res(
        "XF-AGE-UPDATES", "XF-age-updates", "improvements", RuleStatus.VERIFY,
        message=qc_config.template("XF-age-updates", eff=eff_age, actual=actual, gap=gap),
        fields_involved=["effective_age", "year_built", "effective_date"],
        template_id="XF-age-updates", confidence=0.7, finding_type="manual_verify",
        evidence=[ctx.appraisal.evidence("effective_age"),
                  ctx.appraisal.evidence("year_built"),
                  ctx.appraisal.evidence("effective_date")])


# ---------------------------------------------------------------------------
# XF-TREND-NARRATIVE — page-1 trend checkbox contradicts the narrative
# ---------------------------------------------------------------------------

_TREND_NARRATIVE_FIELDS = (
    "market_conditions_commentary", "neighborhood_description", "addendum_text",
    "sales_comparison_summary",
)

# A trend statement is about property VALUES only when a value noun is present. Bare
# "market"/"demand" are deliberately excluded — "slowing market activity" is not a
# value trend, and it was the token that let a financing-rate sentence read as a
# value uptrend on ESMI-0048541.
_VALUE_NOUN = re.compile(r"\b(value|values|price|prices|property\s+values?|home\s+values?)\b", re.I)
# Financing/rate context — an "increase" here is a rate move, not a value move.
_FINANCING = re.compile(r"\b(rate|rates|financing|interest|mortgage|apr|loan)\b", re.I)
# Historical framing — a past uptrend ("after several years of increasing values")
# is context, not the current trend the checkbox reports.
_HISTORICAL = re.compile(
    r"after\s+\w+\s+years|years\s+of|histor|previous|prior\s+years|had\s+been|"
    r"over\s+the\s+(past|last)\s+\w+\s+years", re.I)
_UP_WORD = re.compile(r"\b(increas\w*|apprecia\w*|ris\w*|rising|climb\w*|strengthen\w*|upward)\b", re.I)
_DOWN_WORD = re.compile(r"\b(declin\w*|decreas\w*|depreciat\w*|fall\w*|falling|soften\w*|weaken\w*|downward)\b", re.I)
_FLAT_WORD = re.compile(r"\b(stable|steady|flat|balanced|in\s+balance|unchanged)\b", re.I)


def _checkbox_trend(val) -> str:
    """'up' | 'down' | 'flat' | '' from a property-values trend checkbox value."""
    t = (val or "").lower()
    if re.search(r"increas|apprecia|ris", t):
        return "up"
    if re.search(r"declin|decreas", t):
        return "down"
    if re.search(r"stable|steady|balance", t):
        return "flat"
    return ""


def _sentence_value_trend(sentence: str) -> str:
    """'up' | 'down' | 'flat' | '' — the trend a single sentence asserts about
    property VALUES. Returns '' (not a value-trend statement) when the sentence is
    about financing/rates, has no value noun, is historical framing, or is
    directionally ambiguous."""
    if _FINANCING.search(sentence) or not _VALUE_NOUN.search(sentence):
        return ""
    if _HISTORICAL.search(sentence):
        return ""
    up, down = bool(_UP_WORD.search(sentence)), bool(_DOWN_WORD.search(sentence))
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    if _FLAT_WORD.search(sentence) and not (up or down):
        return "flat"
    return ""


def _narrative_trend_dirs(blob: str) -> set:
    """The set of value-trend directions the narrative asserts, one vote per
    sentence. Sentence-scoped so a value noun in one sentence can't bind to a
    direction word in an unrelated (e.g. financing) sentence."""
    dirs = set()
    for sentence in re.split(r"[.\n;]", blob):
        d = _sentence_value_trend(sentence)
        if d:
            dirs.add(d)
    return dirs


@rule(id="XF-TREND-NARRATIVE", num="XF-trend-narrative", section="neighborhood", phase=4,
      severity="advisory", name="Trend checkbox vs narrative trend")
def xf_trend_narrative(ctx: QCContext):
    """VERIFY when the page-1 property-values trend checkbox and the trend asserted
    in the narrative disagree (e.g. checkbox 'Stable' vs narrative 'increasing').

    Suppressed when the narrative ALSO explicitly asserts the checkbox's own
    direction (the appraiser stated the trend and it agrees) — this is what keeps a
    "stable property values … financing rates have increased" report (528/541) from
    a false VERIFY."""
    if not ctx.appraisal.present:
        return []
    checkbox_val = (ctx.appraisal.value("property_values")
                    or ctx.appraisal.value("property_values_trend"))
    checkbox = _checkbox_trend(checkbox_val)
    if not checkbox:
        return []
    dirs = _narrative_trend_dirs(_narrative_blob(ctx, _TREND_NARRATIVE_FIELDS))
    if not dirs or checkbox in dirs:
        return []  # nothing asserted, or the narrative explicitly agrees → no conflict
    narrative = sorted(dirs - {checkbox})[0]

    # Reviewer-facing words, not the internal direction tokens.
    _human = {"up": "increasing", "down": "declining", "flat": "stable"}
    return _res(
        "XF-TREND-NARRATIVE", "XF-trend-narrative", "neighborhood", RuleStatus.VERIFY,
        message=qc_config.template("XF-trend-narrative",
                                   checkbox=(checkbox_val or _human[checkbox]).strip(),
                                   narrative=_human[narrative]),
        fields_involved=["property_values", "market_conditions_commentary"],
        template_id="XF-trend-narrative", confidence=0.7, finding_type="manual_verify",
        evidence=[ctx.appraisal.evidence("property_values"),
                  ctx.appraisal.evidence("market_conditions_commentary")])


# ---------------------------------------------------------------------------
# XF-GRID-BLANK-ADJ — comp differs on GLA but the adjustment cell is blank
# ---------------------------------------------------------------------------

def _comp_indices(ctx: QCContext) -> List[int]:
    """Real comparable columns — gated on a sale_price so blank template columns
    don't produce phantom findings."""
    return [i for i in range(1, _MAX_COMPS + 1)
            if ctx.appraisal.value(f"comp_{i}_sale_price")]


@rule(id="XF-GRID-BLANK-ADJ", num="XF-grid-blank-adj", section="sales_comparison", phase=4,
      applies_when=lambda ctx: ctx.has_sca_grid, severity="advisory",
      name="Comp differs on GLA but adjustment cell is blank")
def xf_grid_blank_adj(ctx: QCContext):
    """For each comp whose GLA differs from the subject by more than the threshold,
    VERIFY when the GLA adjustment cell is BLANK (present-but-empty) rather than an
    explicit $0. Depends on xml_extractor._set_amount recording comp_N_gla_adj_blank
    — a blank cell leaves comp_N_gla_adj NOT_FOUND, which alone can't be told apart
    from 'not extracted' or '$0'."""
    subject_gla = _num(ctx.appraisal.value("gla"))
    idx = _comp_indices(ctx)
    if subject_gla is None or not idx:
        return []
    min_diff = float(qc_config.semantic("xf_gla_blank_adj_min_sqft", 25))

    out: List[RuleResult] = []
    for i in idx:
        comp_gla = _num(ctx.appraisal.value(f"comp_{i}_gla"))
        if comp_gla is None or abs(comp_gla - subject_gla) < min_diff:
            continue
        has_adj = ctx.appraisal.value(f"comp_{i}_gla_adj") is not None
        is_blank = str(ctx.appraisal.value(f"comp_{i}_gla_adj_blank") or "").lower() == "true"
        if has_adj or not is_blank:
            continue  # explicit adjustment (incl. $0), or cell simply absent → not our case
        diff = int(round(abs(comp_gla - subject_gla)))
        out.append(_res(
            "XF-GRID-BLANK-ADJ", "XF-grid-blank-adj", "sales_comparison", RuleStatus.VERIFY,
            message=qc_config.template("XF-grid-blank-adj", comp=i,
                                       comp_gla=int(round(comp_gla)),
                                       subject_gla=int(round(subject_gla)), diff=diff),
            fields_involved=[f"comp_{i}_gla", f"comp_{i}_gla_adj"],
            template_id="XF-grid-blank-adj", confidence=0.7, finding_type="manual_verify",
            evidence=[ctx.appraisal.evidence(f"comp_{i}_gla"),
                      ctx.appraisal.evidence(f"comp_{i}_gla_adj")]))

    if not out:
        return _res("XF-GRID-BLANK-ADJ", "XF-grid-blank-adj", "sales_comparison",
                    RuleStatus.PASS, fields_involved=["comp_N_gla", "comp_N_gla_adj"],
                    evidence=[ctx.appraisal.evidence(f"comp_{idx[0]}_gla")])
    return out
