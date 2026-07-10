"""Layer-B (appraiser-behaviour) + Layer-C (severity) shared engine for judgment rules.

The MIRA three-layer model: a rule that touches market conditions, comparable
selection, or adjustment support must not fire identically whether the appraiser
silently deviated or explained the deviation in the report narrative.

  Layer A — data existence (each rule already does this: missing data → VERIFY/NA).
  Layer B — appraiser behaviour: does the narrative ADDRESS this concern? Detected
            deterministically by keyword match over the commentary fields, so the
            pass/fail decision NEVER depends on an LLM (CLAUDE.md §17 — the LLM is
            unreliable for decisions, only for evaluative phrasing).
  Layer C — severity calibration: an explained deviation is a lower-severity confirm
            (the reviewer verifies the explanation covers the case); an unexplained
            one keeps full severity.

Reviewer reasoning: every assessment returns a plain-language reasoning string that
is folded into the rule message (so it renders on the existing frontend with no DTO
change). When LAYER_B_LLM_ENABLED, Groq polishes that string into a precise sentence
— an evaluative-only use that does NOT change the explained/severity decision.

P-4: the concern phrase lists and severity confidences are overridable from
qc_thresholds.yaml; P-6: every Groq path degrades to the deterministic template.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional

from app.qc.context import QCContext
from app.qc.result import RuleStatus

logger = logging.getLogger(__name__)

# Commentary fields any judgment explanation could live in (document-level).
# addendum_text is included because appraisers routinely put the adjustment/
# scope/intended-use justification in the supplemental addendum rather than
# repeating it in the field-specific comment box the rule happens to read —
# omitting it caused rules to VERIFY on explanations that were on the page,
# just under a different field name (audit 2026-07-09).
_NARRATIVE_FIELDS = (
    "sales_comparison_summary", "final_reconciliation_comment",
    "market_conditions_commentary", "mca_neighborhood_analysis_comment",
    "neighborhood_description", "contract_analysis_comment",
    "prior_sale_analysis_comment", "special_assessments_comment",
    "addendum_text",
    # Extracted narrative that other rules read under their own names but which
    # never reached Layer-B: the SCA comment box, and the UAD condition/updates
    # blocks (PROPERTY_ANALYSIS). Feeding them here lets is_explained() see the
    # appraiser's real explanations instead of manufacturing "unexplained →
    # VERIFY" findings (audit 2026-07-10).
    "sca_comment", "condition_comments", "improvements_comments",
)

# Per-concern keyword patterns (Layer-B determination). Deterministic by design.
# Each concern also carries a human label and the LLM question used for reasoning.
_CONCERNS: Dict[str, Dict[str, object]] = {
    "dated_comp": {
        "label": "use of an older comparable",
        "rx": re.compile(
            r"(lack|limited|few|no|absence|scarc\w+|shortage)\s+(of\s+)?(recent|current|"
            r"comparable|similar|closed)\s+sales?|best\s+available|most\s+(recent|similar)|"
            r"older\s+(sale|comp)|dated\s+(sale|comp)|expand(ed|ing)?\s+(the\s+)?(search|"
            r"date\s+range|time\s+frame)|limited\s+(inventory|market|data)|rural", re.I),
        "q": "Does this appraisal narrative explain why an older or less-recent "
             "comparable sale was used (e.g. limited inventory, best available)?",
    },
    "large_adjustment": {
        "label": "a large line/net/gross adjustment",
        "rx": re.compile(
            r"adjust\w*\s+(for|reflect|account|due|based)|large\s+adjust|gross\s+adjust|"
            r"net\s+adjust|market[- ]?(derived|extracted|supported)|paired\s+sales?|"
            r"due\s+to\s+(the\s+)?(superior|inferior|size|gla|location|condition|quality)|"
            r"warrant\w*\s+(an?\s+)?adjust", re.I),
        "q": "Does this appraisal narrative explain or support the magnitude of the "
             "adjustments applied to the comparables?",
    },
    "adjustment_consistency": {
        "label": "an inconsistent or absent adjustment",
        "rx": re.compile(
            r"adjust\w*\s+(consistent|differ|vary|same|not\s+(applied|warranted))|"
            r"no\s+adjust\w*\s+(was\s+)?(applied|warranted|necessary)|"
            r"market\s+(did\s+not|does\s+not)\s+(support|warrant)|"
            r"considered\s+equal|similar\s+enough", re.I),
        "q": "Does this appraisal narrative explain why an adjustment was applied "
             "inconsistently across comparables, or why none was applied?",
    },
    "comp_selection": {
        "label": "the selection of this comparable",
        "rx": re.compile(
            r"(selected|chosen|used|utilized)\s+(because|due|as|to|these|the\s+(best|most))|"
            r"best\s+(available|comparable)|most\s+(similar|comparable|recent)|"
            r"despite\s+(the\s+)?(distance|age|difference)|"
            r"(superior|inferior|competing)\s+(market|development|project)|"
            r"buyer\s+pool|same\s+(market|neighborhood|development|project)|new\s+construction", re.I),
        "q": "Does this appraisal narrative explain why this comparable was selected "
             "despite being weak (distance, price bracket, size, or a flip/resale)?",
    },
    "market_trend": {
        "label": "the market-trend / price-range conclusion",
        "rx": re.compile(
            r"market\s+(is|has|trend|condition|remain|appear)|declin\w+|stable|increas\w+|"
            r"over[- ]?suppl\w+|shortage|absorption|months?\s+of\s+supply|"
            r"days?\s+on\s+market|dom\b|median\s+(price|sale)|appreciat\w+|"
            r"predominant|range\s+(of|is|reflect)", re.I),
        "q": "Does this appraisal narrative analyse the market trend or explain the "
             "neighborhood price range with specific data?",
    },
    "approach_omitted": {
        "label": "the omission of a valuation approach",
        "rx": re.compile(
            r"(cost|income)\s+approach\s+(was\s+)?(not|deemed|considered)|"
            r"not\s+(developed|applicable|necessary|required|reliable)|"
            r"owner[- ]?occup\w+|not\s+an?\s+(investor|rental)\s+market|"
            r"credible\s+(assignment\s+)?result", re.I),
        "q": "Does this appraisal narrative explain why the cost or income approach "
             "was not developed?",
    },
    "subject_to": {
        "label": "a Subject-To repair / completion condition",
        "rx": re.compile(
            r"subject\s+to\s+(the\s+)?(repair|completion|inspection|following)|"
            r"repair\w*\s+(required|needed|prior\s+to)|"
            r"1004d|final\s+inspection|recertif\w+|safety\s+(issue|hazard|concern)", re.I),
        "q": "Does this appraisal narrative require a repair, completion, or "
             "re-inspection (a 'Subject To' condition) rather than 'As Is'?",
    },
    # --- Site / Improvements deviation concerns (doc-2 expansion) -------------
    "adverse_condition": {
        "label": "an adverse site/improvement condition",
        "rx": re.compile(
            r"adverse|no\s+(adverse|apparent)|does\s+not\s+(adversely\s+)?affect|"
            r"no\s+(impact|effect)\s+on\s+(value|marketability)|easement|encroach\w+|"
            r"environmental|external\s+(obsolescence|influence)|typical\s+for\s+the\s+(area|market)", re.I),
        "q": "Does the narrative describe the adverse condition and its effect on "
             "value or marketability (or state there is none)?",
    },
    "zoning": {
        "label": "the zoning / legal-conformity status",
        "rx": re.compile(
            r"zoning|legal\s+(non[- ]?)?conform\w+|grandfather\w+|"
            r"rebuilt?\s+(if|to)|can\s+be\s+(rebuilt|re-?built)|"
            r"conform\w+\s+(to|with)\s+(the\s+)?(zoning|use)|permitted\s+use", re.I),
        "q": "Does the narrative explain the zoning non-conformity and whether the "
             "improvement could be rebuilt?",
    },
    "marketability": {
        "label": "marketability / typicality for the market",
        "rx": re.compile(
            r"market\w*\s+(time|abilit|able)|typical\s+for\s+(the\s+)?(area|market|neighborhood)|"
            r"atypical|conform\w+\s+to\s+the\s+(neighborhood|market)|"
            r"no\s+(adverse\s+)?(impact|effect)\s+on\s+market\w+|readily\s+marketable", re.I),
        "q": "Does the narrative address the property's marketability or typicality "
             "for the market given this condition?",
    },
    "conformity": {
        "label": "conformity to the neighborhood",
        "rx": re.compile(
            r"conform\w+\s+(to|with)\s+(the\s+)?(neighborhood|area|market)|"
            r"typical\s+for\s+(the\s+)?(neighborhood|area)|"
            r"over[- ]?improv\w+|under[- ]?improv\w+|compatible\s+with", re.I),
        "q": "Does the narrative address whether the improvement conforms to the "
             "neighborhood (over/under-improvement)?",
    },
    "owner_mismatch": {
        "label": "an owner-of-record vs borrower difference",
        "rx": re.compile(
            r"owner\s+of\s+record|seller\s+(is|of\s+record)|"
            r"vest\w+|title\s+(held|vested)|estate|trust|llc|relocation|"
            r"refinanc\w+|recently\s+(purchased|acquired)", re.I),
        "q": "Does the narrative explain the difference between the owner of record "
             "and the borrower (e.g. recent purchase, trust, relocation)?",
    },
    "concession": {
        "label": "a sale/financing concession",
        "rx": re.compile(
            r"concession|seller\s+(paid|contribut\w+|credit)|"
            r"financ\w+\s+(assistance|terms)|no\s+(concession|adjustment)\s+(was\s+)?(warranted|necessary)|"
            r"cash\s+equivalent|market\s+(did\s+not|does\s+not)\s+(support|require)", re.I),
        "q": "Does the narrative explain the sale/financing concession and how it was "
             "treated (cash-equivalency, no adjustment warranted)?",
    },
}

# Layer-C severity confidences (overridable via qc_thresholds.yaml semantic keys
# layer_b_conf_explained / layer_b_conf_unexplained).
_DEFAULT_EXPLAINED_CONF = 0.4
_DEFAULT_UNEXPLAINED_CONF = 0.7

# Reasoning cache: one Groq call per (narrative, concern, explained) per process.
_reasoning_cache: Dict[str, str] = {}


@dataclass
class Verdict:
    status: RuleStatus
    confidence: float
    message: str
    explained: bool
    reasoning: str


def narrative_text(ctx: QCContext) -> str:
    """All appraiser commentary, concatenated (document-level Layer-B evidence)."""
    parts = [str(ctx.appraisal.value(f) or "") for f in _NARRATIVE_FIELDS]
    return " ".join(p for p in parts if p).strip()


def is_explained(ctx: QCContext, concern: str) -> bool:
    """Deterministic Layer-B: does the narrative address `concern`? (keyword match)"""
    spec = _CONCERNS.get(concern)
    if not spec:
        return False
    rx: re.Pattern = spec["rx"]  # type: ignore[assignment]
    return bool(rx.search(narrative_text(ctx)))


def _conf(key: str, default: float) -> float:
    try:
        from app.qc.config import qc_config
        return float(qc_config.semantic(key, default))
    except Exception:
        return default


def _llm_reasoning(concern: str, explained: bool, facts: str, narrative: str) -> Optional[str]:
    """Polish the reviewer reasoning with Groq (evaluative only — never decides
    pass/fail). Returns None on any failure so the caller uses the template."""
    from app import config
    if not getattr(config, "LAYER_B_LLM_ENABLED", False):
        return None
    key = hashlib.sha1(f"{concern}|{explained}|{facts}|{narrative[:1500]}".encode()).hexdigest()
    if key in _reasoning_cache:
        return _reasoning_cache[key]
    try:
        from app.extraction import llm_groq
        if not llm_groq.groq_extraction_available():
            return None
        spec = _CONCERNS[concern]
        stance = ("The appraiser's narrative APPEARS to address this."
                  if explained else "No clear explanation was found in the narrative.")
        data = llm_groq.chat_json(
            [
                {"role": "system", "content":
                    'You write one concise, neutral sentence of reviewer guidance for a '
                    'mortgage appraisal QC finding. Return ONLY JSON {"reasoning": "..."}. '
                    'Do not invent facts; if unsure, say what the reviewer should confirm.'},
                {"role": "user", "content":
                    f"QC concern: {spec['label']}.\nFinding facts: {facts}\n"
                    f"Keyword assessment: {stance}\n"
                    f"Appraiser narrative (excerpt):\n{narrative[:3000] or '(none extracted)'}\n\n"
                    "Write the one-sentence reviewer guidance."},
            ],
            reasoning_effort="low", max_tokens=400,
        )
        reasoning = (data or {}).get("reasoning")
        if reasoning and isinstance(reasoning, str):
            reasoning = reasoning.strip()
            _reasoning_cache[key] = reasoning
            return reasoning
    except Exception as exc:
        logger.debug("Layer-B LLM reasoning failed (%s) — using template", exc)
    return None


def _template_reasoning(concern: str, explained: bool, facts: str) -> str:
    label = _CONCERNS.get(concern, {}).get("label", "this item")
    if explained:
        return (f"The appraiser's narrative appears to address {label}; "
                f"confirm the explanation specifically covers {facts}.")
    return (f"No supporting explanation for {label} was found in the report "
            f"narrative ({facts}); the appraiser should document the reason.")


def assess(
    ctx: QCContext,
    *,
    concern: str,
    base_message: str,
    facts: str = "",
    explained_status: RuleStatus = RuleStatus.VERIFY,
    unexplained_status: RuleStatus = RuleStatus.VERIFY,
    explained_conf: Optional[float] = None,
    unexplained_conf: Optional[float] = None,
) -> Verdict:
    """Evaluate a judgment finding through Layers B and C and attach reasoning.

    base_message — the rule's existing finding text (the WHAT).
    facts        — short specifics for the reasoning (e.g. "Comps 2, 4 at 25.8% gross").
    The returned message is base_message + reviewer reasoning (the WHY), so the
    frontend shows the full explanation through the existing `message` field.
    """
    narrative = narrative_text(ctx)
    explained = is_explained(ctx, concern)
    status = explained_status if explained else unexplained_status
    conf = (explained_conf if explained else unexplained_conf)
    if conf is None:
        conf = (_conf("layer_b_conf_explained", _DEFAULT_EXPLAINED_CONF) if explained
                else _conf("layer_b_conf_unexplained", _DEFAULT_UNEXPLAINED_CONF))
    reasoning = _llm_reasoning(concern, explained, facts, narrative) \
        or _template_reasoning(concern, explained, facts)
    message = f"{base_message.rstrip()} {reasoning}".strip()
    return Verdict(status=status, confidence=conf, message=message,
                   explained=explained, reasoning=reasoning)
