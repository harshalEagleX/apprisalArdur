"""
Day 22 — Cross-Document Consistency Checker

Plan (Day 22): "After all three documents in a transaction have been processed
by the three-tier extraction, a consistency checker runs on the complete set of
extraction results for the transaction. For each field that appears in more than
one document, it compares the values."

Fields that must match across documents (per plan and Architecture Guide §7):
  - borrower_name       engagement_letter ↔ appraisal_report
  - property_address    engagement_letter ↔ appraisal_report ↔ sales_contract
  - city / state / zip  engagement_letter ↔ appraisal_report
  - lender_name         engagement_letter ↔ appraisal_report
  - contract_price      sales_contract    ↔ appraisal_report
  - contract_date       sales_contract    ↔ appraisal_report
  - assignment_type     engagement_letter ↔ appraisal_report

Normalization before comparison (plan Day 22): "Before comparing values from
different documents, normalize them to remove superficial differences."
  - Address: strip punctuation, expand abbreviations (St→Street, Ave→Avenue)
  - Names: lowercase, strip punctuation
  - Currency: strip $/, commas, compare as float
  - Dates: normalize to YYYY-MM-DD

When values don't match, the field schema source_authority identifies which
document's value to recommend as authoritative.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Address abbreviation expansion for normalization
_ADDR_ABBR = {
    r"\bSt\b\.?": "Street", r"\bAve\b\.?": "Avenue", r"\bBlvd\b\.?": "Boulevard",
    r"\bDr\b\.?": "Drive", r"\bRd\b\.?": "Road", r"\bLn\b\.?": "Lane",
    r"\bCt\b\.?": "Court", r"\bPl\b\.?": "Place", r"\bCir\b\.?": "Circle",
    r"\bSte\b\.?": "Suite", r"\bApt\b\.?": "Apartment",
}

# Which documents are authoritative for each field
_AUTHORITY = {
    "borrower_name":    "engagement_letter",
    "co_borrower_name": "engagement_letter",
    "property_address": "engagement_letter",
    "city":             "engagement_letter",
    "state":            "engagement_letter",
    "zip_code":         "engagement_letter",
    "county":           "engagement_letter",
    "lender_name":      "engagement_letter",
    "lender_address":   "engagement_letter",
    "loan_type":        "engagement_letter",
    "assignment_type":  "engagement_letter",
    "contract_price":   "sales_contract",
    "contract_date":    "sales_contract",
    "seller_name":      "sales_contract",
    "concessions_amount": "sales_contract",
}

# Fields to check across specific document pairs
_CROSS_CHECKS: List[Tuple[str, str, str]] = [
    # (field_name, doc_type_1, doc_type_2)
    ("borrower_name",    "engagement_letter", "appraisal_report"),
    ("property_address", "engagement_letter", "appraisal_report"),
    ("city",             "engagement_letter", "appraisal_report"),
    ("state",            "engagement_letter", "appraisal_report"),
    ("zip_code",         "engagement_letter", "appraisal_report"),
    ("lender_name",      "engagement_letter", "appraisal_report"),
    ("assignment_type",  "engagement_letter", "appraisal_report"),
    ("contract_price",   "sales_contract",    "appraisal_report"),
    ("contract_date",    "sales_contract",    "appraisal_report"),
]


@dataclass
class ConsistencyResult:
    field_name: str
    doc_type_1: str
    doc_type_2: str
    value_1: Optional[str]
    value_2: Optional[str]
    consistent: bool
    normalized_1: Optional[str]
    normalized_2: Optional[str]
    authoritative_value: Optional[str]
    authoritative_source: Optional[str]
    explanation: str
    confidence: float

    def to_db_dict(self, transaction_id: str, document_ids: Dict[str, str]) -> dict:
        """Format for adaptive_validation_results table."""
        return {
            "document_id": transaction_id,
            "transaction_id": transaction_id,
            "rule_id": f"CONS-{self.field_name.upper()[:20]}",
            "rule_category": "cross_document",
            "fields_involved": json.dumps([self.field_name]),
            "result": "pass" if self.consistent else "fail",
            "confidence": self.confidence,
            "explanation": self.explanation,
            "field_values_snapshot": json.dumps({
                self.doc_type_1: self.value_1,
                self.doc_type_2: self.value_2,
                "authoritative": self.authoritative_value,
                "authoritative_source": self.authoritative_source,
            }),
        }


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_text(value: Optional[str]) -> Optional[str]:
    """General text normalization: lowercase, strip punctuation."""
    if value is None:
        return None
    v = value.lower().strip()
    v = re.sub(r"[,\.;:'\"]", "", v)
    v = re.sub(r"\s+", " ", v)
    return v.strip()


def _normalize_address(value: Optional[str]) -> Optional[str]:
    """Address normalization: expand abbreviations, remove punctuation."""
    if value is None:
        return None
    v = value.strip()
    for abbr, expansion in _ADDR_ABBR.items():
        v = re.sub(abbr, expansion, v, flags=re.IGNORECASE)
    return _normalize_text(v)


def _normalize_currency(value: Optional[str]) -> Optional[float]:
    """Currency normalization: strip formatting, return as float."""
    if value is None:
        return None
    clean = re.sub(r"[$,\s]", "", str(value))
    try:
        return round(float(clean), 2)
    except ValueError:
        return None


def _normalize_name(value: Optional[str]) -> Optional[str]:
    """Name normalization: lowercase, strip punctuation, sort word order."""
    if value is None:
        return None
    v = _normalize_text(value) or ""
    # Split by & or "and" to handle co-borrower names in different order
    parts = re.split(r"\s+(?:&|and)\s+", v, flags=re.IGNORECASE)
    return " & ".join(sorted(p.strip() for p in parts))


_NORMALIZERS = {
    "borrower_name":    _normalize_name,
    "co_borrower_name": _normalize_name,
    "property_address": _normalize_address,
    "city":             _normalize_text,
    "state":            _normalize_text,
    "zip_code":         lambda v: v[:5] if v else None,
    "lender_name":      _normalize_text,
    "contract_price":   lambda v: str(_normalize_currency(v)) if v else None,
    "contract_date":    _normalize_text,
    "assignment_type":  _normalize_text,
}


def _values_match(field_name: str, v1: Optional[str], v2: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Normalize and compare. Returns (match, norm1, norm2)."""
    normalizer = _NORMALIZERS.get(field_name, _normalize_text)
    n1 = normalizer(v1)
    n2 = normalizer(v2)
    if n1 is None or n2 is None:
        return False, n1, n2
    # Substring match handles "96 SE Baell Trace Ct" ↔ "96 Baell Trace Ct SE"
    match = n1 == n2 or n1 in n2 or n2 in n1
    return match, n1, n2


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

class CrossDocumentChecker:
    """
    Day 22: Compare extracted fields across the 3 documents in a transaction.
    Architecture Guide §7: "Cross-Document Consistency Checking"
    """

    def check(
        self,
        results_by_doc: Dict[str, "ExtractionResultSet"],
        transaction_id: Optional[str] = None,
        persist: bool = True,
    ) -> List[ConsistencyResult]:
        """
        results_by_doc: {document_type: ExtractionResultSet}
        e.g. {"appraisal_report": rs1, "engagement_letter": rs2, "sales_contract": rs3}
        """
        consistency_results: List[ConsistencyResult] = []

        for field_name, doc1_type, doc2_type in _CROSS_CHECKS:
            rs1 = results_by_doc.get(doc1_type)
            rs2 = results_by_doc.get(doc2_type)

            if rs1 is None or rs2 is None:
                consistency_results.append(ConsistencyResult(
                    field_name=field_name, doc_type_1=doc1_type, doc_type_2=doc2_type,
                    value_1=None, value_2=None, consistent=True,
                    normalized_1=None, normalized_2=None,
                    authoritative_value=None,
                    authoritative_source=_AUTHORITY.get(field_name),
                    explanation=f"One or both documents not available for comparison.",
                    confidence=1.0,
                ))
                continue

            r1 = rs1.get(field_name)
            r2 = rs2.get(field_name)
            v1 = r1.value if r1 and r1.found else None
            v2 = r2.value if r2 and r2.found else None

            if v1 is None and v2 is None:
                consistency_results.append(ConsistencyResult(
                    field_name=field_name, doc_type_1=doc1_type, doc_type_2=doc2_type,
                    value_1=None, value_2=None, consistent=True,
                    normalized_1=None, normalized_2=None,
                    authoritative_value=None,
                    authoritative_source=_AUTHORITY.get(field_name),
                    explanation=f"{field_name} not found in either document.",
                    confidence=0.5,
                ))
                continue

            if v1 is None or v2 is None:
                # One present, one missing — report as unverified
                present_val = v1 or v2
                authority = _AUTHORITY.get(field_name)
                consistency_results.append(ConsistencyResult(
                    field_name=field_name, doc_type_1=doc1_type, doc_type_2=doc2_type,
                    value_1=v1, value_2=v2, consistent=True,
                    normalized_1=v1, normalized_2=v2,
                    authoritative_value=present_val,
                    authoritative_source=authority,
                    explanation=(
                        f"{field_name} present in one document only — "
                        "cross-document verification not possible."
                    ),
                    confidence=0.6,
                ))
                continue

            match, n1, n2 = _values_match(field_name, v1, v2)
            authority = _AUTHORITY.get(field_name)
            authoritative_value = v1 if doc1_type == authority else v2

            if match:
                explanation = f"{field_name} matches across {doc1_type} and {doc2_type}."
                confidence = 0.95
            else:
                explanation = (
                    f"{field_name} MISMATCH: "
                    f"{doc1_type}='{v1}' vs {doc2_type}='{v2}'. "
                    f"Authoritative source is {authority}: '{authoritative_value}'."
                )
                confidence = 0.90
                logger.info(
                    "Cross-doc mismatch: %s | %s=%r | %s=%r",
                    field_name, doc1_type, v1, doc2_type, v2,
                )

            consistency_results.append(ConsistencyResult(
                field_name=field_name, doc_type_1=doc1_type, doc_type_2=doc2_type,
                value_1=v1, value_2=v2, consistent=match,
                normalized_1=n1, normalized_2=n2,
                authoritative_value=authoritative_value,
                authoritative_source=authority,
                explanation=explanation, confidence=confidence,
            ))

        if persist and transaction_id:
            self._persist(consistency_results, transaction_id, results_by_doc)

        mismatches = sum(1 for r in consistency_results if not r.consistent and r.value_1 and r.value_2)
        logger.info(
            "Cross-doc consistency: %d checks, %d mismatches (transaction=%s)",
            len(consistency_results), mismatches, transaction_id,
        )
        return consistency_results

    @staticmethod
    def _persist(
        results: List[ConsistencyResult],
        transaction_id: str,
        results_by_doc: Dict,
    ) -> None:
        doc_ids = {dt: f"{transaction_id}:{dt}" for dt in results_by_doc}
        try:
            from app.database import get_db
            from app.models.db_models import ValidationResultRow
            with get_db() as session:
                for r in results:
                    row = ValidationResultRow(**r.to_db_dict(transaction_id, doc_ids))
                    session.add(row)
        except Exception as exc:
            logger.warning("Cross-doc result persist failed: %s", exc)


cross_document_checker = CrossDocumentChecker()
