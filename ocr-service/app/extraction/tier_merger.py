"""
Day 17 — Confidence Score Merging

Combines Tier 1 (LLM), Tier 2 (embeddings), and Tier 3 (spatial+pattern)
results into a single authoritative extraction result per field.

Merging algorithm (from the 30-day plan, Day 17):
  All three agree:        confidence = 0.95  (unanimous)
  Tier1 + Tier3 agree:    confidence = 0.85
  Tier1 + Tier2 agree:    confidence = 0.78
  Tier2 + Tier3 agree:    confidence = 0.72  (LLM absent/disagrees)
  Only one tier found:    confidence = that tier's confidence × 0.85
  No tier found:          NOT_FOUND, confidence = 0.0

Normalization: each tier's raw confidence is mapped to a common [0, 1] scale
before merging, because the tiers produce scores on different scales:
  Tier 1 (LLM):       0.4-0.82 → already [0,1]
  Tier 2 (embedding): cosine similarity 0.68-0.95 → mapped to [0.55, 0.85]
  Tier 3 (spatial):   0.78-0.95 → already [0,1]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.core.result import ExtractionMethod, ExtractionResult, RoutingDecision
from app.core.schema import schema_loader


def _compute_routing(canonical_name: str, confidence: float) -> str:
    """
    Apply confidence thresholds from the field schema to produce a routing decision.
    Architecture Guide §12: auto_accept → no review, review → optional, reject → manual.
    These thresholds are configuration, not hardcoded (Engineering Principle P-4).
    """
    if confidence == 0.0:
        return RoutingDecision.NOT_FOUND

    thresholds = schema_loader.thresholds_for(canonical_name)
    if confidence >= thresholds.auto_accept:
        return RoutingDecision.AUTO_ACCEPT
    elif confidence >= thresholds.review:
        return RoutingDecision.OPTIONAL_REVIEW
    else:
        return RoutingDecision.MANDATORY_REVIEW

logger = logging.getLogger(__name__)

_MERGED_METHOD = "tier_merged"

# Merged confidence levels (from the plan)
_CONF_ALL_AGREE = 0.95
_CONF_T1_T3_AGREE = 0.85
_CONF_T1_T2_AGREE = 0.78
_CONF_T2_T3_AGREE = 0.72
_CONF_SINGLE_MULT = 0.85   # single-tier result gets this multiplier


def _values_compatible(a: Optional[str], b: Optional[str]) -> bool:
    """True if two extracted values are close enough to count as agreement."""
    if a is None or b is None:
        return False
    a_norm = a.strip().lower().replace(",", "")
    b_norm = b.strip().lower().replace(",", "")
    if a_norm == b_norm:
        return True
    # Check containment (one value is a substring of the other)
    if a_norm in b_norm or b_norm in a_norm:
        return len(min(a_norm, b_norm, key=len)) > 2  # must have substance
    return False


def _normalize_confidence(result: ExtractionResult) -> float:
    """
    Map a tier's raw confidence to the common [0, 1] scale.
    Each tier has different raw ranges — normalize before merging.
    """
    method = result.extraction_method
    raw = result.effective_confidence

    if method == ExtractionMethod.EMBEDDING_MATCH:
        # Embedding similarities range 0.68-0.95 → map to 0.55-0.85
        return max(0.0, min(0.85, 0.55 + (raw - 0.68) * (0.30 / 0.27)))

    # LLM and spatial already in [0, 1]
    return raw


@dataclass
class MergedFieldResult:
    """
    The authoritative result for one field after merging all three tiers.
    Carries the audit trail linking back to each tier's contribution.
    """
    canonical_name: str
    document_type: str
    value: Optional[str]
    confidence: float
    tier1_result: Optional[ExtractionResult] = None
    tier2_result: Optional[ExtractionResult] = None
    tier3_result: Optional[ExtractionResult] = None
    agreement_pattern: str = "none"      # all | t1_t3 | t1_t2 | t2_t3 | single | none
    winning_tier: Optional[str] = None   # "tier1" | "tier2" | "tier3"
    requires_review: bool = False

    @property
    def found(self) -> bool:
        return self.value is not None

    def to_extraction_result(self) -> ExtractionResult:
        r = ExtractionResult(
            canonical_name=self.canonical_name,
            document_type=self.document_type,
            value=self.value,
            extraction_method=_MERGED_METHOD,
            confidence=self.confidence,
        )
        # Copy provenance from winning tier
        winner = getattr(self, f"{self.winning_tier}_result") if self.winning_tier else None
        if winner:
            r.raw_source_text = winner.raw_source_text
            r.source_page = winner.source_page
            r.hallucination_flag = winner.hallucination_flag
        r.sanity_check_reason = self.agreement_pattern if not self.found else None

        # Apply confidence-based routing from schema thresholds (Architecture Guide §12)
        r.routing = _compute_routing(self.canonical_name, self.confidence)
        return r


class TierMerger:
    """
    Day 17 — Three-Tier Confidence Merger.

    Takes results from all three extraction tiers and produces a single
    authoritative result per field using the agreement-based merging algorithm.
    """

    def merge(
        self,
        tier3_results: Dict[str, ExtractionResult],  # spatial + pattern (always runs)
        tier1_results: Dict[str, ExtractionResult],  # LLM (may be empty if Ollama down)
        tier2_results: Dict[str, ExtractionResult],  # embeddings (may be empty)
        document_type: str,
    ) -> Dict[str, MergedFieldResult]:
        """
        Merge all three tier results. Returns {canonical_name: MergedFieldResult}.
        """
        # Collect all field names across all tiers
        all_fields = (
            set(tier3_results)
            | set(tier1_results)
            | set(tier2_results)
        )

        merged: Dict[str, MergedFieldResult] = {}

        for fname in all_fields:
            t3 = tier3_results.get(fname)
            t1 = tier1_results.get(fname)
            t2 = tier2_results.get(fname)

            result = self._merge_field(fname, document_type, t1, t2, t3)
            merged[fname] = result

        found_count = sum(1 for r in merged.values() if r.found)
        logger.info(
            "Tier merge complete: %d/%d fields found | patterns: %s",
            found_count, len(merged),
            self._agreement_summary(merged),
        )
        return merged

    def _merge_field(
        self,
        fname: str,
        document_type: str,
        t1: Optional[ExtractionResult],
        t2: Optional[ExtractionResult],
        t3: Optional[ExtractionResult],
    ) -> MergedFieldResult:
        """Apply the merging algorithm for a single field."""

        # Normalize: treat NOT_FOUND results as absent
        t1_val = t1.value if (t1 and t1.found) else None
        t2_val = t2.value if (t2 and t2.found) else None
        t3_val = t3.value if (t3 and t3.found) else None

        def base(r): return _normalize_confidence(r) if r and r.found else 0.0

        # Case 1: All three agree
        if t1_val and t2_val and t3_val:
            if _values_compatible(t1_val, t2_val) and _values_compatible(t1_val, t3_val):
                return MergedFieldResult(
                    canonical_name=fname, document_type=document_type,
                    value=t3_val,  # Tier 3 (spatial) is most reliable for exact values
                    confidence=_CONF_ALL_AGREE,
                    tier1_result=t1, tier2_result=t2, tier3_result=t3,
                    agreement_pattern="all", winning_tier="tier3",
                )

        # Case 2: Tier 1 and Tier 3 agree (best combination: LLM + spatial)
        if t1_val and t3_val and _values_compatible(t1_val, t3_val):
            return MergedFieldResult(
                canonical_name=fname, document_type=document_type,
                value=t3_val, confidence=_CONF_T1_T3_AGREE,
                tier1_result=t1, tier3_result=t3,
                agreement_pattern="t1_t3", winning_tier="tier3",
            )

        # Case 3: Tier 1 and Tier 2 agree (LLM + embedding agree, spatial absent/different)
        if t1_val and t2_val and _values_compatible(t1_val, t2_val):
            return MergedFieldResult(
                canonical_name=fname, document_type=document_type,
                value=t1_val, confidence=_CONF_T1_T2_AGREE,
                tier1_result=t1, tier2_result=t2,
                agreement_pattern="t1_t2", winning_tier="tier1",
                requires_review=(t3_val is not None),  # flag if spatial disagrees
            )

        # Case 4: Tier 2 and Tier 3 agree (embedding + spatial; LLM absent/hallucinating)
        if t2_val and t3_val and _values_compatible(t2_val, t3_val):
            return MergedFieldResult(
                canonical_name=fname, document_type=document_type,
                value=t3_val, confidence=_CONF_T2_T3_AGREE,
                tier2_result=t2, tier3_result=t3,
                agreement_pattern="t2_t3", winning_tier="tier3",
            )

        # Case 5: Exactly one tier has a result — use it with reduced confidence
        candidates = [(t3, "tier3"), (t1, "tier1"), (t2, "tier2")]
        single_found = [(r, name) for r, name in candidates if r and r.found]

        if len(single_found) == 1:
            winner, tier_name = single_found[0]
            conf = base(winner) * _CONF_SINGLE_MULT
            return MergedFieldResult(
                canonical_name=fname, document_type=document_type,
                value=winner.value, confidence=round(conf, 3),
                **{f"{tier_name}_result": winner},
                agreement_pattern="single", winning_tier=tier_name,
                requires_review=(conf < 0.70),
            )

        # Case 6: Multiple tiers disagree — pick highest confidence
        if len(single_found) > 1:
            best = max(single_found, key=lambda x: base(x[0]))
            winner, tier_name = best
            conf = base(winner) * 0.70  # low — tiers disagree
            logger.debug(
                "Tier disagreement on %s: t1=%r t2=%r t3=%r → using %s",
                fname, t1_val, t2_val, t3_val, tier_name,
            )
            return MergedFieldResult(
                canonical_name=fname, document_type=document_type,
                value=winner.value, confidence=round(conf, 3),
                tier1_result=t1, tier2_result=t2, tier3_result=t3,
                agreement_pattern="disagree", winning_tier=tier_name,
                requires_review=True,
            )

        # Case 7: No tier found anything
        return MergedFieldResult(
            canonical_name=fname, document_type=document_type,
            value=None, confidence=0.0,
            tier3_result=t3,
            agreement_pattern="none",
        )

    @staticmethod
    def _agreement_summary(merged: Dict[str, MergedFieldResult]) -> str:
        counts: Dict[str, int] = {}
        for r in merged.values():
            counts[r.agreement_pattern] = counts.get(r.agreement_pattern, 0) + 1
        return str(counts)
