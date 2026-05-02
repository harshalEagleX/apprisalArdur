"""
RuleOutcome helpers for strict PASS / VERIFY / FAIL decisions.

Rules can still return RuleResult directly, but shared comparison rules should
use evaluate_rule() so thresholds live in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal, Optional

from app.rule_engine.smart_identifier import RuleResult, RuleSeverity, RuleStatus

PASS_THRESHOLD = 0.98
VERIFY_THRESHOLD = 0.70

MatchType = Literal["exact", "fuzzy", "numeric_range", "date", "checkbox"]


@dataclass
class RuleOutcome:
    rule_id: str
    rule_name: str
    status: RuleStatus
    confidence: float
    extracted_value: Any = None
    expected_value: Any = None
    verify_question: Optional[str] = None
    rejection_text: Optional[str] = None
    evidence: list[str] = field(default_factory=list)
    severity: RuleSeverity = RuleSeverity.STANDARD

    def to_rule_result(self) -> RuleResult:
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            status=self.status,
            message=self.rejection_text or self.verify_question or f"{self.rule_name}: {self.status.value}",
            action_item=self.verify_question if self.status == RuleStatus.VERIFY else None,
            appraisal_value=str(self.extracted_value) if self.extracted_value is not None else None,
            engagement_value=str(self.expected_value) if self.expected_value is not None else None,
            review_required=self.status in (RuleStatus.VERIFY, RuleStatus.FAIL),
            severity=self.severity,
            confidence=self.confidence,
            field_confidence=self.confidence,
            extracted_value=self.extracted_value,
            expected_value=self.expected_value,
            verify_question=self.verify_question,
            rejection_text=self.rejection_text,
            evidence=self.evidence,
            details={
                "confidence": round(self.confidence, 4),
                "evidence": self.evidence,
            },
        )


def evaluate_rule(
    *,
    rule_id: str,
    rule_name: str,
    extracted: Any,
    expected: Any,
    extraction_confidence: float,
    match_type: MatchType = "exact",
    field_name: str = "field",
    evidence: Optional[list[str]] = None,
    fail_message: Optional[str] = None,
    verify_question: Optional[str] = None,
    severity: RuleSeverity = RuleSeverity.STANDARD,
) -> RuleOutcome:
    match_score = compute_match(extracted, expected, match_type)
    extraction_confidence = max(0.0, min(1.0, extraction_confidence or 0.0))
    combined = max(0.0, min(1.0, match_score * extraction_confidence))

    if combined >= PASS_THRESHOLD:
        status = RuleStatus.PASS
    elif combined >= VERIFY_THRESHOLD:
        status = RuleStatus.VERIFY
    else:
        status = RuleStatus.FAIL

    refs = evidence or []
    if status == RuleStatus.VERIFY and not verify_question:
        verify_question = (
            f"Please verify {field_name}: appraisal shows '{extracted}' but expected/reference value is "
            f"'{expected}'. Evidence: {', '.join(refs) if refs else 'document evidence'}."
        )
    if status == RuleStatus.FAIL and not fail_message:
        fail_message = (
            f"{field_name} did not meet QC requirements. Appraisal value '{extracted}' does not match "
            f"expected/reference value '{expected}'."
        )

    return RuleOutcome(
        rule_id=rule_id,
        rule_name=rule_name,
        status=status,
        confidence=combined,
        extracted_value=extracted,
        expected_value=expected,
        verify_question=verify_question if status == RuleStatus.VERIFY else None,
        rejection_text=fail_message if status == RuleStatus.FAIL else None,
        evidence=refs,
        severity=severity,
    )


def compute_match(extracted: Any, expected: Any, match_type: MatchType) -> float:
    if extracted is None or expected is None:
        return 0.0

    if match_type == "checkbox":
        return 1.0 if bool(extracted) == bool(expected) else 0.0

    left = str(extracted).strip()
    right = str(expected).strip()
    if not left or not right:
        return 0.0

    if match_type == "exact":
        return 1.0 if _normalize_text(left) == _normalize_text(right) else 0.0
    if match_type == "fuzzy":
        return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()
    if match_type == "numeric_range":
        a = _number(left)
        b = _number(right)
        if a is None or b is None:
            return 0.0
        if b == 0:
            return 1.0 if a == 0 else 0.0
        return 1.0 if abs(a - b) / abs(b) <= 0.01 else max(0.0, 1.0 - abs(a - b) / abs(b))
    if match_type == "date":
        a = _date(left)
        b = _date(right)
        return 1.0 if a and b and a.date() == b.date() else 0.0
    return 0.0


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _number(value: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _date(value: str) -> Optional[datetime]:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None
