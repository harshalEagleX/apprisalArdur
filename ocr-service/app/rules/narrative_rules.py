"""
Narrative / Commentary Rules — N-1 through N-7 (Phase 4)

These rules evaluate the QUALITY of appraiser commentary using:
  Tier 1: LLM (ollama/llama3) — most accurate
  Tier 2: Keyword/pattern matching — always available fallback

They always run LAST (execution_order 210–270) because they are the slowest.
LLM responses are cached by input hash so re-processed documents are instant.

Severity: all ADVISORY or STANDARD — commentary issues are serious but rarely BLOCKING.
"""

import re
import logging
from typing import Optional

from app.rule_engine.engine import rule, RuleStatus, RuleResult, RuleSeverity, DataMissingException
from app.models.appraisal import ValidationContext

logger = logging.getLogger(__name__)

# Cached LLM functions — graceful import (LLM may not be available)
try:
    from app.services.ollama_service import (
        classify_commentary, analyze_market_conditions,
        is_neighborhood_description_specific, is_ollama_available,
        OLLAMA_MODEL,
    )
    _OLLAMA_OK = is_ollama_available()
except Exception:
    _OLLAMA_OK = False

try:
    from app.services.llm_cache import get_cached_llm, save_llm_response
    _CACHE_OK = True
except Exception:
    _CACHE_OK = False

# ── LLM wrapper with caching ───────────────────────────────────────────────────

def _llm_classify_canned(text: str) -> Optional[bool]:
    """True=canned, False=specific, None=unavailable. Cached."""
    if not text or len(text.strip()) < 20:
        return None
    cache_key = f"canned_detection::{text[:800]}"
    if _CACHE_OK:
        cached = get_cached_llm("canned_detection", text[:800])
        if cached is not None:
            return cached.strip().upper() == "CANNED"
    if _OLLAMA_OK:
        result = classify_commentary(text)
        if result is not None and _CACHE_OK:
            save_llm_response("canned_detection", text[:800],
                              "CANNED" if result else "SPECIFIC", OLLAMA_MODEL)
        return result
    return None


def _llm_market_quality(text: str) -> dict:
    """Analyze market conditions commentary quality. Cached."""
    if not text:
        return {}
    if _CACHE_OK:
        import json
        cached = get_cached_llm("market_quality", text[:800])
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
    if _OLLAMA_OK:
        result = analyze_market_conditions(text)
        if result and _CACHE_OK:
            import json
            save_llm_response("market_quality", text[:800], json.dumps(result), OLLAMA_MODEL)
        return result
    return {}


def _llm_nbr_specific(text: str) -> Optional[bool]:
    """True=specific, False=generic. Cached."""
    if not text:
        return None
    if _CACHE_OK:
        cached = get_cached_llm("nbr_specific", text[:600])
        if cached is not None:
            return cached.strip().upper() == "YES"
    if _OLLAMA_OK:
        result = is_neighborhood_description_specific(text)
        if result is not None and _CACHE_OK:
            save_llm_response("nbr_specific", text[:600],
                              "YES" if result else "NO", OLLAMA_MODEL)
        return result
    return None


# ── Keyword fallbacks ──────────────────────────────────────────────────────────

_CANNED_PHRASES = [
    "the subject property is located in a", "the neighborhood is characterized by",
    "the subject is typical for the neighborhood", "see attached addendum",
    "no adverse conditions were noted", "the property appears to be in average condition",
    "the improvements are typical for the area", "the subject is compatible",
    "this is a stable neighborhood", "the market appears balanced",
    "see comparable sales grid", "adjustments reflect market reactions",
    "comparable sales were selected based on", "the cost approach was not developed",
    "the income approach was not developed", "equal weight was given to",
    "weighted average of the indicated values",
]

_SPECIFIC_INDICATORS = [
    r'\$[\d,]+',            # dollar amounts
    r'\d+\s*(?:sf|sq\.?\s*ft)', # square footage
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+',
    r'\d+/\d+/\d+',         # dates
    r'\bDOM\s*\d+',          # days on market
    r'\b[A-Z]{2,5}MLS\b',   # MLS abbreviations
    r'\d+%',                 # percentages
    r'\bMLS\b.*?\d+',        # MLS numbers
]

_REASONING_WORDS = [
    "because", "therefore", "as a result", "due to", "since", "based on",
    "indicates", "suggests", "reflects", "demonstrates", "specifically",
    "in comparison", "relative to", "taking into account", "given that",
]


def _is_canned_fallback(text: str) -> tuple:
    """(is_canned: bool, confidence: float) using keyword matching only."""
    if not text:
        return True, 0.9

    lower = text.lower()
    canned_hits = sum(1 for phrase in _CANNED_PHRASES if phrase in lower)
    specific_hits = sum(1 for p in _SPECIFIC_INDICATORS if re.search(p, text, re.I))
    reasoning_hits = sum(1 for w in _REASONING_WORDS if w in lower)

    score = (canned_hits * 0.3) - (specific_hits * 0.2) - (reasoning_hits * 0.1)

    if specific_hits >= 2 or reasoning_hits >= 3:
        return False, 0.8   # specific
    if canned_hits >= 2:
        return True, 0.75   # canned
    return (score > 0.2), 0.5   # uncertain


def _has_market_analysis_fallback(text: str) -> bool:
    """True if commentary shows real market analysis (not just 'see 1004mc')."""
    if not text:
        return False
    lower = text.lower()
    if re.search(r'see\s+1004mc|refer\s+to.*1004mc', lower):
        return False
    specific = sum(1 for p in _SPECIFIC_INDICATORS if re.search(p, text, re.I))
    return specific >= 2


# ── N-1: Neighborhood Description Specificity ─────────────────────────────────

@rule(id="COM-1", name="Neighborhood Description Specificity")
def validate_neighborhood_description(ctx: ValidationContext) -> RuleResult:
    """
    N-1: Is the neighborhood description specific to this area, or generic boilerplate?
    Fails if: commentary is canned/generic.
    Uses LLM (ollama) with keyword fallback.
    """
    text = ctx.report.neighborhood.description_commentary
    if not text or len(text.strip()) < 20:
        return RuleResult(
            rule_id="COM-1", rule_name="Neighborhood Description Specificity",
            status=RuleStatus.VERIFY,
            message="Neighborhood description not found or too short to evaluate.",
            review_required=True,
            severity=RuleSeverity.ADVISORY,
        )

    # Tier 1: LLM
    llm_result = _llm_nbr_specific(text)
    if llm_result is not None:
        if llm_result:
            return RuleResult(
                rule_id="COM-1", rule_name="Neighborhood Description Specificity",
                status=RuleStatus.PASS,
                message="Neighborhood description is specific to the subject area.",
                severity=RuleSeverity.ADVISORY,
            )
        else:
            return RuleResult(
                rule_id="COM-1", rule_name="Neighborhood Description Specificity",
                status=RuleStatus.WARNING,
                message="Neighborhood description appears generic/boilerplate. "
                        "It should reference specific local landmarks, employers, streets, or market data.",
                action_item="Revise neighborhood description to include area-specific details.",
                severity=RuleSeverity.ADVISORY,
            )

    # Tier 2: Keyword fallback
    is_canned, conf = _is_canned_fallback(text)
    if is_canned:
        return RuleResult(
            rule_id="COM-1", rule_name="Neighborhood Description Specificity",
            status=RuleStatus.WARNING,
            message="Neighborhood description may be generic. Add specific local market details.",
            action_item="Revise to include area-specific data (distances, employers, schools, market stats).",
            field_confidence=conf,
            severity=RuleSeverity.ADVISORY,
        )
    return RuleResult(
        rule_id="COM-1", rule_name="Neighborhood Description Specificity",
        status=RuleStatus.PASS,
        message="Neighborhood description appears specific.",
        field_confidence=conf,
        severity=RuleSeverity.ADVISORY,
    )


# ── N-2: Market Conditions Quality ────────────────────────────────────────────

@rule(id="COM-2", name="Market Conditions Quality")
def validate_market_conditions(ctx: ValidationContext) -> RuleResult:
    """
    N-2: Does the market conditions commentary contain real analysis?
    Fails if: commentary only says 'see 1004mc' without adding analysis.
    """
    text = ctx.report.neighborhood.market_conditions_comment
    if not text or len(text.strip()) < 10:
        return RuleResult(
            rule_id="COM-2", rule_name="Market Conditions Quality",
            status=RuleStatus.FAIL,
            message="Market conditions commentary is blank or missing. "
                    "UAD requires a market analysis in this section; 'See 1004MC' alone is not acceptable.",
            action_item="Add market conditions commentary with specific market data.",
            severity=RuleSeverity.STANDARD,
        )

    # Tier 1: LLM
    llm_result = _llm_market_quality(text)
    if llm_result:
        is_see_1004mc = llm_result.get("is_see_1004mc", False)
        has_analysis  = llm_result.get("has_analysis", True)

        if is_see_1004mc and not has_analysis:
            return RuleResult(
                rule_id="COM-2", rule_name="Market Conditions Quality",
                status=RuleStatus.FAIL,
                message="Market conditions commentary only references the 1004MC addendum. "
                        "UAD requires actual commentary, not just 'see 1004MC'.",
                action_item="Add specific market analysis to this section.",
                appraisal_value=text[:100],
                severity=RuleSeverity.STANDARD,
            )
        if has_analysis:
            return RuleResult(
                rule_id="COM-2", rule_name="Market Conditions Quality",
                status=RuleStatus.PASS,
                message="Market conditions commentary contains actual analysis.",
                severity=RuleSeverity.STANDARD,
            )

    # Tier 2: fallback
    if re.search(r'\bsee\s+1004mc\b', text, re.I) and not _has_market_analysis_fallback(text):
        return RuleResult(
            rule_id="COM-2", rule_name="Market Conditions Quality",
            status=RuleStatus.FAIL,
            message="Market conditions section appears to only say 'See 1004MC'. Add specific commentary.",
            action_item="Provide actual market analysis in this section.",
            severity=RuleSeverity.STANDARD,
        )

    has_analysis = _has_market_analysis_fallback(text)
    return RuleResult(
        rule_id="COM-2", rule_name="Market Conditions Quality",
        status=RuleStatus.PASS if has_analysis else RuleStatus.WARNING,
        message="Market conditions commentary found." if has_analysis
                else "Market conditions commentary may lack specific market data.",
        severity=RuleSeverity.STANDARD,
    )


# ── N-3: Comparable Selection Rationale ───────────────────────────────────────

@rule(id="COM-3", name="Comparable Selection Rationale")
def validate_comparable_selection(ctx: ValidationContext) -> RuleResult:
    """
    N-3: Does the appraiser explain why these comparables were selected?
    Rule-based — looks for selection rationale phrases.
    """
    sales = ctx.report.sales_comparison
    if sales.comparables_count_sales is not None and sales.comparables_count_sales < 3:
        return RuleResult(
            rule_id="COM-3", rule_name="Comparable Selection Rationale",
            status=RuleStatus.FAIL,
            message=f"Only {sales.comparables_count_sales} comparable sale(s) provided. Minimum 3 required.",
            action_item="Add at least 3 comparable sales to the grid.",
            severity=RuleSeverity.STANDARD,
        )

    commentary = sales.summary_commentary or ""
    SELECTION_PHRASES = [
        "selected based on", "selected due to", "selected because",
        "proximity to", "similar in", "most similar", "best available",
        "representative of", "bracketing the", "chosen for",
    ]
    has_rationale = any(phrase in commentary.lower() for phrase in SELECTION_PHRASES)

    if not commentary or len(commentary.strip()) < 20:
        return RuleResult(
            rule_id="COM-3", rule_name="Comparable Selection Rationale",
            status=RuleStatus.VERIFY,
            message="Comparable selection commentary not found. "
                    "Please verify the appraiser explains why these comparables were chosen.",
            review_required=True,
            severity=RuleSeverity.ADVISORY,
        )

    if has_rationale:
        return RuleResult(
            rule_id="COM-3", rule_name="Comparable Selection Rationale",
            status=RuleStatus.PASS,
            message="Comparable selection rationale is provided.",
            severity=RuleSeverity.ADVISORY,
        )

    return RuleResult(
        rule_id="COM-3", rule_name="Comparable Selection Rationale",
        status=RuleStatus.WARNING,
        message="Comparable selection commentary does not clearly explain why these properties were selected.",
        action_item="Add rationale explaining why each comparable was selected (proximity, similarity, availability).",
        severity=RuleSeverity.ADVISORY,
    )


# ── N-4: Adjustments Explanation ──────────────────────────────────────────────

@rule(id="COM-4", name="Adjustments Explanation")
def validate_adjustments_explanation(ctx: ValidationContext) -> RuleResult:
    """
    N-4: Are the adjustments in the sales comparison grid explained?
    FNMA requires that significant adjustments be supported by market data.
    """
    commentary = ctx.report.sales_comparison.summary_commentary or ""

    ADJUSTMENT_PHRASES = [
        "adjustment", "adjusted", "adjusted for", "market support",
        "paired sales", "extracted from", "market reaction", "dollar per",
        "% adjustment", "percent adjustment",
    ]
    has_explanation = any(phrase in commentary.lower() for phrase in ADJUSTMENT_PHRASES)

    if not commentary or len(commentary.strip()) < 20:
        return RuleResult(
            rule_id="COM-4", rule_name="Adjustments Explanation",
            status=RuleStatus.VERIFY,
            message="Sales comparison commentary not found. Verify adjustments are explained.",
            review_required=True,
            severity=RuleSeverity.ADVISORY,
        )

    return RuleResult(
        rule_id="COM-4", rule_name="Adjustments Explanation",
        status=RuleStatus.PASS if has_explanation else RuleStatus.WARNING,
        message="Adjustment explanation found in commentary." if has_explanation
                else "Adjustments may not be adequately explained. "
                     "FNMA requires market support for significant adjustments.",
        action_item=None if has_explanation
                    else "Add commentary explaining the basis for each adjustment.",
        severity=RuleSeverity.ADVISORY,
    )


# ── N-5: Reconciliation Sufficiency ───────────────────────────────────────────

@rule(id="COM-5", name="Reconciliation Sufficiency")
def validate_reconciliation(ctx: ValidationContext) -> RuleResult:
    """
    N-5: Does the reconciliation section explain WHY the final value was chosen,
    or does it just restate the comparable values?
    Uses LLM when available.
    """
    commentary = ctx.report.sales_comparison.summary_commentary or ""

    RECON_PHRASES = [
        "reconciliation", "greater weight", "most weight", "best indicator",
        "final value", "opinion of value", "most representative", "closely reflects",
        "given more weight", "considered most reliable",
    ]
    has_recon_phrases = any(p in commentary.lower() for p in RECON_PHRASES)

    if not commentary or len(commentary.strip()) < 20:
        return RuleResult(
            rule_id="COM-5", rule_name="Reconciliation Sufficiency",
            status=RuleStatus.VERIFY,
            message="Reconciliation commentary not found.",
            review_required=True,
            severity=RuleSeverity.STANDARD,
        )

    # Try LLM — send the last 800 chars (reconciliation is usually at the end)
    recon_text = commentary[-800:]
    llm_result = _llm_classify_canned(recon_text)

    if llm_result is True:   # canned
        return RuleResult(
            rule_id="COM-5", rule_name="Reconciliation Sufficiency",
            status=RuleStatus.WARNING,
            message="Reconciliation commentary appears generic. It should explain why the final "
                    "value was chosen, not just restate the comparable values.",
            action_item="Revise reconciliation to explain the basis for the final value opinion.",
            severity=RuleSeverity.STANDARD,
        )

    if has_recon_phrases:
        return RuleResult(
            rule_id="COM-5", rule_name="Reconciliation Sufficiency",
            status=RuleStatus.PASS,
            message="Reconciliation commentary explains the basis for the final value.",
            severity=RuleSeverity.STANDARD,
        )

    return RuleResult(
        rule_id="COM-5", rule_name="Reconciliation Sufficiency",
        status=RuleStatus.WARNING,
        message="Reconciliation section may not adequately explain why the final value was selected.",
        action_item="Add commentary explaining which comparable(s) are most reliable and why.",
        severity=RuleSeverity.STANDARD,
    )


# ── N-6: Addenda Consistency ──────────────────────────────────────────────────

@rule(id="COM-6", name="Addenda Consistency")
def validate_addenda_consistency(ctx: ValidationContext) -> RuleResult:
    """
    COM-6: Do addenda contradict key main-form values?

    This lightweight automated check scans addenda/certification text for common
    cross-reference problems: different subject address, borrower/lender mismatch,
    or a final value that differs from the main form extraction.
    """
    raw_text = ctx.raw_text or ""
    if not raw_text.strip():
        return RuleResult(
            rule_id="COM-6", rule_name="Addenda Consistency",
            status=RuleStatus.VERIFY,
            message="Addenda text was not available for consistency analysis.",
            action_item="Manually compare addenda against the main report fields.",
            review_required=True,
            severity=RuleSeverity.ADVISORY,
        )

    lower = raw_text.lower()
    starts = [
        lower.find("addendum"),
        lower.find("additional comments"),
        lower.find("supplemental addendum"),
        lower.find("certification"),
    ]
    starts = [pos for pos in starts if pos >= 0]
    addenda_text = raw_text[min(starts):] if starts else raw_text[-5000:]

    subject = ctx.report.subject
    field_meta = ctx.field_meta or {}
    issues = []

    if subject.address and not _contains_normalized(addenda_text, subject.address):
        if re.search(r"\b\d{2,6}\s+[A-Za-z0-9 .'-]{3,80}\b", addenda_text):
            issues.append("Addenda contains an address-like value that does not match the subject address.")

    if subject.borrower and re.search(r"\bborrower\b", addenda_text, re.I):
        if not _contains_normalized(addenda_text, subject.borrower):
            issues.append("Borrower reference in addenda does not match the main form borrower.")

    if subject.lender_name and re.search(r"\b(?:lender|client)\b", addenda_text, re.I):
        if not _contains_normalized(addenda_text, subject.lender_name):
            issues.append("Lender/client reference in addenda does not match the main form lender.")

    mv_meta = field_meta.get("market_value_opinion")
    market_value = getattr(mv_meta, "value", None) if mv_meta else None
    if market_value:
        expected_amount = _money_digits(str(market_value))
        addenda_amounts = {_money_digits(m.group(0)) for m in re.finditer(r"\$\s*\d[\d,]{3,}", addenda_text)}
        addenda_amounts.discard("")
        if expected_amount and addenda_amounts and expected_amount not in addenda_amounts:
            issues.append("Dollar amount in addenda may conflict with the extracted final value.")

    if issues:
        return RuleResult(
            rule_id="COM-6", rule_name="Addenda Consistency",
            status=RuleStatus.WARNING,
            message="Addenda consistency issue found: " + " ".join(issues),
            action_item="Review addenda and correct any references that conflict with the main report.",
            review_required=True,
            severity=RuleSeverity.ADVISORY,
        )

    return RuleResult(
        rule_id="COM-6", rule_name="Addenda Consistency",
        status=RuleStatus.PASS,
        message="Automated addenda consistency check found no obvious conflicts with main report fields.",
        review_required=False,
        severity=RuleSeverity.ADVISORY,
    )


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _contains_normalized(haystack: str, needle: str) -> bool:
    normalized_needle = _normalize_for_compare(needle)
    if not normalized_needle:
        return True
    return normalized_needle in _normalize_for_compare(haystack)


def _money_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "").lstrip("0")


# ── N-7: Prior Sales Disclosure ───────────────────────────────────────────────

@rule(id="COM-7", name="Prior Sales Disclosure")
def validate_prior_sales(ctx: ValidationContext) -> RuleResult:
    """
    N-7: Are prior sales of the subject property disclosed and analyzed?
    FNMA requires disclosure of any transfers in the prior 3 years.
    """
    subject = ctx.report.subject
    offered = subject.prior_sale_offered_12mo

    if offered is None:
        return RuleResult(
            rule_id="COM-7", rule_name="Prior Sales Disclosure",
            status=RuleStatus.VERIFY,
            message="Could not determine if prior listing/sale history is addressed. "
                    "Verify the appraiser has disclosed any prior transfers.",
            review_required=True,
            severity=RuleSeverity.STANDARD,
        )

    if offered:
        # If offered for sale, must have MLS/DOM data
        missing = []
        if not subject.days_on_market:
            missing.append("Days on Market")
        if not subject.data_sources:
            missing.append("Data Source")
        if missing:
            return RuleResult(
                rule_id="COM-7", rule_name="Prior Sales Disclosure",
                status=RuleStatus.WARNING,
                message=f"Property was offered for sale but missing: {', '.join(missing)}.",
                action_item=f"Add {', '.join(missing)} to the Subject section.",
                severity=RuleSeverity.STANDARD,
            )

    return RuleResult(
        rule_id="COM-7", rule_name="Prior Sales Disclosure",
        status=RuleStatus.PASS,
        message="Prior listing/sale history is disclosed.",
        severity=RuleSeverity.STANDARD,
    )
