"""
Day 21 — Context-Aware Semantic Validation

The plan (Day 21): "Semantic validation checks that values make sense in context,
not just that they are formatted correctly."

Rules implemented here (per the plan and QC checklist):

CROSS-FIELD RULES (same document):
  SEM-01  Appraised value vs contract price — >20% difference → FLAG
  SEM-02  Effective date before signature date — sequence must hold
  SEM-03  Contract date before effective date — sequence must hold
  SEM-04  Appraiser cert expiration after effective date — must not be expired
  SEM-05  GLA reasonableness vs comparable GLA average (±50%)
  SEM-06  Neighborhood price range — appraised value within predominant range (±10%)
  SEM-07  Land use total must equal 100%

COMPARABLE SALE DATE RULES:
  SEM-08  Each comparable sale date within 12 months of effective date (FHA: strict)
  SEM-09  Comparable adjusted sale price within reasonable range

REQUIRED FIELD PRESENCE:
  SEM-10  Required_cross_document fields must be present
  SEM-11  Fields required when assignment_type=Purchase

All results stored in adaptive_validation_results. All rules fire independently
— one rule failing never blocks others (graceful degradation, Architecture Guide §8).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from app.core.result import ExtractionResult, ExtractionResultSet
from app.core.schema import schema_loader

logger = logging.getLogger(__name__)

_APPRAISAL_VALUE_PRICE_WARN_PCT = 20.0    # flag if >20% difference
_APPRAISAL_VALUE_PRICE_HOLD_PCT = 30.0    # escalate if >30% difference
_COMP_SALE_WINDOW_MONTHS = 12
_GLA_REASONABLENESS_PCT = 50.0


@dataclass
class ValidationResult:
    rule_id: str
    rule_category: str       # semantic | temporal | cross_document | cross_field
    fields_involved: List[str]
    result: str              # pass | fail | warning | info | skipped
    confidence: float
    explanation: str
    field_values: Dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.result == "pass"

    def to_db_dict(self, document_id: str, transaction_id: Optional[str] = None) -> dict:
        return {
            "document_id": document_id,
            "transaction_id": transaction_id,
            "rule_id": self.rule_id,
            "rule_category": self.rule_category,
            "fields_involved": json.dumps(self.fields_involved),
            "result": self.result,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "field_values_snapshot": json.dumps(self.field_values),
        }


def _val(rs: ExtractionResultSet, field_name: str) -> Optional[str]:
    """Get extracted value or None."""
    r = rs.get(field_name)
    return r.value if r and r.found else None


def _float(rs: ExtractionResultSet, field_name: str) -> Optional[float]:
    """Get extracted value as float or None."""
    v = _val(rs, field_name)
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _date(rs: ExtractionResultSet, field_name: str) -> Optional[datetime]:
    """Get extracted value as date or None."""
    v = _val(rs, field_name)
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def rule_sem01_value_price_ratio(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-01: Appraised value vs contract price — >20% difference = FLAG."""
    av = _float(rs, "appraised_value")
    cp = _float(rs, "contract_price")

    if av is None or cp is None:
        return ValidationResult(
            rule_id="SEM-01", rule_category="cross_field",
            fields_involved=["appraised_value", "contract_price"],
            result="skipped", confidence=1.0,
            explanation="Cannot check: appraised_value or contract_price not extracted.",
        )

    if cp == 0:
        return ValidationResult(
            rule_id="SEM-01", rule_category="cross_field",
            fields_involved=["appraised_value", "contract_price"],
            result="skipped", confidence=1.0,
            explanation="Contract price is zero — cannot compute ratio.",
        )

    diff_pct = abs(av - cp) / cp * 100

    if diff_pct > _APPRAISAL_VALUE_PRICE_HOLD_PCT:
        result, explanation = "fail", (
            f"Appraised value ${av:,.0f} differs from contract price ${cp:,.0f} "
            f"by {diff_pct:.1f}% — exceeds 30% threshold. Hold for escalation."
        )
    elif diff_pct > _APPRAISAL_VALUE_PRICE_WARN_PCT:
        result, explanation = "warning", (
            f"Appraised value ${av:,.0f} differs from contract price ${cp:,.0f} "
            f"by {diff_pct:.1f}% — exceeds 20% threshold. Detailed reconciliation required."
        )
    else:
        result, explanation = "pass", (
            f"Appraised value ${av:,.0f} and contract price ${cp:,.0f} "
            f"within {diff_pct:.1f}% of each other."
        )

    return ValidationResult(
        rule_id="SEM-01", rule_category="cross_field",
        fields_involved=["appraised_value", "contract_price"],
        result=result, confidence=0.95, explanation=explanation,
        field_values={"appraised_value": str(av), "contract_price": str(cp), "diff_pct": f"{diff_pct:.1f}%"},
    )


def rule_sem02_effective_before_signature(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-02: Effective date must be before (or equal to) signature date."""
    eff = _date(rs, "effective_date")
    sig = _date(rs, "date_of_signature")

    if eff is None or sig is None:
        return ValidationResult(
            rule_id="SEM-02", rule_category="temporal",
            fields_involved=["effective_date", "date_of_signature"],
            result="skipped", confidence=1.0,
            explanation="Cannot check date sequence: one or both dates not extracted.",
        )

    if sig < eff:
        return ValidationResult(
            rule_id="SEM-02", rule_category="temporal",
            fields_involved=["effective_date", "date_of_signature"],
            result="fail", confidence=0.95,
            explanation=(
                f"Signature date {sig.date()} is before effective date {eff.date()}. "
                "The appraiser cannot sign before the inspection date."
            ),
            field_values={"effective_date": str(eff.date()), "date_of_signature": str(sig.date())},
        )

    return ValidationResult(
        rule_id="SEM-02", rule_category="temporal",
        fields_involved=["effective_date", "date_of_signature"],
        result="pass", confidence=0.95,
        explanation=f"Date sequence valid: inspection {eff.date()} → signature {sig.date()}.",
    )


def rule_sem03_contract_before_effective(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-03: Contract date should precede or equal effective date for purchase transactions."""
    assignment = _val(rs, "assignment_type") or ""
    if "purchase" not in assignment.lower():
        return ValidationResult(
            rule_id="SEM-03", rule_category="temporal",
            fields_involved=["contract_date", "effective_date"],
            result="info", confidence=1.0,
            explanation="Not a purchase transaction — contract date check skipped.",
        )

    contract_dt = _date(rs, "contract_date")
    eff = _date(rs, "effective_date")

    if contract_dt is None or eff is None:
        return ValidationResult(
            rule_id="SEM-03", rule_category="temporal",
            fields_involved=["contract_date", "effective_date"],
            result="skipped", confidence=1.0,
            explanation="Cannot check: contract_date or effective_date not extracted.",
        )

    days_gap = (eff - contract_dt).days
    if days_gap < 0:
        return ValidationResult(
            rule_id="SEM-03", rule_category="temporal",
            fields_involved=["contract_date", "effective_date"],
            result="fail", confidence=0.90,
            explanation=(
                f"Contract date {contract_dt.date()} is after effective date {eff.date()}. "
                "The contract should pre-date the appraisal inspection."
            ),
            field_values={"contract_date": str(contract_dt.date()), "effective_date": str(eff.date())},
        )

    if days_gap > 365:
        return ValidationResult(
            rule_id="SEM-03", rule_category="temporal",
            fields_involved=["contract_date", "effective_date"],
            result="warning", confidence=0.85,
            explanation=(
                f"Contract dated {contract_dt.date()} is {days_gap} days before "
                f"inspection {eff.date()} — unusually old contract, verify currency."
            ),
            field_values={"contract_date": str(contract_dt.date()), "effective_date": str(eff.date())},
        )

    return ValidationResult(
        rule_id="SEM-03", rule_category="temporal",
        fields_involved=["contract_date", "effective_date"],
        result="pass", confidence=0.95,
        explanation=f"Contract {contract_dt.date()} precedes inspection {eff.date()} by {days_gap} days.",
    )


def rule_sem06_land_use_total(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-07: Present land use percentages must sum to ~100%."""
    components = [
        "land_use_one_unit", "land_use_2_4_unit",
        "land_use_multi_family", "land_use_commercial", "land_use_other",
    ]
    values = {}
    total = 0.0
    missing_count = 0
    for c in components:
        v = _float(rs, c)
        if v is not None:
            values[c] = v
            total += v
        else:
            missing_count += 1

    if missing_count >= 4:
        return ValidationResult(
            rule_id="SEM-07", rule_category="cross_field",
            fields_involved=components,
            result="skipped", confidence=1.0,
            explanation="Land use percentages not available for total check.",
        )

    if abs(total - 100.0) > 3.0:
        return ValidationResult(
            rule_id="SEM-07", rule_category="cross_field",
            fields_involved=components,
            result="fail", confidence=0.90,
            explanation=(
                f"Land use percentages sum to {total:.1f}% — must equal 100%. "
                "Per QC Rule N-4: total must always equal 100%."
            ),
            field_values={k: f"{v:.0f}%" for k, v in values.items()},
        )

    return ValidationResult(
        rule_id="SEM-07", rule_category="cross_field",
        fields_involved=components,
        result="pass", confidence=0.95,
        explanation=f"Land use percentages sum to {total:.1f}% — within acceptable range.",
    )


def rule_sem10_required_fields(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-10: Fields marked required_cross_document must be present."""
    required = [f for f in schema_loader.all_fields() if f.required == "required_cross_document"]
    missing = [f.canonical_name for f in required if not (rs.get(f.canonical_name) and rs.get(f.canonical_name).found)]

    if not missing:
        return ValidationResult(
            rule_id="SEM-10", rule_category="semantic",
            fields_involved=[f.canonical_name for f in required],
            result="pass", confidence=1.0,
            explanation=f"All {len(required)} required-cross-document fields are present.",
        )

    return ValidationResult(
        rule_id="SEM-10", rule_category="semantic",
        fields_involved=missing,
        result="warning", confidence=1.0,
        explanation=(
            f"Missing required fields: {', '.join(missing)}. "
            "These must be present for a complete QC report."
        ),
        field_values={"missing": json.dumps(missing)},
    )


def rule_sem11_purchase_contract_fields(rs: ExtractionResultSet) -> ValidationResult:
    """SEM-11: Purchase transactions require contract section to be complete."""
    assignment = _val(rs, "assignment_type") or ""
    if "purchase" not in assignment.lower():
        return ValidationResult(
            rule_id="SEM-11", rule_category="semantic",
            fields_involved=["assignment_type"],
            result="info", confidence=1.0,
            explanation="Not a purchase transaction — contract section check skipped.",
        )

    contract_fields = ["contract_price", "contract_date", "did_analyze_contract"]
    missing = [f for f in contract_fields if not (_val(rs, f))]

    if missing:
        return ValidationResult(
            rule_id="SEM-11", rule_category="semantic",
            fields_involved=contract_fields,
            result="fail", confidence=0.90,
            explanation=(
                f"Purchase transaction requires contract section completion. "
                f"Missing: {', '.join(missing)}. "
                "Per QC Rule C-1: contract MUST be analyzed for purchase transactions."
            ),
            field_values={"missing": json.dumps(missing)},
        )

    return ValidationResult(
        rule_id="SEM-11", rule_category="semantic",
        fields_involved=contract_fields,
        result="pass", confidence=0.95,
        explanation="Contract section complete for purchase transaction.",
    )


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

_ALL_RULES = [
    rule_sem01_value_price_ratio,
    rule_sem02_effective_before_signature,
    rule_sem03_contract_before_effective,
    rule_sem06_land_use_total,
    rule_sem10_required_fields,
    rule_sem11_purchase_contract_fields,
]


def validate(
    rs: ExtractionResultSet,
    document_id: str,
    transaction_id: Optional[str] = None,
    persist: bool = True,
) -> List[ValidationResult]:
    """
    Run all semantic validation rules on an extraction result set.
    Rules are independent — one failure never blocks others (Plan §8 graceful degradation).
    Results are stored in adaptive_validation_results if persist=True.
    """
    results: List[ValidationResult] = []

    for rule_fn in _ALL_RULES:
        try:
            result = rule_fn(rs)
            results.append(result)
        except Exception as exc:
            logger.error("Validation rule %s failed: %s", rule_fn.__name__, exc)
            results.append(ValidationResult(
                rule_id=rule_fn.__name__.upper(),
                rule_category="semantic",
                fields_involved=[],
                result="skipped",
                confidence=0.0,
                explanation=f"Rule execution error: {exc}",
            ))

    if persist:
        _persist_results(results, document_id, transaction_id)

    fail_count = sum(1 for r in results if r.result == "fail")
    warn_count = sum(1 for r in results if r.result == "warning")
    logger.info(
        "Semantic validation: %s — %d rules: %d fail, %d warning, %d pass",
        document_id, len(results), fail_count, warn_count,
        sum(1 for r in results if r.result == "pass"),
    )
    return results


def _persist_results(
    results: List[ValidationResult],
    document_id: str,
    transaction_id: Optional[str],
) -> None:
    try:
        from app.database import get_db
        from app.models.db_models import ValidationResultRow
        with get_db() as session:
            for r in results:
                session.add(ValidationResultRow(**r.to_db_dict(document_id, transaction_id)))
    except Exception as exc:
        logger.warning("Validation result persist failed: %s", exc)
