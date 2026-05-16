"""
Day 9 — Document Classifier

Two-level classification:
  Level 1 — Broad category: appraisal_report | engagement_letter | sales_contract
             | qc_checklist | unknown
  Level 2 — AMC template: which AMC's template is this, and what version

Keyword signatures are built from ACTUAL text observed in our 6 test batches.
Every keyword here was seen in a real document — not guessed.

AMC fingerprint: structural properties (page count, section headers, software markers)
used to match against amc_profiles table entries.

Per the plan (Day 9): "Build the keyword signature lists based on careful reading
of your real test documents. Do not guess what keywords appear in each document type."
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword signatures — derived from reading actual test documents
# ---------------------------------------------------------------------------

# Keywords that reliably appear in EACH document type (observed in real docs)
# Format: (keyword_pattern, weight)
# Higher weight = stronger signal for this document type

APPRAISAL_SIGNATURES: List[Tuple[str, float]] = [
    ("uniform residential appraisal report", 3.0),
    ("form 1004", 3.0),
    ("form 1073", 3.0),                       # condo form
    ("form 1004uad", 3.0),
    ("uad", 2.0),
    ("uspap", 2.0),
    ("sales comparison approach", 2.5),
    ("comparable sale", 2.0),
    ("appraised value", 2.0),
    ("opinion of value", 2.0),
    ("reconciliation", 1.5),
    ("effective date", 1.5),
    ("subject property", 1.5),
    ("neighborhood characteristics", 1.5),
    ("esign.alamode.com", 2.5),                # TOTAL software marker
    ("a la mode", 2.0),                        # TOTAL software marker
    ("appraisal of real property", 2.5),
    ("certification", 1.0),
    ("scope of work", 1.5),
    ("highest and best use", 1.5),
    ("above grade", 1.5),
    ("gross living area", 2.0),
]

ENGAGEMENT_SIGNATURES: List[Tuple[str, float]] = [
    ("file id:", 3.0),                         # Equity Solutions format
    ("file no.:", 2.5),                        # Henderson format
    ("service fee:", 3.0),
    ("priority:", 2.5),                        # Rush / Standard
    ("assigned:", 2.5),
    ("entry contact:", 2.5),
    ("equity solutions", 3.0),
    ("intended use:", 2.0),
    ("order:", 2.0),
    ("form: conventional", 2.0),
    ("due:", 2.0),
    ("appraiser:", 2.0),
    ("engagement", 1.5),
    ("order form", 2.0),
    ("assignment", 1.5),
]

CONTRACT_SIGNATURES: List[Tuple[str, float]] = [
    ("buyer", 2.0),
    ("seller", 2.0),
    ("closing date", 2.5),
    ("purchase price", 2.5),
    ("earnest money", 2.5),
    ("financing contingency", 2.5),
    ("escrow", 1.5),
    ("paragraph", 1.0),
    ("closing costs", 2.0),
    ("shall", 1.0),
    ("docusign envelope", 2.0),                # DocuSign contract marker
    ("purchase agreement", 2.5),
    ("contract for sale", 2.0),
]

QC_SIGNATURES: List[Tuple[str, float]] = [
    ("quality control", 3.0),
    ("qc checklist", 3.0),
    ("deficiency", 2.0),
    ("condition rating", 2.0),
    ("compliance", 1.5),
    ("revision request", 2.5),
    ("review checklist", 2.0),
]

_SIGNATURES: Dict[str, List[Tuple[str, float]]] = {
    "appraisal_report": APPRAISAL_SIGNATURES,
    "engagement_letter": ENGAGEMENT_SIGNATURES,
    "sales_contract": CONTRACT_SIGNATURES,
    "qc_checklist": QC_SIGNATURES,
}


# ---------------------------------------------------------------------------
# AMC structural fingerprints — derived from real documents
# ---------------------------------------------------------------------------

# Each AMC profile has identifying markers observed in their documents
AMC_FINGERPRINTS: Dict[str, dict] = {
    "henderson_appraisal": {
        "markers": ["henderson appraisal", "craig bardes", "henderson appraisal services"],
        "doc_types": ["appraisal_report", "engagement_letter"],
        "page_range": [8, 30],
        "software": ["total appraisal software", "a la mode"],
        "states": ["GA"],
    },
    "equity_solutions_usa": {
        "markers": ["equity solutions usa", "equity solutions"],
        "doc_types": ["appraisal_report", "engagement_letter"],
        "page_range": [6, 40],
        "software": ["total appraisal software", "a la mode", "esign.alamode.com"],
        "states": ["FL", "TX", "WV", "AZ"],
    },
    "blue_palm_appraisal": {
        "markers": ["blue palm appraisal"],
        "doc_types": ["appraisal_report"],
        "page_range": [20, 35],
        "software": ["total appraisal software", "a la mode"],
        "states": ["FL"],
    },
    "jm_property_appraisal": {
        "markers": ["jm property appraisal", "juan mendoza"],
        "doc_types": ["appraisal_report"],
        "page_range": [25, 35],
        "software": ["esign.alamode.com"],
        "states": ["FL"],
    },
    "freese_and_co": {
        "markers": ["freese", "riley freese", "freese & company"],
        "doc_types": ["appraisal_report"],
        "page_range": [20, 35],
        "states": ["TX"],
    },
    "brian_mccoy_appraisals": {
        "markers": ["brian mccoy", "bma"],
        "doc_types": ["appraisal_report"],
        "page_range": [1, 10],  # 1004D is a short form
        "states": ["WV"],
    },
}

# Template version markers (within an AMC's docs)
TEMPLATE_VERSION_MARKERS = {
    "equity_solutions_usa": {
        "v2026": ["file id:", "priority:", "entry contact:"],    # current format
        "v2025": ["file id:", "priority:"],
    },
    "henderson_appraisal": {
        "v2026": ["henderson appraisal services", "2026"],
    },
}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    document_type: str
    type_confidence: float
    keyword_scores: Dict[str, float]         # {doc_type: score}
    amc_id: Optional[str] = None
    amc_template_version: Optional[str] = None
    amc_match_score: Optional[float] = None
    fingerprint: Dict = field(default_factory=dict)

    @property
    def is_confident(self) -> bool:
        return self.type_confidence >= 0.60

    @property
    def is_appraisal(self) -> bool:
        return self.document_type == "appraisal_report"

    @property
    def is_engagement(self) -> bool:
        return self.document_type == "engagement_letter"

    @property
    def is_contract(self) -> bool:
        return self.document_type == "sales_contract"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class DocumentClassifier:
    """
    Classifies a document before extraction begins.
    Uses first 2 pages for broad category; all pages for AMC fingerprinting.

    Per the plan: keyword signatures from real test documents, not guesses.
    """

    def classify(self, text_by_page: Dict[int, str], total_pages: int) -> ClassificationResult:
        """
        Classify a document.
        text_by_page: {page_number: normalized_text} (1-indexed)
        """
        # Use first 2 pages for keyword scoring
        sample_text = ""
        for pn in sorted(text_by_page.keys())[:2]:
            sample_text += " " + text_by_page[pn]
        sample_lower = sample_text.lower()

        # Score each document type
        scores: Dict[str, float] = {}
        for doc_type, sigs in _SIGNATURES.items():
            score = 0.0
            for keyword, weight in sigs:
                if keyword.lower() in sample_lower:
                    score += weight
            scores[doc_type] = round(score, 2)

        # Pick winner and compute confidence
        if not scores or max(scores.values()) == 0:
            winner = "unknown"
            confidence = 0.0
        else:
            winner = max(scores, key=scores.get)
            total = sum(scores.values())
            confidence = scores[winner] / total if total > 0 else 0.0

        # Structural fingerprint of this document
        fingerprint = self._build_fingerprint(text_by_page, total_pages)

        # AMC identification
        all_text = " ".join(text_by_page.values()).lower()
        amc_id, amc_version, amc_score = self._identify_amc(all_text, total_pages)

        result = ClassificationResult(
            document_type=winner,
            type_confidence=round(confidence, 3),
            keyword_scores=scores,
            amc_id=amc_id,
            amc_template_version=amc_version,
            amc_match_score=amc_score,
            fingerprint=fingerprint,
        )

        logger.info(
            "Classified: %s (%.0f%% confidence) | AMC: %s",
            winner, confidence * 100, amc_id or "unknown",
        )
        return result

    def _build_fingerprint(self, text_by_page: Dict[int, str], total_pages: int) -> dict:
        """Build a structural fingerprint for AMC profile matching."""
        all_text = " ".join(text_by_page.values()).lower()

        # Detect software markers
        software = []
        if "alamode" in all_text or "a la mode" in all_text:
            software.append("a_la_mode_total")
        if "esign.alamode.com" in all_text:
            software.append("a_la_mode_esign")
        if "docusign" in all_text:
            software.append("docusign")

        # Detect form type
        form_type = "unknown"
        if "form 1004uad" in all_text or "form 1004" in all_text:
            form_type = "1004"
        elif "form 1073" in all_text or "1073" in all_text:
            form_type = "1073"
        elif "1004d" in all_text:
            form_type = "1004d"

        # Detect state
        states_found = []
        state_pattern = re.compile(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b")
        for match in state_pattern.finditer(all_text.upper()):
            states_found.append(match.group(0))

        # Detect section headers present
        section_headers = []
        for header in ["subject", "contract", "neighborhood", "site", "improvements",
                       "sales comparison", "reconciliation", "certification"]:
            if re.search(rf"\b{header}\b", all_text):
                section_headers.append(header)

        return {
            "total_pages": total_pages,
            "software": list(set(software)),
            "form_type": form_type,
            "states_detected": list(set(states_found))[:5],
            "section_headers_present": section_headers,
            "text_density": round(sum(len(t) for t in text_by_page.values()) / max(total_pages, 1)),
        }

    def _identify_amc(
        self, all_text_lower: str, total_pages: int
    ) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """Match document text against known AMC fingerprints."""
        best_amc = None
        best_score = 0.0
        best_version = None

        for amc_id, fp in AMC_FINGERPRINTS.items():
            score = 0.0
            for marker in fp.get("markers", []):
                if marker.lower() in all_text_lower:
                    score += 1.0

            # Page count check
            page_range = fp.get("page_range", [0, 999])
            if page_range[0] <= total_pages <= page_range[1]:
                score += 0.5

            if score > best_score:
                best_score = score
                best_amc = amc_id

                # Try to identify template version
                version_markers = TEMPLATE_VERSION_MARKERS.get(amc_id, {})
                for version, markers in version_markers.items():
                    if all(m.lower() in all_text_lower for m in markers):
                        best_version = version
                        break

        if best_score == 0:
            return None, None, None

        # Normalize score to 0-1
        max_possible = max(
            len(AMC_FINGERPRINTS[amc_id]["markers"]) + 0.5
            for amc_id in AMC_FINGERPRINTS
        )
        normalized = min(1.0, best_score / max_possible)

        return best_amc, best_version, round(normalized, 3)

    def persist(self, result: ClassificationResult, document_id: str, document_path: str) -> None:
        """Store classification result in adaptive_document_classifications."""
        from app.database import get_db
        from app.models.db_models import DocumentClassificationRow, AmcProfileRow

        with get_db() as session:
            row = DocumentClassificationRow(
                document_id=document_id,
                document_path=document_path,
                document_type=result.document_type,
                type_confidence=result.type_confidence,
                keyword_scores_json=json.dumps(result.keyword_scores),
                amc_id=result.amc_id,
                amc_template_version=result.amc_template_version,
                amc_match_score=result.amc_match_score,
                fingerprint_json=json.dumps(result.fingerprint),
                total_pages=result.fingerprint.get("total_pages", 0),
            )
            session.add(row)

            # Create or update AMC profile (Layer Four — format registry)
            if result.amc_id:
                existing = session.query(AmcProfileRow).filter_by(
                    amc_id=result.amc_id
                ).first()
                if not existing:
                    # Build initial terminology mapping from known AMC fingerprints
                    term_map = self._build_initial_terminology(result.amc_id)
                    profile = AmcProfileRow(
                        amc_id=result.amc_id,
                        amc_name=result.amc_id.replace("_", " ").title(),
                        document_count=1,
                        maturity_level="new",
                        fingerprint_json=json.dumps(result.fingerprint),
                        terminology_mapping_json=json.dumps(term_map),
                        confidence_threshold_overrides_json=json.dumps({}),
                    )
                    session.add(profile)
                    logger.info(
                        "Created AMC profile: %s — %d terminology mappings",
                        result.amc_id, len(term_map),
                    )
                else:
                    # Update fingerprint (merge with existing by averaging structural props)
                    existing.document_count += 1
                    if existing.document_count >= 50:
                        existing.maturity_level = "mature"
                    elif existing.document_count >= 10:
                        existing.maturity_level = "developing"
                    # Update fingerprint with latest document's properties
                    existing.fingerprint_json = json.dumps(result.fingerprint)


    def _build_initial_terminology(self, amc_id: str) -> dict:
        """
        Build the initial terminology mapping for a new AMC profile.
        This maps AMC-specific label variants to canonical field names,
        derived from the AMC fingerprints we've observed in real documents.

        Format: {amc_label_variant: canonical_field_name}
        This is the starting point — corrections will extend it via fast-path.
        """
        # Known terminology mappings observed in real documents from each AMC
        # (Architecture Guide §11: AMC Profile System — no code changes to onboard new AMC)
        _KNOWN_TERMINOLOGIES: dict = {
            "equity_solutions_usa": {
                "File ID": "lender_reference_number",
                "Service Fee": "appraisal_fee",
                "Entry Contact": "contact_name",
                "Champions Funding": "lender_name",
                "Form: Conventional 1004": "form_type",
                "Priority: Rush": "order_priority",
                "Priority: Standard": "order_priority",
            },
            "henderson_appraisal": {
                "Clear2Mortgage": "lender_name",
                "Henderson Appraisal Services": "appraiser_company_name",
                "SGAMLS": "mls_data_source",
            },
            "blue_palm_appraisal": {
                "Blue Palm Appraisal": "appraiser_company_name",
                "MatrixMLS": "mls_data_source",
            },
            "jm_property_appraisal": {
                "JM Property Appraisal Inc": "appraiser_company_name",
                "SEFMLS": "mls_data_source",
                "Champions Fundings": "lender_name",
            },
            "freese_and_co": {
                "Freese & Company": "appraiser_company_name",
                "Freese & Co": "appraiser_company_name",
            },
        }
        return _KNOWN_TERMINOLOGIES.get(amc_id, {})

    def apply_amc_terminology(self, text: str, amc_id: str) -> str:
        """
        Apply AMC-specific terminology normalization before extraction.
        Translates AMC-specific labels to canonical equivalents so the
        extraction tier doesn't need AMC-specific code.
        Architecture Guide §11: 'AMC onboarding is a configuration task, not a development task.'
        """
        try:
            from app.database import get_db
            from app.models.db_models import AmcProfileRow
            with get_db() as session:
                profile = session.query(AmcProfileRow).filter_by(amc_id=amc_id).first()
                if not profile:
                    return text
                term_map = profile.get_terminology_mapping()
                for amc_term, canonical in term_map.items():
                    text = text.replace(amc_term, canonical)
        except Exception:
            pass
        return text


# Module-level singleton
document_classifier = DocumentClassifier()
