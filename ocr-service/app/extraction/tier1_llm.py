"""
Day 13 — Tier One LLM Extraction

Uses a local Ollama LLM (mistral:7b) to extract fields that spatial and
pattern matching cannot find. This is the final fallback tier — it runs
AFTER spatial (Tier 3) and embedding (Tier 2) extraction.

The Architecture Guide's three-tier ordering is:
  Tier 1 — Pattern + spatial (Weeks 1-2)
  Tier 2 — Embedding similarity (Day 15-16)
  Tier 3 — LLM semantic understanding (Day 13-14, most powerful, used last)

The 30-day plan names this "Tier One LLM" because it was built first in Week 3;
the Architecture Guide calls it Tier Three because it runs last in the pipeline.
Both refer to this same component.

Hallucination detection: every LLM value is verified against the cited source
text. Unverifiable values get hallucination_flag=True and confidence capped at 0.40.
LLM timeout / Ollama unavailability → returns empty dict, pipeline continues (Rule 9).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_TEXT_MODEL, OLLAMA_TIMEOUT_TEXT
from app.core.result import ExtractionMethod, ExtractionResult, ExtractionResultSet
from app.core.schema import FieldDefinition, schema_loader

logger = logging.getLogger(__name__)

_HALLUCINATION_CONFIDENCE_CAP = 0.40
_LLM_BASE_CONFIDENCE = 0.72          # before source verification
_LLM_VERIFIED_CONFIDENCE = 0.82      # after source text confirmed
_LLM_EXTRACTION_METHOD = ExtractionMethod.LLM_INFERENCE


# ---------------------------------------------------------------------------
# Section-specific field groups
# (LLM is only invoked for fields in these groups that spatial didn't find)
# ---------------------------------------------------------------------------

# Fields by form section — what the LLM targets per chunk
_SECTION_FIELDS: Dict[str, List[str]] = {
    "subject": [
        "borrower_name", "co_borrower_name", "owner_of_public_record",
        "lender_name", "lender_address", "property_rights", "assignment_type",
        "occupant_status", "offered_for_sale_12mo", "data_source", "mls_number",
        "neighborhood_name", "hoa_period",
    ],
    "contract": [
        "assignment_type", "did_analyze_contract", "sale_type",
        "contract_analysis_comment", "is_seller_owner_of_record",
        "has_financial_assistance", "personal_property_contributes_to_value",
    ],
    "condo_project": [
        "project_name", "project_primary_occupancy", "management_group_type",
        "is_developer_controls_hoa", "is_single_entity_owns_10pct",
        "is_project_from_conversion", "are_facilities_complete", "has_commercial_space",
        "commercial_space_pct", "is_parking_adequate",
    ],
    "neighborhood": [
        "location", "built_up", "growth_rate", "property_values",
        "demand_supply", "marketing_time", "neighborhood_boundaries",
        "neighborhood_description", "market_conditions_commentary",
    ],
    "site": [
        "site_view", "zoning_classification", "zoning_compliance",
        "highest_and_best_use", "fema_flood_hazard", "fema_flood_zone",
        "adverse_site_conditions",
    ],
    "improvements": [
        "design_style", "status", "foundation_type", "exterior_walls",
        "roof_surface", "heating", "cooling", "adverse_conditions",
        "conforms_to_neighborhood",
    ],
    "appraiser": [
        "appraiser_name", "appraiser_company_name", "appraiser_company_address",
        "appraiser_phone", "appraiser_email", "appraiser_state_cert_number",
        "appraiser_cert_state", "appraiser_cert_expiration_date",
        "date_of_signature", "appraisal_report_type", "reasonable_exposure_time",
        "supervisory_appraiser_name", "supervisory_appraiser_did_inspect",
    ],
    "reconciliation": [
        "final_reconciliation_comment", "appraisal_subject_to",
    ],
}

# For each section, which pages to send (relative to total pages)
_SECTION_PAGE_SLICES: Dict[str, tuple] = {
    "subject":       (0.0, 0.30),
    "contract":      (0.0, 0.30),
    "condo_project": (0.10, 0.45),
    "neighborhood":  (0.10, 0.35),
    "site":          (0.10, 0.45),
    "improvements":  (0.10, 0.50),
    "appraiser":     (0.55, 1.0),
    "reconciliation":(0.40, 0.80),
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a precision extraction assistant for real estate appraisal documents.
Your ONLY job is to find specific field values in the text provided.

CRITICAL RULES:
1. Return ONLY values that ACTUALLY APPEAR in the text. Never invent or infer values.
2. For each field, cite the EXACT source passage from the text where you found the value.
3. If a field is NOT present in the text, return {"found": false, "value": null}.
4. For checkbox fields, look for marked options (X, checked, selected) to determine the active value.
5. Return JSON ONLY — no explanatory text, no markdown, just the JSON object.
"""

_FIELD_DESCRIPTIONS: Dict[str, str] = {
    "borrower_name": "The borrower's full name (may also be called Client, Applicant, Customer)",
    "co_borrower_name": "Co-borrower or second borrower name",
    "owner_of_public_record": "Owner of Public Record (the person on the deed)",
    "lender_name": "Lender/Client name (bank or mortgage company)",
    "lender_address": "Lender/Client mailing address",
    "property_rights": "Property Rights Appraised — one of: Fee Simple, Leasehold, De Minimis PUD, Other",
    "assignment_type": "Assignment type — one of: Purchase Transaction, Refinance Transaction, Other",
    "occupant_status": "Occupant status — one of: Owner, Tenant, Vacant",
    "sale_type": "Type of sale — one of: Arms-Length, Non Arms-Length, REO, Short Sale, Court Ordered",
    "did_analyze_contract": "Whether appraiser analyzed the contract (true/false)",
    "is_seller_owner_of_record": "Whether property seller is the owner of public record (true/false)",
    "has_financial_assistance": "Whether there is financial assistance/concessions (true/false)",
    "location": "Neighborhood location — one of: Urban, Suburban, Rural",
    "built_up": "Neighborhood built-up percentage — one of: Over 75%, 25-75%, Under 25%",
    "growth_rate": "Growth rate — one of: Rapid, Stable, Slow",
    "property_values": "Property value trend — one of: Increasing, Stable, Declining",
    "demand_supply": "Demand/Supply — one of: Shortage, In Balance, Over Supply",
    "marketing_time": "Marketing time — one of: Under 3 mths, 3-6 mths, Over 6 mths",
    "neighborhood_boundaries": "Neighborhood boundaries (N, S, E, W descriptions)",
    "neighborhood_description": "Description of the neighborhood characteristics",
    "market_conditions_commentary": "Market conditions analysis narrative",
    "zoning_compliance": "Zoning compliance — one of: Legal, Legal Non-Conforming, No Zoning, Illegal",
    "highest_and_best_use": "Is current use the highest and best use (true/false)",
    "fema_flood_hazard": "Is property in FEMA flood hazard area (true/false)",
    "fema_flood_zone": "FEMA flood zone designation (e.g., X, AE, A)",
    "design_style": "Design style (e.g., Traditional, Ranch, Colonial, Contemporary)",
    "status": "Property status — one of: Existing, Proposed, Under Const.",
    "foundation_type": "Foundation type (e.g., Concrete Slab, Crawl Space, Full Basement)",
    "exterior_walls": "Exterior wall material",
    "roof_surface": "Roof surface material",
    "heating": "Heating system type",
    "cooling": "Cooling/air conditioning type",
    "project_name": "Condominium or development project name",
    "project_primary_occupancy": "Project primary occupancy — one of: Principal Residence, Second Home, Recreational, Tenant",
    "is_developer_controls_hoa": "Whether developer controls the HOA (true/false)",
    "appraiser_name": "Appraiser's full name (appears on signature page)",
    "appraiser_company_name": "Appraiser's company or firm name",
    "appraiser_company_address": "Appraiser's company address",
    "appraiser_phone": "Appraiser's phone number",
    "appraiser_email": "Appraiser's email address",
    "appraiser_state_cert_number": "Appraiser's state certification or license number",
    "appraiser_cert_state": "State where appraiser is certified",
    "appraiser_cert_expiration_date": "Appraiser's certification expiration date",
    "date_of_signature": "Date the appraiser signed the report",
    "appraisal_report_type": "Report type — one of: Appraisal Report, Restricted Appraisal Report",
    "reasonable_exposure_time": "Estimated reasonable exposure time (e.g., 60-90 days)",
    "supervisory_appraiser_name": "Supervisory appraiser name (if present)",
    "supervisory_appraiser_did_inspect": "Whether supervisory appraiser inspected property (true/false)",
    "appraisal_subject_to": "Whether appraisal is As Is or Subject To conditions",
    "final_reconciliation_comment": "Final reconciliation narrative text",
    "offered_for_sale_12mo": "Has property been offered for sale in prior 12 months (true/false)",
}


def _build_extraction_prompt(
    section: str,
    field_names: List[str],
    text_chunk: str,
    document_type: str,
) -> str:
    """Build a section-specific extraction prompt."""
    field_list = []
    for fname in field_names:
        desc = _FIELD_DESCRIPTIONS.get(fname, fname.replace("_", " ").title())
        fd = schema_loader.get_field(fname)
        examples = ""
        if fd and fd.synonyms:
            examples = f" (also called: {', '.join(fd.synonyms[:3])})"
        field_list.append(f'  "{fname}": "{desc}{examples}"')

    fields_json = "{\n" + ",\n".join(field_list) + "\n}"

    return f"""Extract the following fields from this {document_type} text.

FIELDS TO EXTRACT:
{fields_json}

DOCUMENT TEXT (section: {section}):
---
{text_chunk[:4000]}
---

Return ONLY this JSON structure:
{{
  "fields": {{
    "field_name": {{
      "found": true,
      "value": "extracted value",
      "source_text": "exact quote from document where value was found"
    }}
  }}
}}

For fields not found, return: {{"found": false, "value": null, "source_text": null}}
Do not invent values. Only return values that appear in the document text above.
"""


# ---------------------------------------------------------------------------
# Hallucination detection
# ---------------------------------------------------------------------------

def _verify_value_in_source(value: Optional[str], source_text: Optional[str], full_text: str) -> float:
    """
    Verify the extracted value can be grounded in the document text.
    Returns a confidence multiplier: 1.0 if verified, lower if suspicious.
    """
    if not value or not source_text:
        return 0.5  # can't verify without source text

    val_lower = str(value).lower().strip()
    source_lower = source_text.lower().strip()
    text_lower = full_text.lower()

    # Value must appear in the cited source text
    if val_lower not in source_lower:
        logger.debug("Hallucination: value %r not in source %r", value[:30], source_text[:50])
        return 0.3

    # Source text must appear (or be close) in the document
    if source_lower[:50] in text_lower:
        return 1.0

    # Fuzzy check: first 20 chars of source in document
    if len(source_lower) > 10 and source_lower[:20] in text_lower:
        return 0.85

    logger.debug("Weak verification: source not found in document text")
    return 0.6


# ---------------------------------------------------------------------------
# Ollama client — wrapped by resilience layer (all 13 failure modes)
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, chunk_text: str = "", amc_id: Optional[str] = None,
                 text_quality_score: float = 1.0) -> Optional[str]:
    """
    Call Ollama through the resilience layer.
    Defenses applied: circuit breaker, quality gate, AMC terminology, semaphore,
    model pinning, format validation. Rule 9 fallback always returns None on failure.
    """
    from app.extraction.llm_resilience import resilient_ollama_call
    return resilient_ollama_call(
        prompt=prompt,
        chunk_text=chunk_text,
        amc_id=amc_id,
        text_quality_score=text_quality_score,
    )


def _parse_llm_response(response_text: str) -> Dict[str, dict]:
    """
    Parse LLM JSON response. Robust against markdown code fences and extra text.
    Returns {field_name: {found, value, source_text}} or {}.
    """
    if not response_text:
        return {}

    # Strip markdown code fences
    text = re.sub(r"```(?:json)?", "", response_text).strip()

    # Find the first JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}

    try:
        parsed = json.loads(m.group(0))
        return parsed.get("fields", {})
    except json.JSONDecodeError as exc:
        logger.debug("LLM response JSON parse failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class LLMTier1Extractor:
    """
    Day 13 — LLM Tier 1 Extractor.

    Runs AFTER spatial extraction. Only invoked for fields that spatial
    returned NOT_FOUND, targeting the fields most likely benefited by
    LLM understanding (checkboxes, narrative fields, context-dependent labels).

    Sends section-specific page chunks — not the whole document — to keep
    prompts focused and within context window limits.
    """

    def __init__(self) -> None:
        self._schema = schema_loader
        self._available: Optional[bool] = None  # cached availability check

    def is_available(self) -> bool:
        if self._available is None:
            try:
                r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
                self._available = r.status_code == 200
            except Exception:
                self._available = False
        return self._available

    def extract_missing_fields(
        self,
        page_texts: Dict[int, str],
        document_type: str,
        already_found: Dict[str, ExtractionResult],
        total_pages: int,
        amc_id: Optional[str] = None,
        page_quality_scores: Optional[Dict[int, float]] = None,
    ) -> Dict[str, ExtractionResult]:
        """
        Extract fields that spatial extraction didn't find.
        amc_id: used for terminology normalization before sending to LLM (Defense 1+10).
        page_quality_scores: OCR quality per page — low-quality pages skip LLM (Defense 5).
        Returns a dict of {canonical_name: ExtractionResult} for newly found fields.
        """
        from app.extraction.llm_resilience import check_ollama_health, _circuit_is_open
        if _circuit_is_open():
            logger.info("LLM circuit breaker open — skipping all LLM extraction")
            return {}
        if not self.is_available():
            logger.info("Ollama not available — Tier 1 LLM skipped")
            return {}

        # Build full document text for verification
        full_text = "\n".join(page_texts.get(p, "") for p in sorted(page_texts))

        results: Dict[str, ExtractionResult] = {}

        for section, field_names in _SECTION_FIELDS.items():
            # Only extract fields in this section that aren't already found
            missing_in_section = [
                f for f in field_names
                if f not in already_found or not already_found[f].found
                if self._schema.get_field(f) is not None
            ]
            if not missing_in_section:
                continue

            # Get the relevant page range for this section
            slice_start, slice_end = _SECTION_PAGE_SLICES.get(section, (0.0, 1.0))
            pages_sorted = sorted(page_texts.keys())
            start_idx = max(0, int(len(pages_sorted) * slice_start))
            end_idx = min(len(pages_sorted), int(len(pages_sorted) * slice_end) + 1)
            section_pages = pages_sorted[start_idx:end_idx]

            if not section_pages:
                continue

            # Concatenate the section's page texts
            chunk = "\n\n".join(
                f"[Page {p}]\n{page_texts[p]}"
                for p in section_pages
                if page_texts.get(p, "").strip()
            )
            if len(chunk.strip()) < 50:
                continue

            # Defense 5: compute average quality for this section's pages
            if page_quality_scores:
                section_quality = sum(page_quality_scores.get(p, 1.0) for p in section_pages) / max(len(section_pages), 1)
            else:
                section_quality = 1.0

            # Build prompt and call LLM through resilience layer
            prompt = _build_extraction_prompt(section, missing_in_section, chunk, document_type)
            start = time.time()
            response = _call_ollama(prompt, chunk_text=chunk, amc_id=amc_id, text_quality_score=section_quality)
            elapsed = int((time.time() - start) * 1000)

            if not response:
                logger.debug("LLM returned empty for section %s (%dms)", section, elapsed)
                continue

            logger.debug("LLM section=%s fields=%d time=%dms", section, len(missing_in_section), elapsed)

            # Parse and process results
            parsed = _parse_llm_response(response)
            for fname, field_data in parsed.items():
                if fname not in missing_in_section:
                    continue
                if not field_data.get("found") or field_data.get("value") is None:
                    continue

                value = str(field_data["value"]).strip()
                source_text = field_data.get("source_text") or ""
                if not value or value.lower() in ("null", "none", "n/a", ""):
                    continue

                # Defense 4: Tighter hallucination detection via resilience layer
                from app.extraction.llm_resilience import verify_extraction_against_source, validate_extracted_format
                verified, confidence_mult = verify_extraction_against_source(value, source_text, full_text)
                is_hallucination = not verified

                # Defense 7: Format validation
                fd = self._schema.get_field(fname)
                if fd and fd.data_type not in ("string", "string_list"):
                    fmt_ok, normalized_val = validate_extracted_format(value, fd.data_type)
                    if fmt_ok and normalized_val:
                        value = normalized_val
                    elif not fmt_ok:
                        logger.debug("LLM format invalid for %s: %r (type=%s)", fname, value[:30], fd.data_type)
                        continue  # skip this field — wrong format
                # Defense 11: use calibrated confidence, not LLM's self-reported
                from app.extraction.llm_resilience import llm_base_confidence
                base_conf = llm_base_confidence(verified)
                final_conf = min(
                    _HALLUCINATION_CONFIDENCE_CAP if is_hallucination else base_conf,
                    base_conf * confidence_mult,
                )

                # Find approximate source page
                source_page = 1
                for pn, pt in sorted(page_texts.items()):
                    if source_text[:30] and source_text[:30].lower() in pt.lower():
                        source_page = pn
                        break

                results[fname] = ExtractionResult(
                    canonical_name=fname,
                    document_type=document_type,
                    value=value,
                    raw_source_text=source_text[:500],
                    extraction_method=_LLM_EXTRACTION_METHOD,
                    confidence=round(final_conf, 3),
                    source_page=source_page,
                    hallucination_flag=is_hallucination,
                    normalization_applied=["llm_tier1"],
                )

                if is_hallucination:
                    logger.warning(
                        "Hallucination flagged: field=%s value=%r source=%r",
                        fname, value[:30], source_text[:40],
                    )
                else:
                    logger.debug(
                        "LLM found: %s=%r conf=%.2f page=%d",
                        fname, value[:30], final_conf, source_page,
                    )

        return results
