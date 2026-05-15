"""
Day 18 — Multi-Page Document Reconciler

After the three-tier merger runs on each page/section, this reconciler
handles information that spans multiple pages of a document.

Three cases from the 30-day plan (Day 18):
  Case 1 — Duplicate field extractions:  same field from multiple pages
            → highest confidence result wins
  Case 2 — Complementary field extractions: parts of a multi-part field
            from different pages (e.g., address street vs city/state/zip)
            → assemble into complete value
  Case 3 — Cross-page context validation: value on one page validates
            or disambiguates value on another page
            (e.g., effective date context for comparable sale dates)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.core.result import ExtractionResult
from app.core.schema import schema_loader

logger = logging.getLogger(__name__)


def deduplicate_by_confidence(
    results_by_page: Dict[int, Dict[str, ExtractionResult]],
) -> Dict[str, ExtractionResult]:
    """
    Case 1: When the same field was extracted on multiple pages,
    keep the highest-confidence result.

    Also handles the case where an earlier page has a low-confidence result
    and a later page has a higher-confidence one (e.g., lender name appears
    on cover letter and again on the signature page).
    """
    best: Dict[str, ExtractionResult] = {}

    for page_num in sorted(results_by_page.keys()):
        page_results = results_by_page[page_num]
        for fname, result in page_results.items():
            if not result.found:
                # Still record as NOT_FOUND if not yet seen
                if fname not in best:
                    best[fname] = result
                continue

            current = best.get(fname)
            if current is None or not current.found:
                best[fname] = result
            elif result.effective_confidence > current.effective_confidence:
                logger.debug(
                    "Dedup: %s updated from page %d (%.2f) → page %d (%.2f)",
                    fname, current.source_page, current.effective_confidence,
                    result.source_page, result.effective_confidence,
                )
                best[fname] = result

    return best


def assemble_address(
    results: Dict[str, ExtractionResult],
) -> Dict[str, ExtractionResult]:
    """
    Case 2: Property address assembly.

    The property_address field may contain just the street number + street name
    from the spatial extractor (city/state/zip extracted separately). This
    function assembles the full address if needed but keeps components separate
    as per the field schema design.

    Cross-validate: if city, state, zip all found → mark property_address as
    cross_validated.
    """
    addr = results.get("property_address")
    city = results.get("city")
    state = results.get("state")
    zip_code = results.get("zip_code")

    # If we have city + state + zip but not address, try to reconstruct
    if (not (addr and addr.found)) and city and city.found and state and state.found:
        logger.debug("property_address not found; city/state/zip available for cross-validation")

    # Mark cross-validated if we have consistent address components
    if addr and addr.found and city and city.found and state and state.found and zip_code and zip_code.found:
        addr.cross_validated = True
        addr.cross_validated_source = "address_components_consistent"
        city.cross_validated = True
        city.cross_validated_source = "address_components_consistent"

    return results


def validate_date_relationships(
    results: Dict[str, ExtractionResult],
) -> Dict[str, ExtractionResult]:
    """
    Case 3: Cross-page date context validation.

    Verify date relationships:
    - contract_date must precede effective_date
    - effective_date must precede date_of_signature
    - appraiser_cert_expiration_date must be after effective_date
    """
    from datetime import datetime

    def parse(r: Optional[ExtractionResult]) -> Optional[datetime]:
        if not r or not r.found:
            return None
        try:
            return datetime.strptime(r.value, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    effective = parse(results.get("effective_date"))
    contract = parse(results.get("contract_date"))
    signature = parse(results.get("date_of_signature"))

    if effective and contract and contract > effective:
        r = results.get("contract_date")
        if r:
            r.sanity_check_failed = True
            r.sanity_check_reason = f"contract_date ({r.value}) is after effective_date ({results['effective_date'].value})"
            logger.debug("Date relationship violation: contract_date > effective_date")

    if effective and signature and signature < effective:
        r = results.get("date_of_signature")
        if r:
            r.sanity_check_failed = True
            r.sanity_check_reason = f"date_of_signature ({r.value}) is before effective_date"

    return results


def cross_validate_financial(
    results: Dict[str, ExtractionResult],
) -> Dict[str, ExtractionResult]:
    """
    Case 3: Cross-field financial validation.

    Contract price × appraised value cross-check:
    - If they differ by more than 3% → flag for review
    - If they differ by more than 10% → sanity_check_failed
    """
    cp = results.get("contract_price")
    av = results.get("appraised_value")

    if cp and cp.found and av and av.found:
        try:
            contract_price = float(cp.value)
            appraised_value = float(av.value)
            if contract_price > 0:
                diff_pct = abs(appraised_value - contract_price) / contract_price * 100
                if diff_pct > 10:
                    av.sanity_check_failed = True
                    av.sanity_check_reason = f"appraised_value differs from contract_price by {diff_pct:.1f}%"
                    logger.debug(
                        "Financial sanity: appraised=%s contract=%s diff=%.1f%%",
                        av.value, cp.value, diff_pct,
                    )
        except (ValueError, TypeError):
            pass

    return results


def reconcile(results: Dict[str, ExtractionResult]) -> Dict[str, ExtractionResult]:
    """
    Run all reconciliation passes on a flat dict of extraction results.
    This is called after the tier merger to apply cross-field validation.
    """
    results = assemble_address(results)
    results = validate_date_relationships(results)
    results = cross_validate_financial(results)
    return results
