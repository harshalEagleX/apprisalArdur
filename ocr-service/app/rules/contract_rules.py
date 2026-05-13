"""
Contract Section Rules — C-1 through C-5

Domain source: appraisal_deep_training_domain_knowledge.md (Contract Section)
Rule source:   QCChceklistOpus.md (Contract Section Rules)

CRITICAL GATE — READ FIRST:
The ENTIRE contract section applies ONLY to Purchase assignments.
For Refinance, every field must be blank.  An automated system MUST
check assignment_type before processing any contract field.

WHY THIS SECTION EXISTS:
The contract section is where the appraiser's valuation meets the real-world
deal. The lender ordered this appraisal specifically to verify that the agreed
contract price reflects actual market value. Every field here is about answering
one fundamental question: "Did the buyer pay a fair price?"

If the answer is NO (or unclear), the lender may:
  - Reduce the loan amount to the appraised value
  - Require price renegotiation
  - Decline the loan entirely

LOGGING PHILOSOPHY:
Every decision branch logs with structured key=value pairs so operators and
the ML system can trace exactly WHY a particular flag was raised.  This drives
both the improvement loop and the operator review queue prioritization.
"""

import logging
import re
from datetime import datetime
from typing import Optional, Tuple, List

from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext

logger = logging.getLogger(__name__)


# ── Personal property boilerplate filter ───────────────────────────────────────
# These phrases appear in boilerplate contract language (e.g. Georgia contracts)
# and are NOT real personal property items that need appraisal commentary.
_GAR_PERSONAL_PROPERTY_BOILERPLATE = (
    "firewood shall not be considered debris",
    "property to be delivered in clean condition",
    "property being sold as-is",
    "property is being sold as-is",
    "of the otherwise identified in this agreement as remaining with the property",
)

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "any", "all", "no",
    "not", "if", "as", "so", "that", "this", "these", "those", "which",
})

# Valid sale types per OPUS Rule C-1
_VALID_SALE_TYPES = {
    "ARMS-LENGTH", "ARMS LENGTH", "ARM'S LENGTH",
    "NON ARMS-LENGTH", "NON ARMS LENGTH", "NON ARM'S LENGTH",
    "REO", "REAL ESTATE OWNED", "BANK OWNED",
    "SHORT SALE",
    "COURT ORDERED", "COURT ORDERED SALE",
    "ESTATE SALE",
}


# ── C-1 Domain Helpers ──────────────────────────────────────────────────────────

# NLP red flags for canned/generic commentary (domain training doc, Section 11)
# These phrases are meaningless without supporting property-specific data.
# Finding them in commentary is a signal the appraiser wrote generic text.
_CANNED_COMMENTARY_PHRASES: List[Tuple[str, str]] = [
    (
        r"the\s+contract\s+price\s+reflects\s+market\s+value",
        "Generic statement without supporting comparables or price analysis",
    ),
    (
        r"price\s+is\s+supported\s+by\s+comparable\s+sales",
        "Generic support claim without naming which comparables or by how much",
    ),
    (
        r"no\s+unusual\s+conditions\s+were\s+noted",
        "Blanket dismissal without verifying concessions, seller motivation, or DOM",
    ),
    (
        r"the\s+sale\s+(?:is|appears\s+to\s+be)\s+(?:an?\s+)?arm(?:'s|s)\s+length",
        "Sale type stated without explaining basis (no data source reference)",
    ),
    (
        r"contract\s+(?:price\s+)?(?:has\s+been|was)\s+(?:analyzed|reviewed)",
        "Passive analysis claim without actually presenting the analysis results",
    ),
]


def _detect_canned_commentary(text: Optional[str]) -> List[Tuple[str, str]]:
    """
    Scan contract analysis commentary for known canned/generic phrases.

    Returns list of (phrase_found, reason_it_is_canned).

    WHY: Generic commentary is a QC failure. "The contract price reflects
    market value" tells the lender nothing — there are no comparables cited,
    no price per SF, no adjustments referenced. It is a template sentence that
    could apply to any report in any market.

    Domain rule: Commentary with canned phrases and no supporting specifics
    (no addresses, no dollar amounts, no adjustment analysis) should be flagged
    for revision so the appraiser provides actual analysis.
    """
    if not text or len(text.strip()) < 10:
        return []

    text_lower = text.lower()
    found = []
    for pattern, reason in _CANNED_COMMENTARY_PHRASES:
        if re.search(pattern, text_lower):
            # Check if there are any supporting specifics nearby
            # (dollar amounts, addresses, percentages — evidence of real analysis)
            has_specifics = bool(
                re.search(r"\$[\d,]+", text)          # dollar amount
                or re.search(r"\d+\s*(?:sf|sq\.?\s*ft)", text_lower)  # square footage
                or re.search(r"\d+\.\d+%|\d+%", text)  # percentage
                or re.search(r"\d{1,3}[,\s]\d{3}", text)  # large number (price)
            )
            if not has_specifics:
                found.append((re.search(pattern, text_lower).group(0), reason))

    return found


# ── C-2 Domain Helpers ──────────────────────────────────────────────────────────

def _normalize_date(value: Optional[str]) -> Optional[str]:
    """Normalize a date string to MM/DD/YYYY for comparison."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%m/%d/%Y")
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", value)
    if not m:
        return value
    month, day, year = m.groups()
    if len(year) == 2:
        year = f"20{year}" if int(year) < 70 else f"19{year}"
    try:
        return datetime(int(year), int(month), int(day)).strftime("%m/%d/%Y")
    except ValueError:
        return value


def _contract_dates_in_text(text: Optional[str]) -> List[str]:
    """Find all contract date references in raw text (for internal inconsistency detection)."""
    dates = []
    for m in re.finditer(
        r"\b(?:Date\s+of\s+Contract|Contract\s+Date)\b[^0-9]{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text or "", re.I
    ):
        normalized = _normalize_date(m.group(1))
        if normalized and normalized not in dates:
            dates.append(normalized)
    return dates


def _analyze_contract_age_risk(
    contract_date_str: Optional[str],
    effective_date_str: Optional[str] = None,
) -> Tuple[Optional[int], str, bool]:
    """
    Calculate how old the contract is relative to the effective appraisal date.

    Risk table (domain training doc, Section 7 — Date of Contract):
      < 60 days   → LOW, no comment required
      60–120 days → MEDIUM, verify market hasn't moved significantly
      > 120 days  → HIGH, comment required (market conditions analysis)

    Returns (days_old, risk_level, requires_comment).
    days_old is None if either date cannot be parsed.

    WHY: An old contract in a rising market means the agreed price may be
    BELOW current market — but the appraisal must still reflect current market
    value. In a declining market, an old contract may be ABOVE current values.
    Either way, the appraiser must analyze the market change.

    Contract Date Rule: Date of LAST signature = fully executed date.
    Example: Seller signs March 1, Buyer signs April 2 → Contract Date = April 2.
    """
    contract_date = _normalize_date(contract_date_str)
    if not contract_date:
        return None, "UNKNOWN", False

    try:
        contract_dt = datetime.strptime(contract_date, "%m/%d/%Y")
    except ValueError:
        return None, "UNKNOWN", False

    # Use effective date if available, otherwise today
    if effective_date_str:
        eff_date = _normalize_date(effective_date_str)
        try:
            effective_dt = datetime.strptime(eff_date, "%m/%d/%Y")
        except (ValueError, TypeError):
            effective_dt = datetime.now()
    else:
        effective_dt = datetime.now()

    days_old = (effective_dt - contract_dt).days

    if days_old < 0:
        # Contract date is in the future — likely a data error
        return days_old, "DATA_ERROR", True

    if days_old < 60:
        return days_old, "LOW", False
    if days_old <= 120:
        return days_old, "MEDIUM", False
    # > 120 days
    return days_old, "HIGH", True


def _analyze_concession_risk(
    concession_amount: Optional[float],
    contract_price: Optional[float],
) -> Tuple[str, float, str]:
    """
    Calculate concession as percentage of contract price and return risk level.

    Domain rule (domain training doc, Section 10):
      Concessions distort the true price. The "true" price is contract minus
      excess concessions. Lenders need the real price to calculate accurate LTV.

      > 5% of contract price → HIGH risk (value may be overstated)
      1–5%  → MEDIUM (normal seller-paid closing costs)
      < 1%  → LOW

    Returns (risk_level, concession_pct, explanation).

    WHY: A seller paying $25,000 of the buyer's closing costs on a $500,000
    purchase means the buyer effectively paid $475,000. If the appraiser
    doesn't reduce the value for excessive concessions, the lender's LTV
    calculation is wrong — they're lending 80% of $500,000 instead of 80%
    of $475,000.
    """
    if not concession_amount or not contract_price or contract_price <= 0:
        return "UNKNOWN", 0.0, "Cannot calculate — missing concession or contract price"

    pct = (concession_amount / contract_price) * 100

    if pct > 5:
        return (
            "HIGH",
            pct,
            f"Concessions (${concession_amount:,.0f}) are {pct:.1f}% of contract price — "
            "material amount that may overstate the effective contract price. "
            "Appraiser must address the concession impact on value.",
        )
    if pct >= 1:
        return (
            "MEDIUM",
            pct,
            f"Concessions (${concession_amount:,.0f}) are {pct:.1f}% of contract price — "
            "normal range but should be documented and described.",
        )
    return (
        "LOW",
        pct,
        f"Concessions (${concession_amount:,.0f}) are {pct:.1f}% of contract price — minimal.",
    )


# ── Personal property helpers ───────────────────────────────────────────────────

def _filter_personal_property_items(items: List[str]) -> List[str]:
    """
    Remove boilerplate contract language that is not real personal property.
    Keeps only items that are actual physical goods (appliances, furniture, etc.)
    and rejects contract boilerplate phrases that leaked into the extraction.
    """
    filtered = []
    for item in items or []:
        cleaned = re.sub(r"\s+", " ", str(item)).strip(" .;:,")
        lower = cleaned.lower()
        if not cleaned:
            continue
        if lower in _STOP_WORDS or (len(cleaned) < 4 and not re.search(r"\d", cleaned)):
            continue
        if any(phrase in lower for phrase in _GAR_PERSONAL_PROPERTY_BOILERPLATE):
            continue
        if re.search(r"\b(?:as-is|debris|clean condition|otherwise identified in this agreement)\b", lower):
            continue
        if re.match(r"^[a-z\s]{1,6}$", lower) and lower.split()[0] in _STOP_WORDS:
            continue
        filtered.append(cleaned)
    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# CONTRACT SECTION RULES (C-1 through C-5)
# ══════════════════════════════════════════════════════════════════════════════


@rule(id="C-1", name="Contract Analysis Requirement")
def validate_contract_analysis(ctx: ValidationContext) -> RuleResult:
    """
    Rule C-1 — Contract Analysis Requirement
    Target Field: Did/Did Not Analyze Contract checkbox
    If Purchase: Contract MUST be analyzed and section completed
    If Refinance: Entire contract section MUST be blank
    Commentary: Must show Sale Type + Analysis Results (not generic text)

    WHY THIS MATTERS:
    The "Did Analyze Contract" checkbox is the appraiser's certification that
    they reviewed the purchase agreement. Without this, the lender has no
    assurance that the appraiser knows the agreed price or any unusual terms.

    Sale types the appraiser must identify:
      Arms-Length       → Standard market transaction
      Non Arms-Length   → Family/business relationship; price may be non-market
      REO               → Bank-owned; priced to sell quickly
      Short Sale        → Seller owes more than market value; distressed pricing
      Court Ordered Sale → Price set by legal process, not market

    NLP check: Detect canned/generic commentary that provides no real analysis.
    Generic phrases like "The contract price reflects market value" with no
    specific data are a QC failure — they don't actually analyze anything.

    Rejection templates:
      "Assignment is meant for a refinance transaction; per UAD requirements,
       the contract section should be left blank."
      "Appraiser must provide detailed reasoning and reconciliation if
       appraised value varies from contract price."
    """
    # ── Gate 1: Refinance — contract section MUST be blank ──
    assignment = _get_assignment_type(ctx)

    if assignment == "REFINANCE":
        if ctx.report.contract.contract_price is not None:
            logger.warning(
                "[C-1] domain_check=refinance_contract_blank | outcome=FAIL | "
                "assignment=REFINANCE | contract_price=%.2f | "
                "reason=contract_section_must_be_blank",
                ctx.report.contract.contract_price,
            )
            return RuleResult(
                rule_id="C-1",
                rule_name="Contract Analysis Requirement",
                status=RuleStatus.FAIL,
                message=(
                    "Assignment is meant for a refinance transaction; per UAD requirements, "
                    "the contract section should be left blank."
                ),
                appraisal_value=f"Contract price: ${ctx.report.contract.contract_price:,.2f}",
                expected_value="Contract section: blank",
                details={
                    "assignment_type": "Refinance",
                    "domain_reason": (
                        "In a refinance, the current owner is keeping the property — there is "
                        "no purchase agreement. The contract section is a purchase-transaction tool. "
                        "Any data in it on a refinance suggests a form setup error."
                    ),
                },
                decision_path=["assignment=REFINANCE", "contract_data_present", "fail"],
            )

        logger.info("[C-1] assignment=REFINANCE | contract_section_blank | NOT_APPLICABLE")
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.NOT_APPLICABLE,
            message="Refinance: Contract section purchase-analysis rule is not applicable.",
            decision_path=["assignment=REFINANCE", "contract_section_blank", "not_applicable"],
        )

    # ── Gate 2: Purchase — checkbox must be detected ──
    if ctx.report.contract.did_analyze_contract is None:
        logger.warning(
            "[C-1] domain_check=analyze_checkbox | outcome=VERIFY | "
            "reason=checkbox_not_extracted"
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message=(
                "Did/Did Not Analyze Contract checkbox was not detected. "
                "Please verify manually that the checkbox is marked 'Did Analyze Contract'."
            ),
            decision_path=["assignment=PURCHASE", "did_analyze_checkbox_not_found", "verify"],
        )

    # ── Gate 3: "Did Not Analyze" is a hard FAIL ──
    if ctx.report.contract.did_analyze_contract is False:
        logger.warning(
            "[C-1] domain_check=analyze_checkbox | outcome=FAIL | "
            "reason=did_NOT_analyze_contract"
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.FAIL,
            message=(
                "Contract must be analyzed for purchase transactions. "
                "Please mark 'Did Analyze Contract' and provide analysis."
            ),
            appraisal_value="Did Not Analyze",
            expected_value="Did Analyze",
            decision_path=["assignment=PURCHASE", "did_not_analyze_checkbox", "fail"],
        )

    # ── Gate 4: Commentary must exist and be non-trivial ──
    comment = ctx.report.contract.contract_analysis_comment or ""
    if len(comment.strip()) < 20:
        logger.warning(
            "[C-1] domain_check=commentary_present | outcome=VERIFY | "
            "comment_length=%d | reason=commentary_too_short",
            len(comment.strip()),
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message=(
                "Contract is marked 'Did Analyze' but commentary is missing or too brief. "
                "Appraiser must provide detailed analysis including sale type and results."
            ),
            decision_path=[
                "assignment=PURCHASE", "did_analyze=True",
                "commentary_length_lt_20", "verify",
            ],
        )

    # ── Gate 5: Canned commentary detection ──
    canned_phrases = _detect_canned_commentary(comment)
    if canned_phrases:
        phrase_list = "; ".join(f'"{p}"' for p, _ in canned_phrases)
        reason_list = "; ".join(r for _, r in canned_phrases)
        logger.warning(
            "[C-1] domain_check=canned_commentary | outcome=VERIFY | "
            "found_phrases=%d | phrases=%s",
            len(canned_phrases), phrase_list,
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message=(
                f"Contract analysis commentary contains generic/canned language: {phrase_list}. "
                "These statements provide no specific analysis. The appraiser should reference "
                "specific comparable sales, dollar amounts, or market conditions."
            ),
            details={
                "canned_phrases_found": [p for p, _ in canned_phrases],
                "reasons": [r for _, r in canned_phrases],
                "domain_reason": (
                    "Canned commentary is a QC failure because it could apply to any report "
                    "in any market. Real analysis must be specific to THIS property, THIS market, "
                    "THIS contract — with actual data to support the conclusion."
                ),
            },
            decision_path=[
                "assignment=PURCHASE", "did_analyze=True",
                "commentary_present", "canned_phrases_detected", "verify",
            ],
        )

    # ── Gate 6: Sale type must be identified ──
    sale_type = ctx.report.contract.sale_type
    if not sale_type:
        logger.warning(
            "[C-1] domain_check=sale_type | outcome=VERIFY | reason=sale_type_not_stated"
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message=(
                "Please identify the sale type in the contract analysis: "
                "Arms-Length, Non Arms-Length, REO, Short Sale, or Court Ordered Sale."
            ),
            details={
                "domain_reason": (
                    "The sale type tells the lender whether the price was market-driven or "
                    "influenced by a relationship, financial distress, or legal compulsion. "
                    "Each type has different underwriting implications."
                ),
            },
            decision_path=[
                "assignment=PURCHASE", "did_analyze=True",
                "commentary_adequate", "sale_type_missing", "verify",
            ],
        )

    # Validate sale type value against known valid types
    sale_type_upper = sale_type.strip().upper()
    if not any(valid in sale_type_upper for valid in _VALID_SALE_TYPES):
        logger.warning(
            "[C-1] domain_check=sale_type_valid | outcome=VERIFY | value='%s'", sale_type,
        )
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message=(
                f"Sale type '{sale_type}' is not a recognized UAD sale type. "
                "Must be one of: Arms-Length, Non Arms-Length, REO, Short Sale, Court Ordered Sale."
            ),
            appraisal_value=sale_type,
            details={"valid_sale_types": list(_VALID_SALE_TYPES)},
            decision_path=[
                "assignment=PURCHASE", "did_analyze=True",
                "sale_type_present", "sale_type_not_recognized", "verify",
            ],
        )

    logger.info(
        "[C-1] domain_check=contract_analysis_complete | outcome=PASS | "
        "sale_type='%s' comment_length=%d",
        sale_type, len(comment),
    )
    return RuleResult(
        rule_id="C-1",
        rule_name="Contract Analysis Requirement",
        status=RuleStatus.PASS,
        message=f"Contract analyzed. Sale type: {sale_type}.",
        extracted_value=f"Sale type: {sale_type}",
        details={"sale_type": sale_type, "commentary_length": len(comment)},
        compared_values={"did_analyze": True, "sale_type": sale_type},
        decision_path=[
            "assignment=PURCHASE", "did_analyze=True",
            "commentary_specific", "sale_type_valid", "pass",
        ],
    )


@rule(id="C-2", name="Contract Price and Date")
def validate_contract_price_date(ctx: ValidationContext) -> RuleResult:
    """
    Rule C-2 — Contract Price and Date
    Target Fields: Contract Price, Date of Contract
    Rule: Must match Purchase Agreement EXACTLY
    Contract Date: Date of LAST signature (fully executed date)

    WHY THIS MATTERS:
    The contract price is the SINGLE MOST IMPORTANT data point in a purchase
    appraisal. The lender ordered the appraisal to verify that the agreed price
    reflects actual market value.

    The "Contract Price Triangle":
      Contract Price ↔ Appraised Value ↔ Comparable Sales
    All three must be reconciled. Material divergence requires commentary.

    Contract Age Risk (domain training doc, Section 7):
      < 60 days  → LOW (normal)
      60–120 days → MEDIUM (verify market hasn't moved)
      > 120 days  → HIGH (comment required on market conditions)

    Cross-check: Contract price vs appraised value
      > 3%  variance → FLAG (comment required)
      > 10% variance → HOLD (escalate for review)

    Rejection templates:
      "In contract section, Contract Price noted as $X; however, purchase
       contract shows $Y. Please verify."
      "In contract section, Contract Date noted as [date]; however, purchase
       contract shows [date]. Please verify."
    """
    # Skip entirely for Refinance
    if _get_assignment_type(ctx) == "REFINANCE":
        logger.info("[C-2] assignment=REFINANCE | NOT_APPLICABLE")
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.NOT_APPLICABLE,
            message="Refinance: Contract price/date rule is not applicable.",
            decision_path=["assignment=REFINANCE", "not_applicable"],
        )

    rpt = ctx.report.contract

    # Contract price must exist in report
    if rpt.contract_price is None:
        logger.warning(
            "[C-2] domain_check=contract_price_present | outcome=VERIFY | "
            "reason=price_not_extracted"
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.VERIFY,
            message="Contract Price not extracted from report. Please verify manually.",
            decision_path=["assignment=PURCHASE", "contract_price_not_found", "verify"],
        )

    # Purchase assignment REQUIRES a purchase agreement — report-only is not enough
    if ctx.purchase_agreement is None:
        logger.warning(
            "[C-2] domain_check=pa_present | outcome=SOURCE_MISSING | "
            "contract_price=%.2f | reason=no_purchase_agreement",
            rpt.contract_price,
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.SOURCE_MISSING,
            message=(
                "Purchase agreement was not provided or could not be parsed; "
                "contract price/date cannot pass on appraisal-only evidence."
            ),
            action_item="Upload a readable purchase agreement and rerun QC before accepting the contract price/date.",
            review_required=True,
            evidence=["Appraisal contract section"],
            source_documents=["appraisal"],
            compared_fields=["contract_price", "date_of_contract"],
            decision_path=["report_contract_price_found", "purchase_agreement_missing", "source_missing"],
        )

    if ctx.purchase_agreement.contract_price is None:
        logger.warning(
            "[C-2] domain_check=pa_price_extracted | outcome=EXTRACTION_FAILED | "
            "reason=pa_price_not_extracted"
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.EXTRACTION_FAILED,
            message="Purchase agreement was present but contract price was not extracted.",
            action_item="Review the purchase agreement and confirm the contract price.",
            review_required=True,
            source_documents=["purchase_agreement"],
            compared_fields=["contract_price"],
            decision_path=["pa_present", "pa_price_not_extracted", "extraction_failed"],
        )

    if ctx.purchase_agreement.contract_date is None:
        logger.warning(
            "[C-2] domain_check=pa_date_extracted | outcome=EXTRACTION_FAILED | "
            "reason=pa_date_not_extracted"
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.EXTRACTION_FAILED,
            message=(
                "Purchase agreement was present but fully executed contract date was not extracted. "
                "The contract date must be the date of the LAST signature."
            ),
            action_item="Review the purchase agreement signatures and confirm the fully executed date.",
            review_required=True,
            source_documents=["purchase_agreement"],
            compared_fields=["date_of_contract"],
            decision_path=["pa_present", "pa_date_not_extracted", "extraction_failed"],
        )

    # ── Price comparison ──
    rpt_price = rpt.contract_price
    pa_price = ctx.purchase_agreement.contract_price

    if rpt_price != pa_price:
        logger.warning(
            "[C-2] domain_check=price_match | outcome=FAIL | "
            "report=%.2f pa=%.2f diff=%.2f",
            rpt_price, pa_price, abs(rpt_price - pa_price),
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.FAIL,
            message=(
                f"In contract section, Contract Price noted as ${rpt_price:,.2f}; "
                f"however, purchase contract shows ${pa_price:,.2f}. Please verify."
            ),
            appraisal_value=f"${rpt_price:,.2f}",
            engagement_value=f"${pa_price:,.2f}",
            details={
                "report_price": rpt_price,
                "pa_price": pa_price,
                "difference": abs(rpt_price - pa_price),
                "domain_reason": (
                    "Contract price must match the purchase agreement exactly. A discrepancy "
                    "could mean the appraiser used the wrong contract, or the OCR misread "
                    "the price. Either way, the lender cannot use a report with a wrong price."
                ),
            },
            decision_path=["price_extracted", "pa_price_found", "price_mismatch", "fail"],
        )

    # ── Date comparison ──
    if rpt.date_of_contract:
        report_date = _normalize_date(rpt.date_of_contract)
        pa_date = _normalize_date(ctx.purchase_agreement.contract_date)
        if report_date != pa_date:
            internal_dates = [d for d in _contract_dates_in_text(ctx.raw_text) if d != report_date]
            internal_note = ""
            if internal_dates:
                internal_note = (
                    f" The appraisal also references contract date(s) {', '.join(internal_dates)}, "
                    "creating an internal inconsistency."
                )
            logger.warning(
                "[C-2] domain_check=date_match | outcome=FAIL | "
                "report=%s pa=%s",
                report_date, pa_date,
            )
            return RuleResult(
                rule_id="C-2",
                rule_name="Contract Price and Date",
                status=RuleStatus.FAIL,
                message=(
                    f"Contract section shows Date of Contract as {report_date}; however, the "
                    f"purchase agreement shows the fully executed date as {pa_date}.{internal_note} "
                    f"Please revise the contract date to reflect {pa_date}. "
                    "Note: contract date = date of the LAST signature (fully executed)."
                ),
                appraisal_value=report_date,
                engagement_value=pa_date,
                details={
                    "report_date": report_date,
                    "pa_date": pa_date,
                    "domain_reason": (
                        "The contract date determines how old the deal is relative to the "
                        "appraisal date. Wrong date can trigger or suppress a required market "
                        "conditions commentary requirement."
                    ),
                },
                decision_path=["price_matched", "date_extracted", "date_mismatch", "fail"],
            )
    elif not rpt.date_of_contract:
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.EXTRACTION_FAILED,
            message="Appraisal contract date was not extracted.",
            action_item="Review the appraisal contract section and confirm Date of Contract.",
            review_required=True,
            source_documents=["appraisal"],
            compared_fields=["date_of_contract"],
            decision_path=["price_matched", "pa_date_found", "report_date_missing", "extraction_failed"],
        )

    # ── Contract age risk analysis ──
    effective_date = getattr(ctx.report, "effective_date", None)
    days_old, age_risk, requires_comment = _analyze_contract_age_risk(
        rpt.date_of_contract, effective_date
    )

    if days_old is not None:
        logger.info(
            "[C-2] domain_check=contract_age | days_old=%d risk=%s requires_comment=%s",
            days_old, age_risk, requires_comment,
        )

    if days_old is not None and days_old < 0:
        # Future contract date — likely a data entry error
        logger.warning(
            "[C-2] domain_check=contract_date_sanity | outcome=VERIFY | "
            "days_old=%d | reason=contract_date_is_in_future",
            days_old,
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.VERIFY,
            message=(
                f"Contract date ({rpt.date_of_contract}) appears to be in the future. "
                "Please verify — the contract date should be the date of the last signature."
            ),
            details={"contract_date": rpt.date_of_contract, "days_old": days_old},
            decision_path=["price_date_matched", "contract_date_future", "verify"],
        )

    if requires_comment and days_old is not None:
        logger.warning(
            "[C-2] domain_check=contract_age | outcome=VERIFY | "
            "days_old=%d | risk=%s | reason=comment_required_for_old_contract",
            days_old, age_risk,
        )
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.VERIFY,
            message=(
                f"Contract is {days_old} days old — market conditions comment is required. "
                "Per domain rules: contracts older than 120 days require an analysis of "
                "whether the market has changed since the contract was signed."
            ),
            details={
                "days_old": days_old,
                "risk_level": age_risk,
                "contract_date": rpt.date_of_contract,
                "domain_reason": (
                    "An old contract in a rising market means the agreed price may be below "
                    "current market; in a declining market, above current values. "
                    "Either way, the appraiser must explain how current market conditions "
                    "relate to the contract price."
                ),
            },
            decision_path=[
                "price_date_matched", f"contract_age={days_old}_days",
                "age_gt_120_days", "comment_required", "verify",
            ],
        )

    # ── Contract price vs appraised value triangle check ──
    appraised_value = getattr(ctx.report, "appraised_value", None)
    if appraised_value and rpt_price:
        variance_pct = abs(appraised_value - rpt_price) / rpt_price * 100

        if variance_pct > 10:
            logger.warning(
                "[C-2] domain_check=price_value_triangle | outcome=VERIFY | "
                "contract=%.2f appraised=%.2f variance=%.1f%% | risk=HIGH",
                rpt_price, appraised_value, variance_pct,
            )
            return RuleResult(
                rule_id="C-2",
                rule_name="Contract Price and Date",
                status=RuleStatus.VERIFY,
                message=(
                    f"MAJOR VALUE GAP: Contract price (${rpt_price:,.0f}) and appraised value "
                    f"(${appraised_value:,.0f}) differ by {variance_pct:.1f}%. "
                    "Escalate for senior review. Detailed reconciliation is required."
                ),
                appraisal_value=f"Contract: ${rpt_price:,.0f}",
                engagement_value=f"Appraised: ${appraised_value:,.0f}",
                review_required=True,
                details={
                    "contract_price": rpt_price,
                    "appraised_value": appraised_value,
                    "variance_pct": round(variance_pct, 1),
                    "risk_level": "HIGH",
                    "domain_reason": (
                        "The contract price triangle: contract ↔ appraised value ↔ comparables "
                        "must be reconciled. A 10%+ gap means the appraiser believes the property "
                        "is worth significantly more or less than the agreed price. "
                        "This requires a senior review and detailed appraiser reconciliation."
                    ),
                },
                decision_path=[
                    "price_date_matched",
                    f"appraised_value={appraised_value:.0f}",
                    f"contract_price={rpt_price:.0f}",
                    f"variance={variance_pct:.1f}%_gt_10%",
                    "high_risk_escalate",
                ],
            )

        if variance_pct > 3:
            logger.warning(
                "[C-2] domain_check=price_value_triangle | outcome=VERIFY | "
                "contract=%.2f appraised=%.2f variance=%.1f%% | risk=MEDIUM",
                rpt_price, appraised_value, variance_pct,
            )
            return RuleResult(
                rule_id="C-2",
                rule_name="Contract Price and Date",
                status=RuleStatus.VERIFY,
                message=(
                    f"Contract price (${rpt_price:,.0f}) and appraised value (${appraised_value:,.0f}) "
                    f"differ by {variance_pct:.1f}%. Reconciliation comment required."
                ),
                details={
                    "contract_price": rpt_price,
                    "appraised_value": appraised_value,
                    "variance_pct": round(variance_pct, 1),
                    "risk_level": "MEDIUM",
                },
                decision_path=[
                    "price_date_matched",
                    f"variance={variance_pct:.1f}%_gt_3%",
                    "medium_risk_flag",
                ],
            )

    logger.info(
        "[C-2] domain_check=contract_price_date | outcome=PASS | "
        "price=%.2f date=%s days_old=%s",
        rpt_price,
        rpt.date_of_contract,
        str(days_old) if days_old is not None else "unknown",
    )
    return RuleResult(
        rule_id="C-2",
        rule_name="Contract Price and Date",
        status=RuleStatus.PASS,
        message=(
            f"Contract Price: ${rpt_price:,.2f}, Date: {rpt.date_of_contract}. "
            f"Matches purchase agreement."
            + (f" Contract age: {days_old} days." if days_old is not None else "")
        ),
        compared_values={
            "report_price": rpt_price,
            "pa_price": pa_price,
            "report_date": rpt.date_of_contract,
            "pa_date": ctx.purchase_agreement.contract_date,
        },
        decision_path=["price_matched", "date_matched", "age_ok", "pass"],
    )


@rule(id="C-3", name="Owner of Record Data Source")
def validate_owner_record_source(ctx: ValidationContext) -> RuleResult:
    """
    Rule C-3 — Seller = Owner of Public Record
    Target Field: "Is the property seller the owner of public record?"
    Rule: Must check Yes or No with data source
    If No: Commentary MUST be provided — this is a FRAUD RISK signal

    WHY THIS MATTERS:
    If the seller is NOT the legal owner of the property, this is one of the
    most serious red flags in any real estate transaction. The lender may be
    financing a sale where the seller has no legal right to sell.

    Legitimate exceptions exist but ALL require explanation:
      - Estate sales (deceased owner, executor is selling)
      - Trust sales (trustee is seller, beneficiary is owner of record)
      - LLC sales (company owns but individual is listed)
      - Assignment contracts (investor assigned their purchase rights)

    Unexplained seller ≠ owner situations are potential fraud (e.g., flipping
    scheme where a middleman sells a property they don't yet own).

    Risk levels:
      Seller = Owner of record → LOW (standard)
      Seller ≠ Owner (explained) → MEDIUM (estate/trust/LLC — documented)
      Seller ≠ Owner (unexplained) → CRITICAL (potential fraud — HOLD)

    Rejection template: "Please provide data source for 'Is the property seller
    the owner of public record?' under contract section."
    """
    if _get_assignment_type(ctx) == "REFINANCE":
        logger.info("[C-3] assignment=REFINANCE | NOT_APPLICABLE")
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.NOT_APPLICABLE,
            message="Refinance: Owner record purchase-contract rule is not applicable.",
            decision_path=["assignment=REFINANCE", "not_applicable"],
        )

    c = ctx.report.contract

    # Checkbox not detected — VERIFY, never FAIL (per CLAUDE.md checkbox rules)
    if c.is_seller_owner is None:
        logger.warning(
            "[C-3] domain_check=seller_owner_checkbox | outcome=VERIFY | "
            "reason=checkbox_not_detected"
        )
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.VERIFY,
            message=(
                "Is Seller Owner of Public Record checkbox was not detected. "
                "Please verify manually — this is a required field."
            ),
            decision_path=["assignment=PURCHASE", "checkbox_not_found", "verify"],
        )

    # Data source always required (both Yes and No need a source)
    if not c.owner_record_data_source or len(c.owner_record_data_source.strip()) < 2:
        logger.warning(
            "[C-3] domain_check=data_source | outcome=FAIL | "
            "is_seller_owner=%s | reason=data_source_missing",
            c.is_seller_owner,
        )
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.FAIL,
            message=(
                'Please provide data source for "Is the property seller the owner of public record?" '
                "under contract section."
            ),
            decision_path=["assignment=PURCHASE", "checkbox_found", "data_source_missing", "fail"],
        )

    # Seller IS NOT the owner — CRITICAL risk, commentary required
    if c.is_seller_owner is False:
        if not c.owner_record_commentary or len(c.owner_record_commentary.strip()) < 10:
            logger.warning(
                "[C-3] domain_check=seller_not_owner | outcome=FAIL | "
                "risk=CRITICAL | reason=no_commentary_for_seller_owner_mismatch"
            )
            return RuleResult(
                rule_id="C-3",
                rule_name="Owner of Record Data Source",
                status=RuleStatus.FAIL,
                message=(
                    "CRITICAL: Seller is NOT the owner of public record, and no explanation "
                    "is provided. This is a fraud risk signal. Commentary required explaining "
                    "the relationship (estate, trust, LLC, assignment contract, etc.)."
                ),
                review_required=True,
                details={
                    "is_seller_owner": False,
                    "risk_level": "CRITICAL",
                    "domain_reason": (
                        "If the seller is not the legal owner, they may not have the right to sell. "
                        "This is a common pattern in flip schemes where a middleman assigns their "
                        "purchase contract before they have officially closed. Without explanation, "
                        "the lender cannot determine if the transaction is legitimate."
                    ),
                    "required_action": (
                        "Appraiser must explain: "
                        "(1) Who is the actual legal owner? "
                        "(2) What is the seller's legal authority to convey title? "
                        "(3) What data source was used to verify this?"
                    ),
                },
                decision_path=[
                    "assignment=PURCHASE", "checkbox=NO",
                    "data_source_present", "no_commentary", "critical_risk", "fail",
                ],
            )

        # Seller ≠ owner but commentary exists — medium risk, verify quality
        logger.warning(
            "[C-3] domain_check=seller_not_owner_commentary | outcome=VERIFY | "
            "risk=MEDIUM | reason=seller_not_owner_requires_review"
        )
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.VERIFY,
            message=(
                "Seller is not the owner of public record, but commentary is provided. "
                "Please review the commentary to ensure it adequately explains the "
                "seller's authority to convey title."
            ),
            review_required=True,
            details={
                "is_seller_owner": False,
                "risk_level": "MEDIUM",
                "commentary_preview": c.owner_record_commentary[:200],
                "domain_reason": (
                    "Commentary exists but requires human review to confirm it adequately "
                    "addresses the ownership discrepancy. Automated systems cannot verify "
                    "legal authority claims without external data sources."
                ),
            },
            decision_path=[
                "assignment=PURCHASE", "checkbox=NO",
                "data_source_present", "commentary_present",
                "medium_risk", "human_review_required",
            ],
        )

    # Seller = Owner of record — standard outcome
    logger.info(
        "[C-3] domain_check=seller_owner | outcome=PASS | "
        "is_seller_owner=True data_source='%s'",
        c.owner_record_data_source,
    )
    return RuleResult(
        rule_id="C-3",
        rule_name="Owner of Record Data Source",
        status=RuleStatus.PASS,
        message="Seller is the owner of public record. Data source provided.",
        compared_values={
            "is_seller_owner": True,
            "data_source": c.owner_record_data_source,
        },
        decision_path=["assignment=PURCHASE", "checkbox=YES", "data_source_present", "pass"],
    )


@rule(id="C-4", name="Financial Assistance")
def validate_financial_assistance(ctx: ValidationContext) -> RuleResult:
    """
    Rule C-4 — Financial Assistance / Concessions
    Target Field: Financial assistance (loan charges, sale concessions, gifts)
    Rule: Yes or No MUST be marked; if Yes → amount + description required
    Validation: Cross-check with Purchase Agreement

    WHY THIS MATTERS:
    Concessions distort the true price. The "effective" purchase price is
    the contract price minus any seller-paid concessions.

    Concession Math (domain training doc, Section 10):
      True Market Value = Contract Price − Excess Concessions
      Example: Contract=$500,000, Concession=$10,000 → Effective=$490,000

    Risk levels by concession percentage of contract price:
      > 5%  → HIGH (concessions may overstate the contract price materially)
      1–5%  → MEDIUM (normal seller-paid closing costs)
      < 1%  → LOW (minimal)

    Without disclosing concessions, the lender's LTV is wrong — they think
    they're lending on a $500,000 home but the real transaction was $490,000.

    Rejection template: "Purchase agreement shows concession as $X; however,
    report shows concession as $Y. Please verify."
    """
    if _get_assignment_type(ctx) == "REFINANCE":
        logger.info("[C-4] assignment=REFINANCE | NOT_APPLICABLE")
        return RuleResult(
            rule_id="C-4",
            rule_name="Financial Assistance",
            status=RuleStatus.NOT_APPLICABLE,
            message="Refinance: Financial assistance rule is not applicable.",
            decision_path=["assignment=REFINANCE", "not_applicable"],
        )

    c = ctx.report.contract

    # Checkbox not detected — three-state rule: None = VERIFY, not FAIL
    if c.financial_assistance is None:
        logger.warning(
            "[C-4] domain_check=concession_checkbox | outcome=VERIFY | "
            "reason=checkbox_not_detected"
        )
        return RuleResult(
            rule_id="C-4",
            rule_name="Financial Assistance",
            status=RuleStatus.VERIFY,
            message="Financial Assistance checkbox (Yes/No) not detected. Please verify manually.",
            decision_path=["assignment=PURCHASE", "checkbox_not_found", "verify"],
        )

    # No financial assistance — amount should be 0
    if c.financial_assistance is False:
        if c.financial_assistance_amount is not None and c.financial_assistance_amount > 0:
            logger.warning(
                "[C-4] domain_check=no_concession_amount | outcome=FAIL | "
                "checkbox=NO amount=%.2f | reason=no_checkbox_but_amount_present",
                c.financial_assistance_amount,
            )
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.FAIL,
                message=(
                    f"Financial Assistance is marked 'No', but amount shows "
                    f"${c.financial_assistance_amount:,.2f}. Please verify and reconcile."
                ),
                appraisal_value=f"${c.financial_assistance_amount:,.2f}",
                expected_value="$0 (checkbox=No)",
                decision_path=["checkbox=NO", "amount_gt_zero", "contradiction", "fail"],
            )

    # Financial assistance = YES
    if c.financial_assistance is True:
        # Check for $0 closing costs evidence in raw text (valid: yes checkbox + $0 amount)
        if re.search(
            r"\$\s*0(?:\.00)?\s*;{1,2}\s*closing\s+costs|\bclosing\s+costs\b.{0,40}\$\s*0(?:\.00)?",
            ctx.raw_text or "", re.I
        ):
            logger.info(
                "[C-4] domain_check=concession_zero | outcome=PASS | "
                "evidence=$0_closing_costs"
            )
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.PASS,
                message="Report text indicates $0 closing-cost concessions/financial assistance.",
                details={"checkbox_extracted_as": "Yes", "amount_evidence": "$0 closing costs"},
                decision_path=["checkbox=YES", "zero_amount_in_text", "pass"],
            )

        # PA and report both show $0 — legitimate
        if ctx.purchase_agreement and ctx.purchase_agreement.concessions_amount is not None:
            pa_amt = ctx.purchase_agreement.concessions_amount
            rpt_amt = c.financial_assistance_amount or 0
            if abs(pa_amt) <= 0.01 and abs(rpt_amt) <= 0.01:
                logger.info(
                    "[C-4] domain_check=pa_concession_match | outcome=PASS | "
                    "pa=%.2f report=%.2f both_zero",
                    pa_amt, rpt_amt,
                )
                return RuleResult(
                    rule_id="C-4",
                    rule_name="Financial Assistance",
                    status=RuleStatus.PASS,
                    message="PA and report both indicate $0 financial assistance/concessions.",
                    compared_values={"pa_amount": pa_amt, "report_amount": rpt_amt},
                    decision_path=["checkbox=YES", "pa_zero", "report_zero", "pass"],
                )

        # Yes checkbox + no amount → VERIFY
        if c.financial_assistance_amount is None or c.financial_assistance_amount <= 0:
            logger.warning(
                "[C-4] domain_check=concession_amount | outcome=VERIFY | "
                "reason=yes_checkbox_no_amount"
            )
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.VERIFY,
                message="Financial Assistance is marked 'Yes', but no dollar amount is specified.",
                decision_path=["checkbox=YES", "amount_missing", "verify"],
            )

        # Amount exists but no description
        if not c.financial_assistance_description or len(c.financial_assistance_description.strip()) < 5:
            logger.warning(
                "[C-4] domain_check=concession_description | outcome=VERIFY | "
                "amount=%.2f | reason=description_missing",
                c.financial_assistance_amount,
            )
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.VERIFY,
                message=(
                    f"Financial assistance amount (${c.financial_assistance_amount:,.2f}) is noted, "
                    "but description of items is missing or incomplete. "
                    "Per Rule C-4: total dollar amount AND description are required."
                ),
                details={"amount": c.financial_assistance_amount},
                decision_path=["checkbox=YES", "amount_present", "description_missing", "verify"],
            )

        # ── Concession percentage risk check ──
        rpt_price = ctx.report.contract.contract_price
        concession_amt = c.financial_assistance_amount
        risk_level, concession_pct, explanation = _analyze_concession_risk(
            concession_amt, rpt_price
        )

        logger.info(
            "[C-4] domain_check=concession_risk | amount=%.2f pct=%.1f%% risk=%s",
            concession_amt, concession_pct, risk_level,
        )

        if risk_level == "HIGH":
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.VERIFY,
                message=(
                    f"HIGH CONCESSION RISK: {explanation} "
                    "Appraiser must address the net impact of concessions on market value. "
                    "Concessions > 5% of contract price may overstate the effective transaction price."
                ),
                details={
                    "concession_amount": concession_amt,
                    "contract_price": rpt_price,
                    "concession_pct": round(concession_pct, 1),
                    "risk_level": risk_level,
                    "domain_reason": (
                        "Excessive concessions inflate the stated transaction price above what "
                        "the buyer actually paid in net economic terms. The appraiser's value "
                        "conclusion must reflect market value net of non-market concessions."
                    ),
                },
                decision_path=[
                    "checkbox=YES", "amount_present", "description_present",
                    f"concession_pct={concession_pct:.1f}%_gt_5%",
                    "high_risk_concession", "verify",
                ],
            )

    # Cross-check with Purchase Agreement
    if ctx.purchase_agreement and ctx.purchase_agreement.concessions_amount is not None:
        pa_amt = ctx.purchase_agreement.concessions_amount
        rpt_amt = c.financial_assistance_amount or 0
        if abs(pa_amt - rpt_amt) > 0.01:
            logger.warning(
                "[C-4] domain_check=pa_concession_match | outcome=FAIL | "
                "pa=%.2f report=%.2f diff=%.2f",
                pa_amt, rpt_amt, abs(pa_amt - rpt_amt),
            )
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.FAIL,
                message=(
                    f"Purchase agreement shows concession as ${pa_amt:,.2f}; however, "
                    f"report shows concession as ${rpt_amt:,.2f}. Please verify."
                ),
                appraisal_value=f"${rpt_amt:,.2f}",
                engagement_value=f"${pa_amt:,.2f}",
                details={
                    "pa_amount": pa_amt,
                    "report_amount": rpt_amt,
                    "domain_reason": (
                        "The concession amount must match the purchase agreement exactly. "
                        "The PA is the authoritative source for what the seller agreed to pay."
                    ),
                },
                decision_path=[
                    "checkbox=YES", "amounts_present",
                    "pa_report_concession_mismatch", "fail",
                ],
            )

    logger.info(
        "[C-4] domain_check=financial_assistance | outcome=PASS | "
        "checkbox=%s amount=%s",
        c.financial_assistance,
        f"${c.financial_assistance_amount:,.2f}" if c.financial_assistance_amount else "$0",
    )
    return RuleResult(
        rule_id="C-4",
        rule_name="Financial Assistance",
        status=RuleStatus.PASS,
        message="Financial assistance information is consistent.",
        compared_values={
            "checkbox": c.financial_assistance,
            "amount": c.financial_assistance_amount,
        },
        decision_path=["checkbox_present", "amounts_consistent", "pass"],
    )


@rule(id="C-5", name="Personal Property Analysis")
def validate_personal_property(ctx: ValidationContext) -> RuleResult:
    """
    Rule C-5 — Personal Property Analysis
    Target: Contract + Concession Commentary
    Rule: All personal property from PA must be identified in commentary
    Requirement: State explicitly whether each item contributes to value

    WHY THIS MATTERS:
    Personal property (appliances, furniture, riding mower) is NOT real
    property — it does not contribute to the appraised value of the real
    estate. When a seller includes a $10,000 riding mower as part of a deal,
    the buyer might be paying $10,000 above market value for the house.

    The appraiser must:
    1. Identify ALL personal property items from the contract
    2. State whether each contributes to real property value
    3. If yes → explain how the value was allocated

    This protects the lender from inflated collateral values where personal
    property is included in the "real estate" value.
    """
    if _get_assignment_type(ctx) == "REFINANCE":
        logger.info("[C-5] assignment=REFINANCE | NOT_APPLICABLE")
        return RuleResult(
            rule_id="C-5",
            rule_name="Personal Property Analysis",
            status=RuleStatus.NOT_APPLICABLE,
            message="Refinance: Personal property rule is not applicable.",
            decision_path=["assignment=REFINANCE", "not_applicable"],
        )

    # Check Purchase Agreement for personal property items
    if ctx.purchase_agreement and ctx.purchase_agreement.personal_property_items:
        pa_items = _filter_personal_property_items(ctx.purchase_agreement.personal_property_items)

        if pa_items:
            comment = ctx.report.contract.sales_concessions_comment or ""

            # No commentary at all
            if len(comment.strip()) < 10:
                logger.warning(
                    "[C-5] domain_check=personal_property_commentary | outcome=FAIL | "
                    "pa_items=%s | reason=no_commentary",
                    pa_items,
                )
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.FAIL,
                    message=(
                        f"Purchase Agreement indicates personal property items "
                        f"({', '.join(pa_items)}), but report commentary is missing or incomplete. "
                        "Per Rule C-5: all personal property items must be identified and their "
                        "value contribution must be stated."
                    ),
                    details={
                        "pa_items": pa_items,
                        "domain_reason": (
                            "Personal property must be separated from real property value. "
                            "A $10,000 appliance package included in a $400,000 deal means "
                            "the real estate was only worth $390,000 — a $10,000 lender exposure."
                        ),
                    },
                    decision_path=["pa_items_found", "no_commentary", "fail"],
                )

            # Check if PA items are mentioned in commentary
            comment_upper = comment.upper()
            missing_items = [item for item in pa_items if item.upper() not in comment_upper]

            if missing_items:
                logger.warning(
                    "[C-5] domain_check=personal_property_mentioned | outcome=VERIFY | "
                    "missing_items=%s",
                    missing_items,
                )
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.VERIFY,
                    message=(
                        f"Personal property items from contract may not be fully addressed: "
                        f"{', '.join(missing_items)}. Please confirm all items are addressed "
                        "in the concession commentary."
                    ),
                    details={"missing_items": missing_items, "all_pa_items": pa_items},
                    decision_path=["pa_items_found", "commentary_present", "items_not_mentioned", "verify"],
                )

            # Check for explicit "contribute to value" statement (most critical element)
            contributes_keywords = [
                "CONTRIBUTE", "CONTRIBUTORY VALUE", "NO VALUE", "NO CONTRIBUTORY",
                "VALUE CONTRIBUTION", "PERSONAL PROPERTY VALUE",
            ]
            has_contribution_statement = any(k in comment_upper for k in contributes_keywords)

            if not has_contribution_statement:
                logger.warning(
                    "[C-5] domain_check=contribution_statement | outcome=VERIFY | "
                    "reason=no_contribution_statement"
                )
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.VERIFY,
                    message=(
                        "Personal property items are mentioned but the commentary does not "
                        "explicitly state whether they contribute to the appraised value. "
                        "Please add a statement such as: "
                        "'The included [items] are personal property and do not contribute to "
                        "the appraised value of the real estate.'"
                    ),
                    details={
                        "pa_items": pa_items,
                        "domain_reason": (
                            "An implicit 'no contribution' is not sufficient. The appraiser must "
                            "explicitly state that personal property value is excluded from the "
                            "appraised value so the lender's collateral valuation is clear."
                        ),
                    },
                    decision_path=[
                        "pa_items_found", "commentary_present",
                        "items_mentioned", "contribution_statement_missing", "verify",
                    ],
                )

    # Check if report's own personal property items need a contribution statement
    report_items = _filter_personal_property_items(ctx.report.contract.personal_property_items)
    if report_items:
        if ctx.report.contract.personal_property_contributes_to_value is None:
            logger.warning(
                "[C-5] domain_check=report_pp_contribution | outcome=VERIFY | "
                "items=%s | reason=contribution_not_stated",
                report_items,
            )
            return RuleResult(
                rule_id="C-5",
                rule_name="Personal Property Analysis",
                status=RuleStatus.VERIFY,
                message=(
                    f"Personal property items are listed ({', '.join(report_items)}). "
                    "Please explicitly state whether they contribute to the appraised value."
                ),
                details={"report_items": report_items},
                decision_path=["report_pp_items_present", "contribution_not_stated", "verify"],
            )

    logger.info("[C-5] domain_check=personal_property | outcome=PASS")
    return RuleResult(
        rule_id="C-5",
        rule_name="Personal Property Analysis",
        status=RuleStatus.PASS,
        message="Personal property analysis is complete.",
        decision_path=["pa_items_checked", "commentary_adequate", "contribution_stated", "pass"],
    )


# ── Private helpers ─────────────────────────────────────────────────────────────

def _get_assignment_type(ctx: ValidationContext) -> str:
    """
    Derive assignment type from engagement letter or report contract section.
    Returns uppercase string ("PURCHASE", "REFINANCE", "OTHER", "").
    """
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type:
        return ctx.engagement_letter.assignment_type.strip().upper()
    if ctx.report.contract.assignment_type:
        return ctx.report.contract.assignment_type.strip().upper()
    return ""
