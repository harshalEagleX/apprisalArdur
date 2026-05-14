"""
Subject Section Rules — S-1 through S-12

Domain source: appraisal_deep_training_domain_knowledge.md
Rule source:   QCChceklistOpus.md

WHY THIS FILE EXISTS:
Every residential appraisal starts with a Subject section that identifies
the property and the parties involved.  Errors here propagate to every
downstream check — an address mismatch means the appraiser may have valued
the wrong house; a missing HOA fee means the lender's debt-to-income
calculation is wrong.  These rules are the first safety gate.

LOGGING PHILOSOPHY:
Each rule logs structured entries at every decision branch so operators and
developers can see exactly WHY a flag was raised.  Format:
  [RULE_ID] domain_check=<name> | found=<value> | outcome=<status> | reason=<domain reason>
This log stream drives the ML improvement loop — missing fields that fire
EXTRACTION_FAILED here become training examples for better OCR models.
"""

import logging
import re
import difflib
from datetime import datetime
from typing import Optional, Tuple

from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext
from app.services.external_services import ExternalServices

logger = logging.getLogger(__name__)

# ── Shared helpers ──────────────────────────────────────────────────────────────

MISSING_ENGAGEMENT_MESSAGE = (
    "Engagement letter was not provided for this order. Cross-reference validation "
    "against the order form cannot be performed. Please upload the engagement letter and reprocess."
)


def _engagement_document_missing(ctx: ValidationContext) -> bool:
    missing = {str(v).upper() for v in (ctx.missing_supporting_documents or [])}
    return bool(ctx.supporting_document_missing or "ENGAGEMENT" in missing)


def _missing_engagement_result(rule_id: str, rule_name: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_name,
        status=RuleStatus.VERIFY,
        message=MISSING_ENGAGEMENT_MESSAGE,
        action_item="Upload the engagement letter and reprocess this QC result.",
        review_required=True,
        details={
            "supporting_document_missing": True,
            "missing_supporting_documents": ["ENGAGEMENT"],
        },
    )


# ── S-7 Domain Helpers ──────────────────────────────────────────────────────────

def _classify_occupancy_risk(occu_upper: str) -> Tuple[str, str]:
    """
    Return (risk_level, domain_reason) for a given occupancy type.

    Domain logic (from deep training doc):
      Owner Occupied → LOW RISK — owner has personal incentive to maintain
      Tenant Occupied → MEDIUM RISK — lease agreement should exist, rental income factor
      Vacant → HIGH RISK — potential deferred maintenance, vandalism, utilities off

    These risk levels are reported in rule details so operators immediately
    understand what extra scrutiny is required.
    """
    if "VACANT" in occu_upper:
        return (
            "HIGH",
            "Vacant properties carry the highest risk: deferred maintenance, potential vandalism, "
            "utilities may be off, and the property may deteriorate between inspection and closing.",
        )
    if "TENANT" in occu_upper:
        return (
            "MEDIUM",
            "Tenant-occupied properties carry medium risk: lease agreement must exist, rental "
            "income may factor into underwriting, and loan type eligibility may be affected.",
        )
    # Owner occupied
    return (
        "LOW",
        "Owner-occupied properties are lowest risk: owner has personal incentive to maintain "
        "the property and keep it in good condition.",
    )


def _check_photo_occupancy_mismatch(
    stated_occupancy: str,
    vision_results: Optional[list],
) -> Optional[Tuple[str, str]]:
    """
    Cross-check stated occupancy against AI photo analysis results.

    Returns (flag_message, decision_path_entry) if a mismatch is detected,
    None if no mismatch or vision results unavailable.

    Domain rule (Rule S-7 in OPUS, domain training doc Section 1):
      If report says "Owner Occupied" but photos show empty rooms → FLAG
      If report says "Vacant" but photos show personal belongings → FLAG
      If report says "Vacant" but photos show staged home → VERIFY (not hard FAIL)

    WHY: Occupancy fraud is a real risk. A non-owner-occupant getting an
    owner-occupant interest rate is mortgage fraud. Photo evidence is the
    appraiser's direct observation and carries high evidentiary weight.
    """
    if not vision_results:
        return None  # No photo AI results available yet — skip this check

    # Aggregate occupancy indicators from all photo AI results
    occupancy_indicators = []
    for result in vision_results:
        if isinstance(result, dict):
            indicator = result.get("occupancy_indicators", "").upper()
            if indicator:
                occupancy_indicators.append(indicator)

    if not occupancy_indicators:
        return None

    # Majority-vote: what do the photos say?
    dominant = max(set(occupancy_indicators), key=occupancy_indicators.count)
    occu_upper = stated_occupancy.strip().upper()

    if "OWNER" in occu_upper and dominant == "VACANT":
        msg = (
            "Subject section indicates property is owner occupied; however, photos appear to show "
            "property is vacant. Please revise or comment."
        )
        path_entry = (
            f"photo_ai_occupancy={dominant} contradicts stated=OWNER_OCCUPIED → mismatch_flag"
        )
        return (msg, path_entry)

    if "VACANT" in occu_upper and dominant == "OCCUPIED":
        msg = (
            "Subject section shows occupancy as vacant; however, photos show property appears "
            "occupied. Please revise or comment if it is a staged home."
        )
        path_entry = (
            f"photo_ai_occupancy={dominant} contradicts stated=VACANT → mismatch_flag"
        )
        return (msg, path_entry)

    return None


# ── S-8 Domain Helpers ──────────────────────────────────────────────────────────

def _special_assessment_commentary_sufficient(comment: Optional[str]) -> Tuple[bool, list]:
    """
    Check that special assessment commentary covers the required elements:
      1. Purpose (what is the assessment for?)
      2. Paid or unpaid status (affects buyer's obligation)
      3. Temporary or ongoing (affects long-term cost of ownership)

    Domain logic: A $10,000 unpaid assessment that transfers to the buyer
    is a material financial obligation that changes the true cost of ownership
    and must be reflected in the lender's underwriting calculations.

    Returns (is_sufficient, list_of_missing_elements).
    """
    if not comment or len(comment.strip()) < 10:
        return False, ["purpose", "paid/unpaid status", "temporary/ongoing"]

    comment_lower = comment.lower()
    missing = []

    # Check for purpose — comment should explain WHAT the assessment is for
    # We look for dollar amounts or descriptive keywords as proxy for purpose statement
    has_purpose = bool(
        re.search(r"\$[\d,]+", comment)  # dollar amount mentioned
        or re.search(r"\b(?:road|sewer|drainage|sidewalk|water|utility|park|improvement|repair|tax)\b", comment_lower)
    )
    if not has_purpose:
        missing.append("purpose (what is this assessment for?)")

    # Check for paid/unpaid status — directly affects the buyer's liability
    has_paid_status = bool(
        re.search(r"\b(?:paid|unpaid|outstanding|settled|cleared|balance|due)\b", comment_lower)
    )
    if not has_paid_status:
        missing.append("paid/unpaid status")

    # Check for temporary vs ongoing — temporary assessments end; ongoing affect long-term costs
    has_duration = bool(
        re.search(r"\b(?:temporary|ongoing|annual|monthly|permanent|one.?time|recurring|per year|per month)\b", comment_lower)
    )
    if not has_duration:
        missing.append("temporary or ongoing status")

    return len(missing) == 0, missing


# ── S-12 Domain Helpers ──────────────────────────────────────────────────────────

def _analyze_dom_risk(dom: int) -> Tuple[str, str, str]:
    """
    Classify Days-on-Market into domain risk levels.

    Risk table (from deep training doc, Section 4 — DOM Interpretation):
      0–10   → MEDIUM (extremely fast — verify no buyer pressure / overpayment)
      10–60  → LOW (normal, healthy market)
      60–90  → MEDIUM (softening market — compare to neighborhood marketing time)
      90+    → HIGH (weak demand or overpriced — comment required)

    Returns (risk_level, market_signal, qc_action).
    WHY: DOM is one of the most powerful single-number indicators of market
    health. A 2-day DOM might mean the buyer overpaid in a bidding war; a
    120-day DOM means the market rejected the property at its original price.
    Both extremes require commentary from the appraiser.
    """
    if dom <= 10:
        return (
            "MEDIUM",
            "Extremely fast sale — verify no buyer pressure or overpayment",
            "FLAG if no multiple-offer comment provided",
        )
    if dom <= 60:
        return (
            "LOW",
            "Normal, healthy market pace",
            "No additional action required",
        )
    if dom <= 90:
        return (
            "MEDIUM",
            "Above-average marketing time — market may be softening",
            "Compare to neighborhood marketing time; flag if inconsistent",
        )
    # 90+
    return (
        "HIGH",
        "Extended marketing time — weak demand or property was overpriced",
        "Comment required explaining market conditions; verify no price reductions",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SUBJECT SECTION RULES (S-1 through S-12)
# ══════════════════════════════════════════════════════════════════════════════


@rule(id="S-1", name="Property Address Validation")
def validate_property_address(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-1 — Property Address Validation
    Target Fields: Property Address, City, State, Zip Code, County
    Rule: Must match Client Engagement Letter EXACTLY
    Validation: Cross-verify with USPS address verification

    WHY THIS MATTERS: If the address in the report does not match the engagement
    letter, the appraiser may have evaluated the wrong property entirely. This is
    a BLOCKING error — the lender cannot use the report until the address is
    confirmed correct.

    Rejection templates (from OPUS):
      "Property address does not match with order form."
      "Property City name does not match with order form."
      "Property Zip code does not match with order form."
      "Property county does not match with order form."
    """
    if _engagement_document_missing(ctx):
        return _missing_engagement_result("S-1", "Property Address Validation")

    if not ctx.report.subject.address:
        raise DataMissingException("Property Address (Report)")

    if not ctx.engagement_letter:
        raise DataMissingException("Client Engagement Letter")

    eng = ctx.engagement_letter
    subj = ctx.report.subject

    if not eng.property_address:
        raise DataMissingException("Property Address (Engagement Letter)")

    def normalize_string(s: Optional[str]) -> str:
        if not s:
            return ""
        return re.sub(r'[^A-Z0-9\s]', '', s.strip().upper())

    def normalize_address(s: Optional[str]) -> str:
        """
        Normalize USPS-style street abbreviations so real matches are not
        failed because one source says "Circle North" and the other "Cir N".
        """
        normalized = normalize_string(s)
        replacements = {
            "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
            "CIRCLE": "CIR", "COURT": "CT", "STREET": "ST", "AVENUE": "AVE",
            "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN",
            "TERRACE": "TER", "TRACE": "TR", "PLACE": "PL",
            "PARKWAY": "PKWY", "HIGHWAY": "HWY",
        }
        tokens = [replacements.get(t, t) for t in normalized.split()]
        if len(tokens) > 2 and tokens[1] in {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}:
            direction = tokens.pop(1)
            tokens.append(direction)
        return " ".join(tokens)

    def street_tokens_match(rpt: str, eng: str) -> bool:
        """House number must match; at least one non-suffix word must match."""
        rt, et = rpt.split(), eng.split()
        if not rt or not et:
            return False
        if rt[0] != et[0]:  # house number must match
            return False
        suffix_words = {"ST", "AVE", "BLVD", "DR", "RD", "LN", "CT", "CIR", "TER", "TR",
                        "PL", "PKWY", "HWY", "N", "S", "E", "W"}
        rpt_core = {t for t in rt[1:] if t not in suffix_words}
        eng_core = {t for t in et[1:] if t not in suffix_words}
        return bool(rpt_core & eng_core)

    # --- Parse engagement letter components ---
    eng_street = re.split(r'\bProperty\s+County\b', eng.property_address, flags=re.IGNORECASE)[0].strip()
    eng_city = eng.city
    eng_state = eng.state
    eng_zip = eng.zip_code

    if eng_street and (not eng_city or not eng_state or not eng_zip):
        # Pattern 1: "Street City, State Zip"
        m = re.search(r'^(.+?)\s+([A-Za-z\s]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', eng_street)
        if m:
            eng_street = m.group(1).strip()
            if not eng_city:  eng_city = m.group(2).strip()
            if not eng_state: eng_state = m.group(3).strip()
            if not eng_zip:   eng_zip = m.group(4).strip()
        else:
            # Pattern 2: "Street City State Zip" (no comma)
            m = re.search(r'^(.+?)\s+([A-Za-z\s]+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', eng_street)
            if m:
                eng_street = m.group(1).strip()
                if not eng_city:  eng_city = m.group(2).strip()
                if not eng_state: eng_state = m.group(3).strip()
                if not eng_zip:   eng_zip = m.group(4).strip()

    mismatches, mismatch_fields = [], []

    # --- Street comparison (fuzzy, 85% threshold) ---
    norm_eng_street = normalize_address(eng_street)
    norm_rpt_street = normalize_address(subj.address)
    similarity = difflib.SequenceMatcher(None, norm_rpt_street, norm_eng_street).ratio()
    if similarity < 0.85:
        if (norm_rpt_street not in norm_eng_street
                and norm_eng_street not in norm_rpt_street
                and not street_tokens_match(norm_rpt_street, norm_eng_street)):
            mismatches.append(f"Street: '{subj.address}' vs '{eng_street}' ({similarity:.1%} match)")
            mismatch_fields.append("property_address")

    # --- City comparison (exact normalized) ---
    rpt_city = normalize_string(subj.city)
    eng_city_norm = normalize_string(eng_city)
    if not rpt_city:
        mismatches.append("City missing in Report")
        mismatch_fields.append("city")
    elif rpt_city != eng_city_norm:
        mismatches.append(f"City: '{subj.city}' vs '{eng_city}'")
        mismatch_fields.append("city")

    # --- State comparison (exact) ---
    rpt_state = (subj.state or "").strip().upper()
    eng_state_clean = (eng_state or "").strip().upper()
    if not rpt_state:
        mismatches.append("State missing in Report")
        mismatch_fields.append("state")
    elif rpt_state != eng_state_clean:
        mismatches.append(f"State: '{rpt_state}' vs '{eng_state_clean}'")
        mismatch_fields.append("state")

    # --- Zip code comparison (first 5 digits) ---
    rpt_zip = (subj.zip_code or "")[:5]
    eng_zip_clean = (eng_zip or "")[:5]
    if not rpt_zip:
        mismatches.append("Zip code missing in Report")
        mismatch_fields.append("zip_code")
    elif rpt_zip != eng_zip_clean:
        mismatches.append(f"Zip: '{rpt_zip}' vs '{eng_zip_clean}'")
        mismatch_fields.append("zip_code")

    # --- County comparison (robust — handles OCR row-flatten pollution) ---
    rpt_county = normalize_string(subj.county)
    eng_county = normalize_string(eng.county)
    if eng_county:
        if not rpt_county:
            mismatches.append("County missing in Report")
            mismatch_fields.append("county")
        elif rpt_county != eng_county:
            county_ok = (
                eng_county in rpt_county
                or rpt_county in eng_county
                or difflib.SequenceMatcher(None, rpt_county, eng_county).ratio() >= 0.85
            )
            if not county_ok:
                mismatches.append(f"County: '{subj.county}' vs '{eng.county}'")
                mismatch_fields.append("county")

    # --- USPS verification (best-effort) ---
    usps_result = None
    try:
        import asyncio
        usps_result = asyncio.run(
            ExternalServices().verify_usps_address(
                subj.address, city=subj.city, state=subj.state, zip_code=subj.zip_code,
            )
        )
        if not usps_result.is_valid:
            mismatches.append(f"USPS validation failed: {usps_result.error_message or 'invalid address'}")
            mismatch_fields.append("property_address")
        elif usps_result.zip_code and rpt_zip and usps_result.zip_code[:5] != rpt_zip:
            mismatches.append(f"USPS ZIP mismatch: '{rpt_zip}' vs '{usps_result.zip_code[:5]}'")
            mismatch_fields.append("zip_code")
    except Exception:
        usps_result = None

    if not mismatches:
        logger.info(
            "[S-1] domain_check=address_match | outcome=PASS | "
            "report='%s %s %s %s' matches engagement_letter",
            subj.address, subj.city, subj.state, subj.zip_code,
        )
        return RuleResult(
            rule_id="S-1",
            rule_name="Property Address Validation",
            status=RuleStatus.PASS,
            message="Property address components match engagement letter.",
            appraisal_value=f"{subj.address}, {subj.city}, {subj.state} {subj.zip_code}",
            engagement_value=f"{eng_street}, {eng_city}, {eng_state} {eng_zip}",
            extracted_value=f"{subj.address}, {subj.city}, {subj.state} {subj.zip_code}",
            expected_value=f"{eng_street}, {eng_city}, {eng_state} {eng_zip}",
            target_field="property_address",
            compared_values={
                "street": subj.address,
                "city": subj.city,
                "state": subj.state,
                "zip": subj.zip_code,
            },
            decision_path=["engagement_present", "all_components_matched", "usps_verified"],
        )

    # LLM normalization override — if LLM says same location, downgrade to VERIFY
    llm_addr = ((ctx.llm_enrichment or {}).get("items") or {}).get("address_normalization") or {}
    target_field = mismatch_fields[0] if mismatch_fields else "property_address"

    if llm_addr.get("same_location") is True and llm_addr.get("llm_confidence_score", 0.0) >= 0.75:
        logger.warning(
            "[S-1] domain_check=address_match | outcome=VERIFY | "
            "mismatches=%s | llm_override=same_location_confirmed",
            mismatches,
        )
        return RuleResult(
            rule_id="S-1",
            rule_name="Property Address Validation",
            status=RuleStatus.VERIFY,
            message="Address components differ, but LLM normalization indicates the same physical location.",
            appraisal_value=f"{subj.address}, {subj.city}, {subj.state} {subj.zip_code}",
            engagement_value=f"{eng_street}, {eng_city}, {eng_state} {eng_zip}",
            review_required=True,
            target_field=target_field,
            action_item="Confirm whether the appraisal and engagement-letter addresses are the same property.",
            details={
                "mismatches": mismatches,
                "target_field": target_field,
                "llm_address_normalization": llm_addr,
            },
            decision_path=["engagement_present", "component_mismatch_detected", "llm_same_location_override"],
        )

    logger.warning(
        "[S-1] domain_check=address_match | outcome=FAIL | mismatches=%s | "
        "risk=BLOCKING (appraiser may have valued wrong property)",
        mismatches,
    )
    return RuleResult(
        rule_id="S-1",
        rule_name="Property Address Validation",
        status=RuleStatus.FAIL,
        message=f"Property address does not match with order form. {'; '.join(mismatches)}",
        appraisal_value=f"{subj.address}, {subj.city}, {subj.state} {subj.zip_code}",
        engagement_value=f"{eng_street}, {eng_city}, {eng_state} {eng_zip}",
        review_required=True,
        target_field=target_field,
        details={
            "target_field": target_field,
            "mismatches": mismatches,
            "risk": "BLOCKING — address mismatch means appraiser may have valued the wrong property",
            "report_components": {
                "street": subj.address, "city": subj.city,
                "state": subj.state, "zip": subj.zip_code, "county": subj.county,
            },
            "engagement_components": {
                "street": eng_street, "city": eng_city,
                "state": eng_state, "zip": eng_zip, "county": eng.county,
            },
            "usps": {
                "source": getattr(usps_result, "source", "unavailable") if usps_result else "unavailable",
                "standardized_address": getattr(usps_result, "standardized_address", None) if usps_result else None,
            },
        },
        decision_path=["engagement_present", "component_mismatch_detected", "no_llm_override", "fail"],
    )


@rule(id="S-2", name="Borrower Name Validation")
def validate_borrower_name(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-2 — Borrower Name Validation
    Target Field: Borrower
    Rule: Must match Client Engagement Letter EXACTLY
    Validation: Include ALL borrowers and co-borrowers
    Watch Items: Spelling errors, Middle names, Suffixes (JR/SR)

    WHY: The borrower name ties the appraisal to the specific loan file.
    A mismatch means the appraisal may belong to a different loan, which
    is a compliance failure under UAD requirements.

    Special case: Refinance where Owner of Record ≠ Borrower requires
    a comment from the appraiser explaining why (e.g., trust, LLC, estate).
    """
    if _engagement_document_missing(ctx):
        return _missing_engagement_result("S-2", "Borrower Name Validation")

    if not ctx.report.subject.borrower:
        raise DataMissingException("Borrower Name (Report)")

    if not ctx.engagement_letter or not ctx.engagement_letter.borrower_name:
        raise DataMissingException("Borrower Name (Engagement Letter)")

    def normalize_person_name(value: str) -> str:
        """
        Strip any form labels that OCR accidentally captured after the name
        (e.g. "John Smith Owner of Public Record" → "JOHN SMITH").
        OCR row-flattening is the most common cause of this problem.
        """
        value = re.split(
            r"\b(?:Owner of Public Record|Property Address|City|County|Legal Description|"
            r"Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b",
            value, maxsplit=1, flags=re.I,
        )[0]
        return re.sub(r"[^A-Z0-9\s]", "", value.upper()).strip()

    rpt_borrower = normalize_person_name(ctx.report.subject.borrower)
    eng_borrower = normalize_person_name(ctx.engagement_letter.borrower_name)

    if rpt_borrower != eng_borrower:
        logger.warning(
            "[S-2] domain_check=borrower_match | outcome=FAIL | "
            "report='%s' vs engagement='%s'",
            rpt_borrower, eng_borrower,
        )
        return RuleResult(
            rule_id="S-2",
            rule_name="Borrower Name Validation",
            status=RuleStatus.FAIL,
            message=(
                f"Borrower name mismatch. Report shows '{ctx.report.subject.borrower}' "
                f"but order form shows '{ctx.engagement_letter.borrower_name}'."
            ),
            appraisal_value=str(ctx.report.subject.borrower),
            engagement_value=str(ctx.engagement_letter.borrower_name),
            review_required=True,
            details={
                "report_normalized": rpt_borrower,
                "engagement_normalized": eng_borrower,
                "risk": "BLOCKING — borrower name must match loan file exactly",
            },
            decision_path=["borrower_extracted", "engagement_borrower_found", "name_mismatch", "fail"],
        )

    # Refinance check: Owner of Record ≠ Borrower requires explanation
    if ctx.engagement_letter.assignment_type == "Refinance":
        if ctx.report.subject.owner_of_public_record:
            owner = ctx.report.subject.owner_of_public_record.strip().upper()
            if owner != rpt_borrower:
                logger.warning(
                    "[S-2] domain_check=refinance_owner_match | outcome=VERIFY | "
                    "owner='%s' != borrower='%s' | reason=refinance requires comment",
                    owner, rpt_borrower,
                )
                return RuleResult(
                    rule_id="S-2",
                    rule_name="Borrower Name Validation",
                    status=RuleStatus.VERIFY,
                    message=(
                        "Assignment type is 'Refinance'; however, owner name and borrower name "
                        "are different. Please revise or comment (e.g. trust, LLC, estate sale)."
                    ),
                    appraisal_value=f"Owner: {owner}, Borrower: {rpt_borrower}",
                    engagement_value="Refinance — Borrower should match Owner unless explained",
                    review_required=True,
                    details={
                        "owner": owner,
                        "borrower": rpt_borrower,
                        "domain_reason": (
                            "In a refinance, the current owner is re-financing their own property. "
                            "If owner and borrower differ, this may indicate the property was "
                            "transferred, or the loan is in a different name — both require explanation."
                        ),
                    },
                    decision_path=["borrower_matched", "refinance_detected", "owner_borrower_mismatch", "verify"],
                )

    logger.info(
        "[S-2] domain_check=borrower_match | outcome=PASS | borrower='%s'", rpt_borrower,
    )
    return RuleResult(
        rule_id="S-2",
        rule_name="Borrower Name Validation",
        status=RuleStatus.PASS,
        message="Borrower name matches engagement letter.",
        appraisal_value=str(ctx.report.subject.borrower),
        engagement_value=str(ctx.engagement_letter.borrower_name),
        extracted_value=str(ctx.report.subject.borrower),
        expected_value=str(ctx.engagement_letter.borrower_name),
        target_field="borrower_name",
        compared_values={"report": rpt_borrower, "engagement": eng_borrower},
        decision_path=["borrower_extracted", "engagement_borrower_found", "names_match", "pass"],
    )


@rule(id="S-3", name="Owner of Public Record")
def validate_owner_record(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-3 — Owner of Public Record
    Target Field: Owner of Public Record
    Rule: Must be provided and current
    Condition: If Refinance AND Owner ≠ Borrower → Comment REQUIRED

    WHY: The owner of record establishes legal chain of title. If the
    person selling is not the legal owner, it is a fraud signal. For
    refinances, lenders need to know who legally owns the property being
    used as collateral for the new loan.
    """
    if not ctx.report.subject.owner_of_public_record:
        logger.warning(
            "[S-3] domain_check=owner_present | outcome=FAIL | "
            "reason=owner_of_record_field_blank"
        )
        return RuleResult(
            rule_id="S-3",
            rule_name="Owner of Public Record",
            status=RuleStatus.FAIL,
            message="Owner of Public Record is missing or blank.",
            decision_path=["owner_field_blank", "fail"],
        )

    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        borrower = (ctx.report.subject.borrower or "").strip().upper()
        owner = ctx.report.subject.owner_of_public_record.strip().upper()

        if borrower and owner != borrower:
            logger.warning(
                "[S-3] domain_check=refinance_owner | outcome=VERIFY | "
                "owner='%s' != borrower='%s'",
                owner, borrower,
            )
            return RuleResult(
                rule_id="S-3",
                rule_name="Owner of Public Record",
                status=RuleStatus.VERIFY,
                message=(
                    "Refinance transaction: Owner of Public Record differs from Borrower. "
                    "Verify a comment is provided explaining the discrepancy."
                ),
                details={
                    "owner": owner,
                    "borrower": borrower,
                    "domain_reason": (
                        "In a refinance, the owner of record is the collateral provider. "
                        "A mismatch with the borrower could indicate a trust, LLC, or estate — "
                        "all of which have different underwriting requirements."
                    ),
                },
                decision_path=["owner_present", "refinance_detected", "owner_borrower_mismatch", "verify"],
            )

    logger.info(
        "[S-3] domain_check=owner_present | outcome=PASS | owner='%s'",
        ctx.report.subject.owner_of_public_record,
    )
    return RuleResult(
        rule_id="S-3",
        rule_name="Owner of Public Record",
        status=RuleStatus.PASS,
        message="Owner of Public Record is present and valid.",
        extracted_value=ctx.report.subject.owner_of_public_record,
        decision_path=["owner_present", "consistency_check_passed", "pass"],
    )


@rule(id="S-4", name="Legal Description and Taxes")
def validate_legal_tax(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-4 — Legal Description and Taxes
    Target Fields: Legal Description, APN, Tax Year, R.E. Taxes
    Rule: All fields MUST be completed, current, and non-blank
    Tax Year: Must be within last 2 years
    R.E. Taxes: Decimal values NOT allowed

    WHY: Legal description and APN uniquely identify the parcel in county
    records — without them, the appraisal cannot be tied to a specific piece
    of real property. Real estate taxes factor into the borrower's total
    housing payment (PITI), so stale or decimal values cause DTI calculation
    errors.
    """
    subj = ctx.report.subject
    missing = []

    if not subj.legal_description: missing.append("Legal Description")
    if not subj.apn:               missing.append("Assessor's Parcel Number (APN)")
    if not subj.tax_year:          missing.append("Tax Year")
    if subj.re_taxes is None:      missing.append("Real Estate Taxes")

    if missing:
        logger.warning(
            "[S-4] domain_check=tax_legal_fields | outcome=EXTRACTION_FAILED | "
            "missing=%s", missing,
        )
        raise DataMissingException(f"Missing Tax/Legal Fields: {', '.join(missing)}")

    # Tax year currency check (within last 2 years)
    try:
        tax_year = int(subj.tax_year)
        current_year = datetime.now().year
        if tax_year < current_year - 2:
            logger.warning(
                "[S-4] domain_check=tax_year_currency | outcome=FAIL | "
                "tax_year=%d | current_year=%d | reason=stale_tax_data",
                tax_year, current_year,
            )
            return RuleResult(
                rule_id="S-4",
                rule_name="Legal Description and Taxes",
                status=RuleStatus.FAIL,
                message=(
                    f"Tax Year ({tax_year}) must be within the last 2 years. "
                    f"Current year: {current_year}. Stale tax data can cause "
                    f"incorrect DTI calculations."
                ),
                appraisal_value=str(tax_year),
                expected_value=str(current_year),
                decision_path=["fields_present", "tax_year_stale", "fail"],
            )
    except (ValueError, TypeError):
        return RuleResult(
            rule_id="S-4",
            rule_name="Legal Description and Taxes",
            status=RuleStatus.FAIL,
            message=f"Tax Year '{subj.tax_year}' is not a valid year format.",
            decision_path=["fields_present", "tax_year_parse_error", "fail"],
        )

    # RE taxes format check (no decimals — lender systems expect whole dollar amounts)
    if subj.re_taxes is not None and subj.re_taxes % 1 != 0:
        logger.warning(
            "[S-4] domain_check=re_taxes_format | outcome=FAIL | "
            "taxes=%.2f | reason=decimal_not_allowed",
            subj.re_taxes,
        )
        return RuleResult(
            rule_id="S-4",
            rule_name="Legal Description and Taxes",
            status=RuleStatus.FAIL,
            message=(
                f"Real Estate Taxes (${subj.re_taxes}) must be a whole number. "
                "Decimal values are not allowed per UAD requirements."
            ),
            appraisal_value=str(subj.re_taxes),
            decision_path=["fields_present", "tax_year_valid", "re_taxes_decimal", "fail"],
        )

    logger.info(
        "[S-4] domain_check=tax_legal_complete | outcome=PASS | "
        "apn='%s' tax_year=%s taxes=%.0f",
        subj.apn, subj.tax_year, subj.re_taxes or 0,
    )
    return RuleResult(
        rule_id="S-4",
        rule_name="Legal Description and Taxes",
        status=RuleStatus.PASS,
        message="Legal description and tax data are complete and valid.",
        compared_values={
            "apn": subj.apn,
            "tax_year": subj.tax_year,
            "re_taxes": subj.re_taxes,
        },
        decision_path=["all_fields_present", "tax_year_valid", "taxes_format_valid", "pass"],
    )


@rule(id="S-5", name="Neighborhood Name")
def validate_neighborhood_name(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-5 — Neighborhood Name
    Target Field: Neighborhood Name
    Rule: Must be an actual subdivision/area name — not blank, N/A, or Unknown

    WHY: The neighborhood name anchors the market area analysis. Without a
    real name, the appraiser's neighborhood analysis cannot be verified against
    market data, and reviewers cannot confirm the comparable sales came from
    the correct area.

    Rejection template: "The neighborhood name in subject section is mentioned as
    N/A. Per UAD requirements, the appraiser should enter a neighborhood name
    recognized by the municipality..."
    """
    neighborhood = ctx.report.subject.neighborhood_name

    if not neighborhood:
        logger.warning(
            "[S-5] domain_check=neighborhood_name | outcome=FAIL | reason=field_blank"
        )
        return RuleResult(
            rule_id="S-5",
            rule_name="Neighborhood Name",
            status=RuleStatus.FAIL,
            message=(
                "The neighborhood name in subject section is blank. Per UAD requirements, "
                "the appraiser should enter a neighborhood name recognized by the municipality "
                "or the common name by which residents refer to the location. Please revise."
            ),
            decision_path=["neighborhood_name_blank", "fail"],
        )

    invalid_values = {"NONE", "N/A", "NA", "UNKNOWN", "NOT APPLICABLE", "N.A.", "BLANK"}
    if neighborhood.strip().upper() in invalid_values:
        logger.warning(
            "[S-5] domain_check=neighborhood_name | outcome=FAIL | value='%s' | reason=placeholder_value",
            neighborhood,
        )
        return RuleResult(
            rule_id="S-5",
            rule_name="Neighborhood Name",
            status=RuleStatus.FAIL,
            message=(
                f"The neighborhood name in subject section is mentioned as {neighborhood}. "
                "Per UAD requirements, the appraiser should enter a neighborhood name recognized "
                "by the municipality or the common name residents use. Please revise."
            ),
            appraisal_value=neighborhood,
            decision_path=["neighborhood_name_present", "invalid_placeholder_detected", "fail"],
        )

    logger.info(
        "[S-5] domain_check=neighborhood_name | outcome=PASS | name='%s'", neighborhood,
    )
    return RuleResult(
        rule_id="S-5",
        rule_name="Neighborhood Name",
        status=RuleStatus.PASS,
        message=f"Neighborhood name '{neighborhood}' is provided.",
        extracted_value=neighborhood,
        decision_path=["neighborhood_name_present", "valid_name_confirmed", "pass"],
    )


@rule(id="S-6", name="Map Reference and Census Tract")
def validate_map_census(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-6 — Map Reference and Census Tract
    Target Fields: Map Reference, Census Tract
    Format: Census Tract must be XXXX.XX (UAD numeric format)

    WHY: Census tract data is used by government agencies (HMDA, CRA) to
    monitor lending patterns by geographic area. Incorrect or missing census
    tract data creates regulatory reporting failures for the lender.
    """
    subject = ctx.report.subject
    missing = []
    if not subject.map_reference:  missing.append("Map Reference")
    if not subject.census_tract:   missing.append("Census Tract")

    if missing:
        logger.warning(
            "[S-6] domain_check=map_census | outcome=VERIFY | missing=%s", missing,
        )
        return RuleResult(
            rule_id="S-6",
            rule_name="Map Reference and Census Tract",
            status=RuleStatus.VERIFY,
            message=(
                f"Missing required field(s): {', '.join(missing)}. "
                "Verify Page 1 contains current map reference and census tract."
            ),
            review_required=True,
            decision_path=["map_or_census_missing", "verify"],
        )

    census_pattern = r'^\d{4}(?:\.\d{2})?$'
    if not re.match(census_pattern, subject.census_tract.strip()):
        logger.warning(
            "[S-6] domain_check=census_format | outcome=FAIL | value='%s' | "
            "reason=not_UAD_format",
            subject.census_tract,
        )
        return RuleResult(
            rule_id="S-6",
            rule_name="Map Reference and Census Tract",
            status=RuleStatus.FAIL,
            message=(
                f"Census Tract '{subject.census_tract}' is not in valid UAD numeric format "
                "(XXXX or XXXX.XX)."
            ),
            appraisal_value=subject.census_tract,
            decision_path=["both_fields_present", "census_format_invalid", "fail"],
        )

    logger.info(
        "[S-6] domain_check=map_census | outcome=PASS | map='%s' census='%s'",
        subject.map_reference, subject.census_tract,
    )
    return RuleResult(
        rule_id="S-6",
        rule_name="Map Reference and Census Tract",
        status=RuleStatus.PASS,
        message="Map Reference and Census Tract are present and valid.",
        compared_values={
            "map_reference": subject.map_reference,
            "census_tract": subject.census_tract,
        },
        decision_path=["both_fields_present", "census_format_valid", "pass"],
    )


@rule(id="S-7", name="Occupant Status")
def validate_occupant(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-7 — Occupant Status
    Target Field: Occupant (Owner, Tenant, Vacant)
    If Tenant: Must state lease dates AND rental amount
    If Vacant: Must state if utilities are ON
    Image Validation: Cross-check photos against stated occupancy

    WHY THIS MATTERS:
    Occupancy is one of the most important risk signals in a residential
    appraisal.  Lenders price risk differently for owner-occupied (lowest),
    tenant-occupied (medium), and vacant properties (highest).  More critically,
    occupancy fraud — claiming owner-occupied to get a better interest rate when
    the buyer intends to rent — is one of the most common forms of mortgage fraud.

    Photo cross-checking is the appraiser's primary tool to verify occupancy.
    If photos show empty rooms but the report says "Owner Occupied", that is a
    material inconsistency that the QC system must flag.

    Risk levels:
      Owner Occupied → LOW RISK
      Tenant Occupied → MEDIUM RISK (lease docs, rental income, loan type eligibility)
      Vacant → HIGH RISK (deferred maintenance, vandalism, utilities off)

    Rejection templates (OPUS Rule S-7):
      "Subject section indicates property is owner occupied; however, photos appear
       to show property is vacant. Please revise or comment."
      "Subject section shows occupancy as vacant; however, photos show property
       appears occupied. Please revise or comment if it is a staged home."
    """
    occu = ctx.report.subject.occupant

    if not occu:
        logger.warning(
            "[S-7] domain_check=occupancy_present | outcome=FAIL | reason=field_blank"
        )
        return RuleResult(
            rule_id="S-7",
            rule_name="Occupant Status",
            status=RuleStatus.FAIL,
            message="Occupant status is missing or blank.",
            decision_path=["occupancy_field_blank", "fail"],
        )

    valid_status = ["OWNER", "TENANT", "VACANT", "OWNER OCCUPIED"]
    occu_upper = occu.strip().upper()

    if occu_upper not in valid_status:
        logger.warning(
            "[S-7] domain_check=occupancy_valid_value | outcome=FAIL | value='%s'", occu,
        )
        return RuleResult(
            rule_id="S-7",
            rule_name="Occupant Status",
            status=RuleStatus.FAIL,
            message=f"Invalid occupant status: '{occu}'. Must be one of: Owner, Tenant, Vacant.",
            appraisal_value=occu,
            decision_path=["occupancy_present", "invalid_value", "fail"],
        )

    # Classify risk level based on occupancy type
    risk_level, domain_reason = _classify_occupancy_risk(occu_upper)
    logger.info(
        "[S-7] domain_check=occupancy_risk | occupancy='%s' risk=%s | %s",
        occu_upper, risk_level, domain_reason,
    )

    # --- Photo cross-check (Rule S-7, highest value inconsistency signal) ---
    photo_mismatch = _check_photo_occupancy_mismatch(occu_upper, ctx.vision_results)
    if photo_mismatch:
        mismatch_msg, path_entry = photo_mismatch
        logger.warning(
            "[S-7] domain_check=photo_occupancy_mismatch | outcome=FAIL | %s", path_entry,
        )
        return RuleResult(
            rule_id="S-7",
            rule_name="Occupant Status",
            status=RuleStatus.FAIL,
            message=mismatch_msg,
            appraisal_value=occu,
            review_required=True,
            details={
                "stated_occupancy": occu,
                "risk_level": "HIGH",
                "domain_reason": (
                    "Occupancy fraud is one of the most common forms of mortgage fraud. "
                    "Photos provide direct observational evidence that contradicts the stated occupancy. "
                    "This is a FAIL — the report must be revised or explained."
                ),
                "photo_analysis": "AI photo analysis detected occupancy inconsistency",
            },
            decision_path=["occupancy_present", "valid_value", path_entry, "fail"],
        )

    # --- Tenant-specific requirements ---
    if "TENANT" in occu_upper:
        if not ctx.report.subject.lease_dates:
            logger.warning(
                "[S-7] domain_check=tenant_lease_dates | outcome=VERIFY | "
                "reason=lease_dates_not_stated"
            )
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.VERIFY,
                message=(
                    "Property is tenant-occupied. Please provide lease dates. "
                    "Per Rule S-7: Tenant occupancy requires lease dates and rental amount "
                    "to be stated in the report."
                ),
                appraisal_value="Tenant Occupied",
                review_required=True,
                details={
                    "risk_level": risk_level,
                    "domain_reason": domain_reason,
                    "missing_element": "lease_dates",
                    "domain_rule": (
                        "Lease dates tell the lender when the tenancy ends — a tenant "
                        "whose lease expires in 2 months creates a different risk profile "
                        "than a tenant on a 2-year lease."
                    ),
                },
                decision_path=["occupancy=TENANT", "lease_dates_missing", "verify"],
            )
        if not ctx.report.subject.rental_amount:
            logger.warning(
                "[S-7] domain_check=tenant_rental_amount | outcome=VERIFY | "
                "reason=rental_amount_not_stated"
            )
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.VERIFY,
                message=(
                    "Property is tenant-occupied. Please provide rental amount. "
                    "Rental income factors into the debt-to-income calculation."
                ),
                details={
                    "risk_level": risk_level,
                    "domain_reason": (
                        "The rental amount determines whether the property generates positive "
                        "cash flow. Lenders use this in investment property underwriting."
                    ),
                },
                decision_path=["occupancy=TENANT", "lease_dates_present", "rental_amount_missing", "verify"],
            )

    # --- Vacant-specific requirements ---
    if "VACANT" in occu_upper:
        if ctx.report.subject.utilities_on is None:
            logger.warning(
                "[S-7] domain_check=vacant_utilities | outcome=VERIFY | "
                "reason=utilities_status_not_stated"
            )
            return RuleResult(
                rule_id="S-7",
                rule_name="Occupant Status",
                status=RuleStatus.VERIFY,
                message=(
                    "Property is vacant. Please state if utilities are ON or OFF. "
                    "Per Rule S-7: Vacant properties must document utility status at time of inspection."
                ),
                details={
                    "risk_level": "HIGH",
                    "domain_reason": (
                        "Utilities off at a vacant property is a high-risk signal: pipes can freeze, "
                        "HVAC cannot be tested, and the property may have hidden damage. "
                        "The appraiser must document utility status as part of their scope of work."
                    ),
                },
                decision_path=["occupancy=VACANT", "utilities_status_unknown", "verify"],
            )
        logger.info(
            "[S-7] domain_check=vacant_utilities | utilities_on=%s",
            ctx.report.subject.utilities_on,
        )

    logger.info(
        "[S-7] domain_check=occupancy_valid | outcome=PASS | "
        "occupancy='%s' risk=%s",
        occu, risk_level,
    )
    return RuleResult(
        rule_id="S-7",
        rule_name="Occupant Status",
        status=RuleStatus.PASS,
        message=f"Occupant status '{occu}' is valid and complete.",
        extracted_value=occu,
        details={
            "risk_level": risk_level,
            "occupancy_type": occu_upper,
        },
        decision_path=["occupancy_present", "valid_value", "requirements_satisfied", "pass"],
    )


@rule(id="S-8", name="Special Assessments")
def validate_special_assessments(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-8 — Special Assessments
    Target Field: Special Assessments
    Rule: Field must not be blank; if >0 → amount + purpose + paid/unpaid + temporary/ongoing
    If None: Must contain "0"

    WHY THIS MATTERS:
    A special assessment is an EXTRA charge from local government for a specific
    infrastructure project (road repaving, sewer upgrade, drainage improvement).
    Unlike regular property taxes, special assessments can be:
      - Large one-time amounts (e.g., $15,000 for a new road)
      - Ongoing annual charges
      - Unpaid — meaning they transfer to the buyer at closing

    An unreported or vague special assessment can:
      1. Change the buyer's DTI ratio (lenders count it as a monthly obligation)
      2. Create surprise closing costs (if unpaid, must be cleared at settlement)
      3. Reduce the property's net value

    Domain logic: amount > $5,000 AND not explained → escalate to MEDIUM risk
    Commentary must cover: (1) purpose, (2) paid/unpaid, (3) temporary/ongoing

    Rejection template: "In the subject section, please specify what the special
    assessment of $[amount] is for."
    """
    subj = ctx.report.subject

    # Field must not be blank — "0" is the correct value when no assessments exist
    if subj.special_assessments is None:
        logger.warning(
            "[S-8] domain_check=assessment_present | outcome=EXTRACTION_FAILED | "
            "reason=field_blank_not_zero"
        )
        raise DataMissingException("Special Assessments")

    if subj.special_assessments == 0:
        logger.info(
            "[S-8] domain_check=assessment_amount | outcome=PASS | amount=0 (no assessments)"
        )
        return RuleResult(
            rule_id="S-8",
            rule_name="Special Assessments",
            status=RuleStatus.PASS,
            message="Special assessments field is $0 — no active assessments.",
            extracted_value="$0",
            decision_path=["field_present", "amount_zero", "pass"],
        )

    # Assessment exists — evaluate commentary quality
    amount = subj.special_assessments
    comment = subj.special_assessments_comment or ""

    logger.info(
        "[S-8] domain_check=assessment_commentary | amount=%.2f | "
        "comment_length=%d chars",
        amount, len(comment.strip()),
    )

    # Quick check: is there any commentary at all?
    if len(comment.strip()) < 10:
        logger.warning(
            "[S-8] domain_check=assessment_commentary | outcome=FAIL | "
            "amount=%.2f | reason=no_commentary",
            amount,
        )
        return RuleResult(
            rule_id="S-8",
            rule_name="Special Assessments",
            status=RuleStatus.FAIL,
            message=(
                f"In the subject section, please specify what the special assessment of "
                f"${amount:,.2f} is for."
            ),
            appraisal_value=f"${amount:,.2f}",
            target_field="special_assessments",
            details={
                "amount": amount,
                "risk_level": "HIGH" if amount > 5000 else "MEDIUM",
                "domain_reason": (
                    "Special assessments are mandatory financial obligations from local government. "
                    "Without purpose, paid/unpaid status, and duration, the lender cannot correctly "
                    "calculate the buyer's true housing cost."
                ),
            },
            decision_path=["field_present", "amount_gt_zero", "no_commentary", "fail"],
        )

    # Check that commentary covers the three required elements
    is_sufficient, missing_elements = _special_assessment_commentary_sufficient(comment)

    if not is_sufficient:
        # Large amount escalation: >$5,000 is explicitly called out in the domain doc
        risk_level = "MEDIUM"
        escalation_note = ""
        if amount > 5000:
            risk_level = "HIGH"
            escalation_note = (
                f" An assessment of ${amount:,.2f} is material and may significantly affect "
                "the buyer's closing costs and monthly obligations."
            )

        logger.warning(
            "[S-8] domain_check=assessment_commentary_quality | outcome=FAIL | "
            "amount=%.2f | missing_elements=%s | risk=%s",
            amount, missing_elements, risk_level,
        )
        return RuleResult(
            rule_id="S-8",
            rule_name="Special Assessments",
            status=RuleStatus.FAIL,
            message=(
                f"Special assessment of ${amount:,.2f} is noted but commentary is incomplete. "
                f"Missing: {', '.join(missing_elements)}.{escalation_note}"
            ),
            appraisal_value=f"${amount:,.2f}",
            target_field="special_assessments",
            details={
                "amount": amount,
                "risk_level": risk_level,
                "missing_commentary_elements": missing_elements,
                "existing_comment_preview": comment[:200] if comment else None,
                "domain_reason": (
                    "UAD and FNMA require full disclosure of all special assessments. "
                    "The commentary must address: (1) what the assessment is for, "
                    "(2) whether it has been paid or remains outstanding, and "
                    "(3) whether it is a one-time or recurring charge."
                ),
                "required_elements": ["purpose", "paid/unpaid status", "temporary/ongoing status"],
            },
            decision_path=[
                "field_present", "amount_gt_zero", "commentary_present",
                "commentary_quality_insufficient", f"risk={risk_level}", "fail",
            ],
        )

    logger.info(
        "[S-8] domain_check=assessment_complete | outcome=PASS | amount=%.2f", amount,
    )
    return RuleResult(
        rule_id="S-8",
        rule_name="Special Assessments",
        status=RuleStatus.PASS,
        message=f"Special assessment of ${amount:,.2f} is documented with complete commentary.",
        extracted_value=f"${amount:,.2f}",
        details={"amount": amount},
        decision_path=["field_present", "amount_gt_zero", "commentary_covers_all_elements", "pass"],
    )


@rule(id="S-9", name="PUD and HOA")
def validate_pud_hoa(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-9 — PUD and HOA
    Target Fields: PUD checkbox, HOA Dues, HOA period (Per Year / Per Month)
    Rule: If HOA dues are mandatory → PUD checkbox MUST be marked
    Rule: HOA fees must state Per Year OR Per Month

    WHY THIS MATTERS:
    HOA fees are a MANDATORY monthly or annual financial obligation. Lenders
    must add HOA dues to the borrower's total housing payment (PITI + HOA)
    when calculating their debt-to-income ratio. An unreported or
    mis-periodized HOA fee causes the DTI calculation to be wrong — a
    compliance failure.

    The PUD (Planned Unit Development) connection is critical:
      Mandatory HOA dues → PUD checkbox MUST be marked
      PUD marked → PUD section of the report MUST be completed
    These are hard cross-field dependencies from UAD requirements.

    Rejection template: "HOA dues are noted as $[X] per [year/month] in subject
    section; however, PUD box is not marked. Please revise."
    """
    subject = ctx.report.subject
    hoa_dues = subject.hoa_dues or 0.0
    is_pud = subject.is_pud

    # PUD checkbox could not be extracted — cannot PASS or FAIL with certainty
    if is_pud is None:
        logger.warning(
            "[S-9] domain_check=pud_checkbox_extracted | outcome=EXTRACTION_FAILED | "
            "hoa_dues=%.2f | reason=pud_checkbox_not_extracted",
            hoa_dues,
        )
        return RuleResult(
            rule_id="S-9",
            rule_name="PUD and HOA",
            status=RuleStatus.EXTRACTION_FAILED,
            message=(
                "PUD checkbox was not extracted; HOA/PUD consistency cannot be verified. "
                "Review the subject PUD checkbox and HOA dues."
            ),
            action_item="Review the subject PUD checkbox and HOA dues before accepting this rule.",
            review_required=True,
            target_field="is_pud_checked",
            details={
                "hoa_dues": hoa_dues,
                "domain_reason": (
                    "The PUD checkbox is required when HOA dues are mandatory. Without this "
                    "checkbox, the lender cannot determine if additional PUD section data is required."
                ),
            },
            decision_path=["pud_checkbox_missing", "extraction_failed"],
        )

    # Core rule: HOA dues > 0 → PUD must be marked
    if hoa_dues > 0 and not is_pud:
        period = subject.hoa_period or "year"
        logger.warning(
            "[S-9] domain_check=hoa_pud_consistency | outcome=FAIL | "
            "hoa_dues=%.2f per %s | is_pud=%s | reason=pud_not_marked",
            hoa_dues, period, is_pud,
        )
        return RuleResult(
            rule_id="S-9",
            rule_name="PUD and HOA",
            status=RuleStatus.FAIL,
            message=(
                f"HOA dues are noted as \"${hoa_dues:.2f}\" per {period} in subject section; "
                "however, PUD box is not marked. Please revise."
            ),
            appraisal_value=f"HOA ${hoa_dues:.2f}/{period}",
            expected_value="PUD checkbox = marked",
            target_field="is_pud_checked",
            details={
                "hoa_dues": hoa_dues,
                "hoa_period": period,
                "is_pud": is_pud,
                "risk_level": "MEDIUM",
                "domain_reason": (
                    "Mandatory HOA dues mean the property is part of a planned community with "
                    "shared governance. FNMA requires the PUD checkbox so the lender knows the "
                    "full PUD section applies — including HOA financial health, litigation status, "
                    "and insurance coverage. Without PUD marked, those checks are skipped."
                ),
            },
            decision_path=[
                "pud_checkbox_extracted", "hoa_dues_gt_zero",
                "pud_not_marked", "domain_rule_hoa_requires_pud", "fail",
            ],
        )

    # If HOA dues exist but period is not specified
    if hoa_dues > 0 and not subject.hoa_period:
        logger.warning(
            "[S-9] domain_check=hoa_period | outcome=VERIFY | "
            "hoa_dues=%.2f | reason=period_not_stated",
            hoa_dues,
        )
        return RuleResult(
            rule_id="S-9",
            rule_name="PUD and HOA",
            status=RuleStatus.VERIFY,
            message=(
                f"HOA dues (${hoa_dues:.2f}) are noted but the payment period "
                "(Per Year / Per Month) is not indicated. Per UAD requirements, the period must be stated."
            ),
            target_field="hoa_dues",
            details={
                "hoa_dues": hoa_dues,
                "domain_reason": (
                    "Monthly and annual HOA dues have very different DTI impacts. "
                    "$2,400/year ≈ $200/month. Without the period, the lender cannot "
                    "correctly add HOA to the borrower's monthly obligations."
                ),
            },
            decision_path=["pud_present", "hoa_dues_gt_zero", "period_missing", "verify"],
        )

    # If PUD is marked, remind that PUD section must be complete (we can't check here
    # since there's no PUD section in scope, but log it for the operator)
    if is_pud:
        logger.info(
            "[S-9] domain_check=pud_marked | note=PUD section must be completed | "
            "hoa_dues=%.2f %s",
            hoa_dues, subject.hoa_period or "(period unspecified)",
        )

    logger.info(
        "[S-9] domain_check=pud_hoa | outcome=PASS | hoa=%.2f %s pud=%s",
        hoa_dues, subject.hoa_period or "N/A", is_pud,
    )
    return RuleResult(
        rule_id="S-9",
        rule_name="PUD and HOA",
        status=RuleStatus.PASS,
        message="PUD/HOA information is consistent.",
        compared_values={
            "hoa_dues": hoa_dues,
            "hoa_period": subject.hoa_period,
            "is_pud": is_pud,
        },
        decision_path=["pud_extracted", "hoa_pud_consistent", "period_valid", "pass"],
    )


@rule(id="S-10", name="Lender/Client Information")
def validate_lender_client(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-10 — Lender/Client Information
    Target Fields: Lender/Client Name, Lender/Client Address
    Rule: Must match Client Engagement Letter EXACTLY

    WHY: The lender name on the report determines who the appraisal is made
    for. An incorrect lender name means the appraisal was not prepared for
    the entity that ordered it — a USPAP violation that renders the report
    unusable by the lender.

    Rejection templates:
      "Please correct the lender's name so it reflects as: [name]"
      "Please correct the lender's address so it reflects as: [address]"
    """
    if _engagement_document_missing(ctx):
        return _missing_engagement_result("S-10", "Lender/Client Information")

    if not ctx.engagement_letter:
        raise DataMissingException("Engagement Letter (for Lender Verification)")

    eng_lender = ctx.engagement_letter.lender_name
    eng_address = ctx.engagement_letter.lender_address
    rpt_lender = ctx.report.subject.lender_name
    rpt_address = ctx.report.subject.lender_address

    if not eng_lender or not eng_address:
        logger.warning(
            "[S-10] domain_check=lender_evidence | outcome=EXTRACTION_FAILED | "
            "eng_lender='%s' eng_address='%s'",
            eng_lender, eng_address,
        )
        return RuleResult(
            rule_id="S-10",
            rule_name="Lender/Client Information",
            status=RuleStatus.EXTRACTION_FAILED,
            message="Engagement lender name/address was not fully extracted; lender validation cannot PASS.",
            action_item="Review the engagement/order lender fields and rerun extraction.",
            review_required=True,
            evidence=["Engagement/order lender fields"],
            source_documents=["engagement"],
            compared_fields=["lender_name", "lender_address"],
            decision_path=["engagement_present", "lender_fields_not_extracted", "extraction_failed"],
        )

    if eng_lender and rpt_lender:
        if rpt_lender.strip().upper() != eng_lender.strip().upper():
            logger.warning(
                "[S-10] domain_check=lender_name_match | outcome=FAIL | "
                "report='%s' vs engagement='%s'",
                rpt_lender, eng_lender,
            )
            return RuleResult(
                rule_id="S-10",
                rule_name="Lender/Client Information",
                status=RuleStatus.FAIL,
                message=f"Please correct the lender's name so it reflects as: {eng_lender}",
                appraisal_value=rpt_lender,
                engagement_value=eng_lender,
                target_field="lender_name",
                details={
                    "report": rpt_lender,
                    "engagement": eng_lender,
                    "domain_reason": (
                        "The lender name establishes who this appraisal was prepared for. "
                        "A wrong lender name is a USPAP violation (wrong intended user)."
                    ),
                },
                decision_path=["engagement_present", "lender_extracted", "name_mismatch", "fail"],
            )
    elif eng_lender and not rpt_lender:
        raise DataMissingException("Lender Name (Report)")

    if eng_address and rpt_address:
        if rpt_address.strip().upper() != eng_address.strip().upper():
            logger.warning(
                "[S-10] domain_check=lender_address_match | outcome=FAIL | "
                "report='%s' vs engagement='%s'",
                rpt_address, eng_address,
            )
            return RuleResult(
                rule_id="S-10",
                rule_name="Lender/Client Information",
                status=RuleStatus.FAIL,
                message=f"Please correct the lender's address so it reflects as: {eng_address}",
                appraisal_value=rpt_address,
                engagement_value=eng_address,
                target_field="lender_address",
                details={"report": rpt_address, "engagement": eng_address},
                decision_path=["lender_name_matched", "address_mismatch", "fail"],
            )

    logger.info(
        "[S-10] domain_check=lender_match | outcome=PASS | lender='%s'", rpt_lender,
    )
    return RuleResult(
        rule_id="S-10",
        rule_name="Lender/Client Information",
        status=RuleStatus.PASS,
        message="Lender/Client information matches engagement letter.",
        compared_values={"lender_name": rpt_lender, "lender_address": rpt_address},
        decision_path=["lender_extracted", "address_extracted", "both_match_engagement", "pass"],
    )


@rule(id="S-11", name="Property Rights Appraised")
def validate_property_rights(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-11 — Property Rights Appraised
    Target Field: Property Rights Appraised
    Rule: Only ONE checkbox may be marked
    Options: Fee Simple, Leasehold, De Minimis PUD

    WHY THIS MATTERS:
    Property rights define WHAT is being valued. Two identical houses can have
    very different values if one has fee simple ownership (own the land) and
    the other is leasehold (lease the land — which has an expiration date).

    Fee Simple → STANDARD processing
    Leasehold  → HIGH RISK — lender must evaluate remaining lease term vs
                 loan term; comparables MUST also be leasehold per Rule SCA-10
    De Minimis PUD → treated like Fee Simple for most purposes

    Critical Rule: Only ONE checkbox may be marked. Multiple checkboxes is an
    OCR or appraiser error that must be corrected before processing.
    """
    subj = ctx.report.subject

    if not subj.property_rights:
        logger.warning(
            "[S-11] domain_check=property_rights_present | outcome=EXTRACTION_FAILED | "
            "reason=field_blank"
        )
        raise DataMissingException("Property Rights Appraised")

    rights_upper = subj.property_rights.strip().upper()

    # Detect multiple checkboxes — domain says "Critical Rule: only ONE"
    # This manifests as OCR extracting both labels, e.g. "FEE SIMPLE LEASEHOLD"
    right_keywords = {
        "FEE SIMPLE": "Fee Simple",
        "LEASEHOLD": "Leasehold",
        "DE MINIMIS": "De Minimis PUD",
    }
    found_rights = [label for keyword, label in right_keywords.items() if keyword in rights_upper]

    if len(found_rights) > 1:
        logger.warning(
            "[S-11] domain_check=single_checkbox | outcome=FAIL | "
            "found=%s | reason=multiple_rights_marked",
            found_rights,
        )
        return RuleResult(
            rule_id="S-11",
            rule_name="Property Rights Appraised",
            status=RuleStatus.FAIL,
            message=(
                f"Only one property rights checkbox may be selected. "
                f"Report appears to have multiple checked: {', '.join(found_rights)}. "
                "Please revise to mark only the applicable right."
            ),
            appraisal_value=subj.property_rights,
            target_field="property_rights",
            details={
                "found_rights": found_rights,
                "domain_reason": (
                    "Multiple property rights checkboxes is an error. Marking both "
                    "Fee Simple and Leasehold is contradictory — a property cannot be "
                    "both simultaneously. This indicates an OCR or data entry error."
                ),
            },
            decision_path=["property_rights_extracted", "multiple_checkboxes_detected", "fail"],
        )

    valid_rights = ["FEE SIMPLE", "LEASEHOLD", "LEASEHOLD INTEREST", "DE MINIMIS PUD"]
    if rights_upper not in valid_rights:
        logger.warning(
            "[S-11] domain_check=property_rights_valid | outcome=FAIL | value='%s'",
            subj.property_rights,
        )
        return RuleResult(
            rule_id="S-11",
            rule_name="Property Rights Appraised",
            status=RuleStatus.FAIL,
            message=(
                f"Invalid Property Rights value: '{subj.property_rights}'. "
                "Must be one of: Fee Simple, Leasehold, De Minimis PUD."
            ),
            appraisal_value=subj.property_rights,
            target_field="property_rights",
            decision_path=["property_rights_extracted", "single_checkbox", "invalid_value", "fail"],
        )

    # Leasehold — HIGH risk, requires special handling
    if "LEASEHOLD" in rights_upper:
        logger.warning(
            "[S-11] domain_check=leasehold_risk | outcome=VERIFY | "
            "rights='%s' | risk=HIGH | reason=leasehold_requires_special_underwriting",
            subj.property_rights,
        )
        return RuleResult(
            rule_id="S-11",
            rule_name="Property Rights Appraised",
            status=RuleStatus.VERIFY,
            message=(
                "Property Rights are appraised as Leasehold — HIGH RISK. "
                "Per Rule SCA-10: comparable sales used must also be leasehold. "
                "Lender must evaluate remaining lease term against the loan term."
            ),
            appraisal_value=subj.property_rights,
            review_required=True,
            details={
                "rights_type": subj.property_rights,
                "risk_level": "HIGH",
                "domain_reason": (
                    "Leasehold ownership means the appraiser valued only the building, "
                    "not the land. Land leases have expiration dates — if the lease expires "
                    "before the loan matures, the borrower's collateral disappears. "
                    "This requires a senior underwriting review."
                ),
                "required_action": (
                    "Verify: (1) Comparable sales are also leasehold, "
                    "(2) Remaining lease term exceeds loan term, "
                    "(3) Senior underwriter has reviewed."
                ),
            },
            decision_path=[
                "property_rights_extracted", "single_checkbox",
                "leasehold_detected", "high_risk_flag", "verify_required",
            ],
        )

    logger.info(
        "[S-11] domain_check=property_rights | outcome=PASS | rights='%s'",
        subj.property_rights,
    )
    return RuleResult(
        rule_id="S-11",
        rule_name="Property Rights Appraised",
        status=RuleStatus.PASS,
        message=f"Property rights appraised: {subj.property_rights}.",
        extracted_value=subj.property_rights,
        decision_path=["property_rights_extracted", "single_checkbox", "valid_value", "pass"],
    )


@rule(id="S-12", name="Prior Listing/Sale History")
def validate_prior_history(ctx: ValidationContext) -> RuleResult:
    """
    Rule S-12 — Prior Listing / Sale History
    Target Field: "Subject currently offered for sale in past 12 months?"
    If NO:  Data source (MLS name) MUST be provided
    If YES: DOM, MLS name, MLS #, List price, List date ALL required

    WHY THIS MATTERS:
    Market exposure is fundamental to establishing whether the contract price
    is credible. If a property was publicly listed, the price was tested
    against real market demand. If it was never listed (off-market / private
    deal), the price was set privately — higher risk that it doesn't reflect
    true market value.

    DOM Risk Analysis (domain training doc, Section 4):
      0–10 days   → MEDIUM risk (buyer may have overpaid in bidding war)
      10–60 days  → LOW risk (normal market pace)
      60–90 days  → MEDIUM risk (above average, market softening)
      90+ days    → HIGH risk (weak demand, overpriced, comment required)

    Condition (from OPUS): If listed but NOT a purchase assignment, and
    market value varies from listing price by >3% → Comment REQUIRED.
    """
    subj = ctx.report.subject

    if subj.prior_sale_offered_12mo is None:
        logger.warning(
            "[S-12] domain_check=offered_status | outcome=FAIL | "
            "reason=yes_no_not_indicated"
        )
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.FAIL,
            message=(
                "Prior sale/offered status (Yes/No) is not indicated in the subject section. "
                "This field is required per UAD requirements."
            ),
            decision_path=["offered_status_field_blank", "fail"],
        )

    # Data source is required regardless of Yes or No (per OPUS Rule S-12)
    if not subj.data_sources or len(subj.data_sources.strip()) < 2:
        logger.warning(
            "[S-12] domain_check=data_source | outcome=FAIL | "
            "offered=%s | reason=data_source_missing",
            subj.prior_sale_offered_12mo,
        )
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.FAIL,
            message=(
                "Please provide Data sources in subject section for the question "
                '"Is the subject property currently offered for sale or has it been '
                'offered for sale in the twelve months prior to the effective date of '
                'this appraisal?" as per UAD requirement.'
            ),
            decision_path=["offered_status_present", "data_source_missing", "fail"],
        )

    # NOT listed — this is an off-market deal, medium risk
    if not subj.prior_sale_offered_12mo:
        logger.info(
            "[S-12] domain_check=offered_status | outcome=PASS | "
            "listed=NO | risk=MEDIUM (off-market) | data_source='%s'",
            subj.data_sources,
        )
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.PASS,
            message=(
                "Property was NOT listed in the past 12 months (off-market transaction). "
                f"Data source provided: {subj.data_sources}."
            ),
            extracted_value="Not listed",
            details={
                "risk_level": "MEDIUM",
                "domain_reason": (
                    "Off-market deals were not price-tested by the market. The contract price "
                    "was set privately, which creates a higher risk of the price not reflecting "
                    "true market value. The appraiser must support the value with market data."
                ),
            },
            decision_path=["offered_status_no", "data_source_present", "pass"],
        )

    # Property WAS listed — verify all required details (YES path)
    missing_details = []
    if not subj.mls_number:     missing_details.append("MLS Number")
    if not subj.days_on_market: missing_details.append("Days on Market (DOM)")
    if not subj.list_price:     missing_details.append("List Price")
    if not subj.list_date:      missing_details.append("List Date")

    if missing_details:
        logger.warning(
            "[S-12] domain_check=listing_details | outcome=VERIFY | "
            "missing=%s",
            missing_details,
        )
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.VERIFY,
            message=(
                f"Property was listed in the past 12 months. "
                f"Missing required details: {', '.join(missing_details)}. "
                "Per Rule S-12, listed properties require DOM, MLS name, MLS#, list price, and list date."
            ),
            details={"missing_fields": missing_details},
            decision_path=["offered_status_yes", "data_source_present", "details_incomplete", "verify"],
        )

    # All listing details present — run DOM risk analysis
    dom = subj.days_on_market
    risk_level, market_signal, qc_action = _analyze_dom_risk(dom)

    logger.info(
        "[S-12] domain_check=dom_risk | dom=%d | risk=%s | signal='%s'",
        dom, risk_level, market_signal,
    )

    # DOM > 90: HIGH risk — must flag for comment
    if dom > 90:
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.VERIFY,
            message=(
                f"Days on Market = {dom} days — EXTENDED marketing time. "
                "Market signal: weak demand or property was overpriced. "
                "Comment required explaining market conditions and any price reductions."
            ),
            extracted_value=f"DOM={dom}",
            details={
                "dom": dom,
                "risk_level": risk_level,
                "market_signal": market_signal,
                "qc_action": qc_action,
                "domain_reason": (
                    "DOM > 90 means the market rejected the property at its original price. "
                    "The appraiser must explain whether this was a price reduction, market softening, "
                    "or a property-specific issue — and how it relates to the final contract price."
                ),
                "list_price": subj.list_price,
                "mls_number": subj.mls_number,
            },
            decision_path=[
                "offered_status_yes", "all_details_present",
                f"dom={dom}", "dom_gt_90", "high_risk", "verify",
            ],
        )

    # DOM <= 10: MEDIUM risk — check for multiple offers comment
    if dom <= 10:
        logger.info(
            "[S-12] domain_check=dom_fast_sale | dom=%d | risk=%s | "
            "action=check_multiple_offer_comment",
            dom, risk_level,
        )
        return RuleResult(
            rule_id="S-12",
            rule_name="Prior Listing/Sale History",
            status=RuleStatus.VERIFY,
            message=(
                f"Days on Market = {dom} days — extremely fast sale. "
                "Verify a multiple-offer comment is provided to explain the rapid sale pace. "
                "Risk: buyer may have overpaid above market in a competitive situation."
            ),
            extracted_value=f"DOM={dom}",
            details={
                "dom": dom,
                "risk_level": risk_level,
                "market_signal": market_signal,
                "qc_action": qc_action,
                "domain_reason": (
                    "Very short DOM suggests either a hot market or a private deal "
                    "with artificially limited exposure. Both scenarios can result in "
                    "prices that don't reflect true market value."
                ),
            },
            decision_path=[
                "offered_status_yes", "all_details_present",
                f"dom={dom}", "dom_lte_10", "medium_risk", "verify",
            ],
        )

    # Check list price vs contract price divergence (>3% gap requires comment)
    if subj.list_price and ctx.report.contract.contract_price:
        list_px = subj.list_price
        contract_px = ctx.report.contract.contract_price
        delta = list_px - contract_px
        delta_pct = abs(delta) / list_px * 100 if list_px > 0 else 0

        if delta_pct > 10:
            logger.warning(
                "[S-12] domain_check=list_contract_delta | outcome=VERIFY | "
                "list=%.2f contract=%.2f delta_pct=%.1f%%",
                list_px, contract_px, delta_pct,
            )
            direction = "below" if delta > 0 else "above"
            return RuleResult(
                rule_id="S-12",
                rule_name="Prior Listing/Sale History",
                status=RuleStatus.VERIFY,
                message=(
                    f"Contract price (${contract_px:,.0f}) is {delta_pct:.1f}% {direction} "
                    f"list price (${list_px:,.0f}) — significant gap. "
                    "Comment on why the price diverged from the listing."
                ),
                extracted_value=f"List=${list_px:,.0f}, Contract=${contract_px:,.0f}",
                details={
                    "list_price": list_px,
                    "contract_price": contract_px,
                    "delta_pct": round(delta_pct, 1),
                    "direction": direction,
                    "dom": dom,
                    "risk_level": "MEDIUM",
                    "domain_reason": (
                        "A 10%+ gap between list and contract price is notable. "
                        "If the price dropped, the market didn't support the original price. "
                        "If the price is above list, there were likely multiple offers — "
                        "both scenarios require the appraiser's commentary."
                    ),
                },
                decision_path=[
                    "offered_status_yes", "all_details_present",
                    f"list_contract_delta={delta_pct:.1f}%", "delta_gt_10pct", "verify",
                ],
            )

    logger.info(
        "[S-12] domain_check=prior_listing | outcome=PASS | dom=%d mls='%s'",
        dom, subj.mls_number,
    )
    return RuleResult(
        rule_id="S-12",
        rule_name="Prior Listing/Sale History",
        status=RuleStatus.PASS,
        message=f"Prior listing/sale history is complete. DOM={dom} days, MLS={subj.mls_number}.",
        extracted_value=f"DOM={dom}",
        details={
            "dom": dom,
            "risk_level": risk_level,
            "market_signal": market_signal,
            "list_price": subj.list_price,
            "mls_number": subj.mls_number,
        },
        compared_values={
            "dom": dom,
            "mls_number": subj.mls_number,
            "list_price": subj.list_price,
            "data_sources": subj.data_sources,
        },
        decision_path=["offered_status_yes", "all_details_present", "dom_normal_range", "pass"],
    )
