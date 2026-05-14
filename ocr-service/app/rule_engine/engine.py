"""
Rule Engine — Phase 3 upgrade.

Improvements over previous version:
  - Rules execute in DB-configured order (structural → logic → commentary)
  - Inactive/non-applicable rules are explicit non-scoring outcomes, never PASS
  - Severity (BLOCKING / STANDARD / ADVISORY) attached to every result
  - source_page and field_confidence passed from Phase 2 field_meta
  - Single rule crash never stops other rules
"""

import logging
import re
import traceback
from typing import List, Callable, Dict, Optional

from app.models.appraisal import ValidationContext
from app.rule_engine.smart_identifier import (
    SmartLogger, RuleResult, RuleStatus, RuleSeverity, DataMissingException
)

logger = logging.getLogger(__name__)


def _engagement_missing(context: ValidationContext) -> bool:
    missing = {str(v).upper() for v in (context.missing_supporting_documents or [])}
    return bool(context.supporting_document_missing or "ENGAGEMENT" in missing or context.engagement_letter is None)


class RuleEngine:
    """Orchestrates registered rules against a ValidationContext."""

    def __init__(self):
        self._rules: Dict[str, Callable] = {}   # rule_id → function
        self.logger = SmartLogger()

    def register_rule(self, rule_func: Callable):
        rule_id = getattr(rule_func, "rule_id", rule_func.__name__)
        self._rules[rule_id] = rule_func
        return rule_func

    def execute(self, context: ValidationContext) -> List[RuleResult]:
        """
        Execute all active rules in DB-configured order.

        Execution order (Phase 3):
          1. Structural rules  (S-1–S-6, C-1–C-3)  — simple field comparisons
          2. Logic rules       (S-7–S-12, C-4–C-5)  — multi-field checks
          3. Narrative rules   (N-1–N-7)             — LLM commentary analysis
        """
        from app.rule_engine.rules_db import load_rule_configs

        self.logger = SmartLogger()
        results: List[RuleResult] = []

        # Load DB config (is_active, severity, order) — graceful fallback to defaults
        configs = load_rule_configs()

        # Sort by execution_order; rules not in DB config run last
        def sort_key(rule_id: str) -> int:
            cfg = configs.get(rule_id)
            return cfg.execution_order if cfg else 999

        ordered_ids = sorted(self._rules.keys(), key=sort_key)

        for rule_id in ordered_ids:
            rule_func = self._rules[rule_id]
            cfg = configs.get(rule_id)

            if cfg and not cfg.is_active:
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.NOT_EXECUTED,
                    message="Rule disabled via configuration; it was not executed and does not count as PASS.",
                    severity=RuleSeverity(cfg.severity) if cfg else RuleSeverity.STANDARD,
                    review_required=False,
                    decision_path=["rule_config_loaded", "rule_inactive", "not_counted_as_pass"],
                )
                results.append(res)
                self.logger.log_result(res)
                continue

            if cfg and not self._is_applicable(context, cfg.applicable_loan_types):
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.NOT_APPLICABLE,
                    message=f"Rule not applicable for this assignment/loan type ({cfg.applicable_loan_types}); it was not counted as PASS.",
                    severity=RuleSeverity(cfg.severity),
                    review_required=False,
                    decision_path=["rule_config_loaded", "applicability_check_false", "not_counted_as_pass"],
                )
                results.append(res)
                self.logger.log_result(res)
                continue

            try:
                result = rule_func(context)

                # Attach Phase 3 metadata if not set by the rule itself
                if cfg:
                    if result.severity == RuleSeverity.STANDARD:
                        result.severity = RuleSeverity(cfg.severity)
                self._attach_location_meta(context, rule_id, result)
                self._enforce_pass_evidence_contract(context, rule_id, result)
                self._complete_rule_outcome(result)

                results.append(result)
                self.logger.log_result(result)

            except DataMissingException as e:
                missing_field_name = str(e.field_name or "")
                missing_external_source = bool(re.search(
                    r"\b(engagement|order|contract|purchase agreement|client engagement letter)\b",
                    missing_field_name,
                    re.I,
                ))
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.EXTRACTION_FAILED,
                    message=f"Required evidence missing: {e.field_name}.",
                    details={"field": e.field_name},
                    action_item=f"Review required: extract or confirm field '{e.field_name}' before this rule can pass.",
                    review_required=True,
                    severity=RuleSeverity(cfg.severity) if cfg else RuleSeverity.STANDARD,
                    decision_path=["rule_started", "required_field_missing", "escalated_to_review"],
                    stage="rule_engine",
                    retry_eligible=True,
                )
                res.target_field = self._normalize_field_name(e.field_name)
                if missing_external_source:
                    res.confidence = 0.0
                    res.field_confidence = 0.0
                    res.source_page = None
                    res.evidence = []
                    res.decision_path.append("external_expected_value_missing")
                else:
                    self._attach_location_meta(context, rule_id, res, field_hint=e.field_name)
                self._complete_rule_outcome(res)
                results.append(res)
                self.logger.log_result(res)

            except Exception as e:
                logger.exception("Rule %s crashed: %s", rule_id, e)
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.SYSTEM_ERROR,
                    message=f"Runtime error: {str(e)}",
                    action_item="Report this to the development team.",
                    review_required=True,
                    exception_type=e.__class__.__name__,
                    exception_trace=traceback.format_exc(),
                    stage="rule_engine",
                    retry_eligible=True,
                    decision_path=["rule_started", "exception_raised", "system_error_escalated_to_review"],
                )
                self._attach_location_meta(context, rule_id, res)
                self._complete_rule_outcome(res)
                results.append(res)
                self.logger.log_result(res)

        return results

    def _complete_rule_outcome(self, result: RuleResult):
        """
        Populate derived fields on a RuleResult before it is stored.

        Confidence propagation order (first non-None value wins):
          result.confidence  →  already set by the rule itself
          result.field_confidence  →  set by _attach_location_meta from field_meta
        Storing 0.0 is valid (genuinely unknown).  The important fix is that
        field_confidence is never left as None when it can be derived, because
        a None confidence on the Java side surfaces as 0 in the metrics, which
        incorrectly inflates the low-confidence field count.
        """
        if result.confidence is None and result.field_confidence is not None:
            result.confidence = result.field_confidence
        # Ensure confidence is always a float so Java does not receive null
        if result.confidence is None:
            result.confidence = 0.0
        if result.field_confidence is None:
            result.field_confidence = result.confidence or 0.0

        if result.extracted_value is None and result.appraisal_value is not None:
            result.extracted_value = result.appraisal_value
        if result.expected_value is None and result.engagement_value is not None:
            result.expected_value = result.engagement_value

        evidence = result.evidence or []
        if result.source_page and not evidence:
            evidence = [f"Appraisal page {result.source_page}"]
        result.evidence = evidence

        if result.status == RuleStatus.REVIEW and not result.verify_question:
            result.verify_question = self._generate_verify_question(result)
            result.action_item = result.verify_question or result.action_item
            result.review_required = True
        if result.status == RuleStatus.FAIL and not result.rejection_text:
            result.rejection_text = result.message
            result.review_required = True
        if result.status in {
            RuleStatus.EXTRACTION_FAILED,
            RuleStatus.OCR_LOW_CONFIDENCE,
            RuleStatus.SYSTEM_ERROR,
            RuleStatus.SOURCE_MISSING,
            RuleStatus.CROSS_DOC_MISMATCH,
        }:
            result.review_required = True
            if not result.verify_question:
                result.verify_question = result.action_item or result.message

    def _enforce_pass_evidence_contract(
        self,
        context: ValidationContext,
        rule_id: str,
        result: RuleResult,
    ) -> None:
        """A PASS must prove execution, source evidence, and sufficient confidence."""
        if result.status != RuleStatus.PASS:
            return

        result.decision_path.append("rule_returned_pass")

        if self._requires_engagement(rule_id) and _engagement_missing(context):
            self._downgrade_pass(
                result,
                RuleStatus.SOURCE_MISSING,
                "Required engagement/order evidence is missing; rule cannot PASS.",
                "Upload the engagement/order document and rerun QC.",
            )
            return

        if self._requires_purchase_agreement(rule_id, context) and context.purchase_agreement is None:
            self._downgrade_pass(
                result,
                RuleStatus.SOURCE_MISSING,
                "Purchase agreement evidence is missing or unreadable; rule cannot PASS.",
                "Upload a readable purchase agreement and rerun QC.",
            )
            return

        field_conf, _, field_meta = self._extract_meta(context, rule_id, result)
        if field_meta is not None:
            raw_status = getattr(field_meta, "extraction_status", "") or ""
            status = str(getattr(raw_status, "value", raw_status) or "").upper()
            if status and status != "FOUND":
                self._downgrade_pass(
                    result,
                    RuleStatus.EXTRACTION_FAILED,
                    f"Rule consumed field '{getattr(field_meta, 'field_name', result.target_field)}' with extraction status {status}; PASS is not allowed.",
                    "Review the extracted field and source snippet before accepting this rule.",
                )
                return

        confidence = result.confidence if result.confidence is not None else field_conf

        # Tiered confidence threshold based on how the value was extracted.
        # Spatial anchoring (word-level bounding boxes) is the most reliable method,
        # so it gets a lower threshold.  Fallback regex methods need a higher bar
        # because they are more susceptible to OCR noise and row-flattening artifacts.
        #
        # Threshold table (same scale as Python confidence: 0.0–1.0):
        #   spatial_anchor  → 0.75  (bbox-verified hit on a known word position)
        #   regex_primary   → 0.80  (first-choice pattern with a strong label anchor)
        #   regex_fallback  → 0.85  (secondary pattern — stricter gate)
        #   context_fallback / anything else → 0.87  (weakest extraction method)
        #
        # If no extraction method is recorded (field_meta absent), default to 0.85.
        _extraction_method = None
        if field_meta is not None:
            _extraction_method = getattr(field_meta, "extraction_method", None)

        _thresholds = {
            "spatial_anchor":   0.75,
            "regex_primary":    0.80,
            "regex_fallback":   0.85,
            "context_fallback": 0.87,
            "total_value_stream": 0.82,
        }
        _pass_threshold = _thresholds.get(str(_extraction_method or ""), 0.85)

        if confidence is not None and confidence < _pass_threshold:
            self._downgrade_pass(
                result,
                RuleStatus.OCR_LOW_CONFIDENCE,
                (
                    f"Rule returned PASS with confidence {confidence:.2f}, below the "
                    f"{_pass_threshold:.2f} threshold for extraction method "
                    f"'{_extraction_method or 'unknown'}'."
                ),
                "Review the source evidence because confidence is below the PASS threshold.",
            )
            return

        has_comparison = (
            result.compared_values is not None
            or result.extracted_value is not None
            or result.expected_value is not None
            or result.appraisal_value is not None
            or result.engagement_value is not None
            or bool(result.compared_fields)
        )
        has_evidence = bool(result.evidence or result.source_page or result.source_documents)
        if not has_evidence and not has_comparison:
            self._downgrade_pass(
                result,
                RuleStatus.REVIEW,
                "Rule returned PASS without source evidence or compared values.",
                "Review required because the PASS outcome is not evidence-backed.",
            )
            return

        # P3.5 — Auto-pass calibration model check.
        # Before downgrading to REVIEW, consult the trained model.  If the model
        # is confident this rule can auto-pass (P(accepted) >= 0.80) AND the rule
        # does not have a high historical rejection rate, allow the PASS through.
        # On cold start (no model), predict_auto_pass returns None and we fall
        # through to the structured-pass gate unchanged.
        if self._requires_structured_pass(rule_id) and not self._has_structured_pass(result):
            loan_type = None
            try:
                from app.services.auto_pass_calibration import predict_auto_pass
                ctx_engagement = getattr(context, "engagement_letter", None)
                loan_type = getattr(ctx_engagement, "loan_type", None) if ctx_engagement else None
                ml_decision = predict_auto_pass(
                    rule_id=rule_id,
                    extraction_method=getattr(field_meta, "extraction_method", None) if field_meta is not None else None,
                    confidence=result.confidence,
                    source_page=result.source_page,
                    bbox_x=result.bbox_x,
                    has_compared_values=bool(result.compared_values),
                    has_extracted_value=result.extracted_value is not None,
                    loan_type=loan_type,
                    details=result.details,
                )
            except Exception:
                ml_decision = None

            if ml_decision is True:
                result.decision_path.append("auto_pass_model_accepted")
                result.decision_path.append("pass_evidence_contract_satisfied")
                return
            elif ml_decision is False:
                result.decision_path.append("auto_pass_model_rejected")

            # Fall through to standard structured-pass gate (ml_decision is None or False)
            self._downgrade_pass(
                result,
                RuleStatus.REVIEW,
                "Rule returned PASS from weak text/image evidence only; structured validation evidence is required before PASS.",
                "Reviewer confirmation required until this rule produces structured fields, compared values, or explicit validation lineage.",
            )
            return

        result.decision_path.append("pass_evidence_contract_satisfied")

    def _downgrade_pass(
        self,
        result: RuleResult,
        status: RuleStatus,
        message: str,
        action_item: str,
    ) -> None:
        result.details = {
            **(result.details or {}),
            "original_status": "pass",
            "pass_blocked_reason": message,
        }
        result.status = status
        result.message = message
        result.action_item = action_item
        result.review_required = status != RuleStatus.NOT_APPLICABLE
        result.decision_path.append(f"pass_blocked:{status.value}")

    def _requires_engagement(self, rule_id: str) -> bool:
        return rule_id in {"S-1", "S-2", "S-10", "XF-4"}

    def _requires_purchase_agreement(self, rule_id: str, context: ValidationContext) -> bool:
        if rule_id not in {"C-2", "C-4", "C-5"}:
            return False
        return self._assignment(context) == "PURCHASE"

    def _requires_structured_pass(self, rule_id: str) -> bool:
        """Rule families where raw text/page presence is reviewer-assist only."""
        family = (rule_id or "").split("-", 1)[0].upper()
        return family in {
            "N", "ST", "I",
            "SCA", "R", "CA", "IA",
            "ADD", "COM",
            "PH", "M", "SK",
            "DOC", "SIG",
            "FHA", "USDA", "MF",
        }

    def _has_structured_pass(self, result: RuleResult) -> bool:
        details = result.details or {}

        # Level 1: full structured validation (cross-document comparison, field extraction)
        if details.get("structured_validation") is True:
            return True
        if details.get("extraction_based_validation") is True:
            return True
        if result.compared_values is not None or result.compared_fields:
            return True
        if result.extracted_value is not None and result.expected_value is not None:
            return True

        # Level 2: presence validation.
        # Rules that check WHETHER something exists in the PDF (photos present,
        # sketch page present, signature detected, maps section found, addenda
        # present) are PRESENCE rules.  They cannot produce "compared values"
        # because there is no reference document to compare against — the
        # question is binary (found / not found).
        # Rules signal this by setting details["presence_validated"] = True in
        # their PASS return.  This exempts them from the structured-evidence
        # requirement while still requiring an explicit evidence flag rather than
        # allowing a bare PASS with no details at all.
        if details.get("presence_validated") is True:
            return True

        return False

    def _assignment(self, context: ValidationContext) -> str:
        engagement = context.engagement_letter
        return (
            getattr(engagement, "assignment_type", None)
            or getattr(context.report.contract, "assignment_type", None)
            or ""
        ).strip().upper()

    def _generate_verify_question(self, result: RuleResult) -> str:
        fallback = result.action_item or result.message
        if result.extracted_value is None and result.expected_value is None:
            return fallback
        try:
            from app.services.ollama_service import generate_verify_question
            question = generate_verify_question(
                rule_description=f"{result.rule_id} {result.rule_name}",
                field_name=result.rule_name,
                extracted_value=result.extracted_value,
                expected_value=result.expected_value,
                confidence=result.confidence or 0.0,
                evidence=", ".join(result.evidence or []),
            )
            return question or fallback
        except Exception:
            return fallback

    def _attach_location_meta(
        self,
        context: ValidationContext,
        rule_id: str,
        result: RuleResult,
        field_hint: Optional[str] = None,
    ):
        """Attach the most specific known field location to a rule result."""
        field_conf, src_page, field_meta = self._extract_meta(context, rule_id, result, field_hint)

        if result.source_page is None and src_page:
            result.source_page = src_page
        if field_meta and result.bbox_x is None:
            result.bbox_x = getattr(field_meta, "bbox_x", None)
            result.bbox_y = getattr(field_meta, "bbox_y", None)
            result.bbox_w = getattr(field_meta, "bbox_w", None)
            result.bbox_h = getattr(field_meta, "bbox_h", None)
        if result.source_page is None:
            inferred_page = self._infer_source_page(context, rule_id, result)
            if inferred_page:
                result.source_page = inferred_page
        if result.field_confidence is None and field_conf is not None:
            result.field_confidence = field_conf

    def _extract_meta(
        self,
        context: ValidationContext,
        rule_id: str,
        result: Optional[RuleResult] = None,
        field_hint: Optional[str] = None,
    ):
        """
        Look up source_page and field_confidence from Phase 2 field_meta
        based on which fields a rule is likely to use.
        """
        # Map rule_id → primary field name in field_meta
        RULE_FIELD_MAP = {
            "S-1":  "property_address",  "S-2":  "borrower_name",
            "S-3":  "owner_of_public_record", "S-4": "legal_description",
            "S-5":  "neighborhood_name", "S-6":  "census_tract",
            "S-7":  "occupant_status",   "S-8":  "special_assessments",
            "S-9":  "hoa_dues",          "S-10": "lender_name",
            "S-11": "property_rights",   "S-12": "offered_for_sale_12mo",
            "C-1":  "contract_analyzed", "C-2":  "contract_price", "C-3":  "owner_of_public_record",
            "C-4":  "financial_assistance", "C-5":  "personal_property",
            "N-1":  "neighborhood_description",
            "N-2":  "market_conditions_commentary",
            "N-3":  "one_unit_housing_price_low", "N-4": "present_land_use_total",
            "N-5":  "neighborhood_boundaries", "N-6": "neighborhood_description",
            "N-7":  "market_conditions_commentary",
            "ST-1": "site_dimensions", "ST-2": "site_area", "ST-3": "site_shape",
            "ST-4": "view", "ST-5": "zoning_classification", "ST-6": "highest_best_use",
            "ST-7": "utilities", "ST-8": "flood_hazard", "ST-9": "utilities_typical",
            "I-1":  "effective_age", "I-3": "roof_surface", "I-5": "utilities",
            "I-7":  "gla", "SCA-1": "comparable_market_summary",
            "SCA-2": "comparable_count", "SCA-5": "comparable_data_sources",
            "PH-1": "subject_photos", "PH-4": "fha_photo_requirements",
            "SK-1": "sketch_floor_plan", "FHA-2": "fha_case_number",
            "FHA-3": "fha_intended_use", "COM-2": "market_conditions_commentary",
            "COM-3": "comparable_selection_commentary",
            "COM-4": "sales_comparison_commentary",
            "COM-5": "reconciliation_commentary",
            "COM-7": "offered_for_sale_12mo",
        }

        target_field = (
            self._normalize_field_name(field_hint)
            or self._normalize_field_name(getattr(result, "target_field", None))
            or self._normalize_field_name((getattr(result, "details", None) or {}).get("target_field") if result else None)
            or self._normalize_field_name((getattr(result, "details", None) or {}).get("failed_field") if result else None)
            or self._normalize_field_name((getattr(result, "details", None) or {}).get("field") if result else None)
        )

        if not context.field_meta:
            return None, None, None

        field_candidates = []
        if target_field:
            field_candidates.append(target_field)
        default_field = RULE_FIELD_MAP.get(rule_id)
        if default_field and default_field not in field_candidates:
            field_candidates.append(default_field)

        for field_name in field_candidates:
            meta = context.field_meta.get(field_name)
            if meta and hasattr(meta, "effective_confidence"):
                return meta.effective_confidence, meta.source_page, meta

        return None, None, None

    def _normalize_field_name(self, value: Optional[str]) -> Optional[str]:
        """Translate rule-language field labels into Phase 2 field_meta keys."""
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None

        key = re.sub(r"\([^)]*\)", "", raw).strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        aliases = {
            "property_address": "property_address",
            "property_address_report": "property_address",
            "address": "property_address",
            "street": "property_address",
            "city": "city",
            "state": "state",
            "zip": "zip_code",
            "zip_code": "zip_code",
            "county": "county",
            "client_engagement_letter": None,
            "property_address_engagement_letter": None,
            "borrower": "borrower_name",
            "borrower_name": "borrower_name",
            "borrower_name_report": "borrower_name",
            "owner_of_public_record": "owner_of_public_record",
            "legal_description": "legal_description",
            "assessors_parcel_number": "assessors_parcel_number",
            "apn": "assessors_parcel_number",
            "tax_year": "tax_year",
            "real_estate_taxes": "real_estate_taxes",
            "special_assessments": "special_assessments",
            "hoa_dues": "hoa_dues",
            "pud": "is_pud_checked",
            "pud_checkbox": "is_pud_checked",
            "lender_name": "lender_name",
            "lender_name_report": "lender_name",
            "lender_address": "lender_address",
            "property_rights": "property_rights",
            "property_rights_appraised": "property_rights",
            "prior_sale_offered_status": "offered_for_sale_12mo",
            "prior_sale_offered_12mo": "offered_for_sale_12mo",
            "data_sources": "data_source",
            "data_source": "data_source",
        }
        return aliases.get(key, key)

    def _is_applicable(self, context: ValidationContext, applicable_loan_types: str) -> bool:
        tokens = {
            token.strip().upper()
            for token in (applicable_loan_types or "ALL").split(",")
            if token.strip()
        }
        if not tokens or "ALL" in tokens:
            return True

        engagement = context.engagement_letter
        assignment = (
            getattr(engagement, "assignment_type", None)
            or getattr(context.report.contract, "assignment_type", None)
            or ""
        ).strip().upper()
        loan_type = (getattr(engagement, "loan_type", None) or "").strip().upper()

        active = {assignment, loan_type}
        if assignment == "PURCHASE":
            active.add("PURCHASE")
        if assignment == "REFINANCE":
            active.add("REFINANCE")

        return bool(tokens & active)

    # UAD 1004 form has a predictable page layout.  When OCR search fails to locate
    # a specific term, fall back to the section's canonical page range so the reviewer
    # is navigated to approximately the right area instead of page 0 (top of document).
    # These are first-page estimates; multi-page sections land on the starting page.
    _SECTION_DEFAULT_PAGES: Dict[str, int] = {
        "S":    1,   # Subject section — always starts on page 1
        "C":    1,   # Contract section — page 1 (lower half of UAD form page 1)
        "N":    1,   # Neighborhood section — page 1 (right column of UAD form)
        "ST":   1,   # Site section — page 1 (bottom portion)
        "I":    2,   # Improvements section — page 2 or 3 depending on form length
        "SCA":  3,   # Sales Comparison Approach — pages 3-5
        "R":    4,   # Reconciliation — page 4 (bottom of SCA page)
        "CA":   4,   # Cost Approach — page 4 (right half)
        "IA":   4,   # Income Approach — page 4 (right half, below Cost)
        "ADD":  5,   # Addendum starts on page 5+
        "COM":  2,   # Commentary in Neighborhood/Addendum area
        "PH":   7,   # Photographs section
        "SK":   9,   # Sketch / floor plan
        "M":    10,  # Maps section
        "DOC":  6,   # Documentation / certification page
        "SIG":  6,   # Signature page — UAD certification
        "MF":   1,   # Multi-family — same first page
        "FHA":  1,   # FHA requirements — start on page 1
        "USDA": 1,
        "XF":   1,   # Cross-field rules map to their primary field's page
    }

    def _infer_source_page(self, context: ValidationContext, rule_id: str, result: RuleResult):
        """
        Best-effort page fallback for rules whose primary field has no extracted page.

        Resolution order (most → least precise):
          1. Search page_index for rule-specific anchor terms.
          2. DocumentSectionMap (doc_section_map) — actual section page from the document.
          3. Static section default table (_SECTION_DEFAULT_PAGES) — canonical UAD pages.
        """
        page_index = context.page_index or {}

        # Step 1: anchor term text search
        if page_index:
            for term in self._rule_search_terms(rule_id, result):
                term_l = term.lower().strip()
                if not term_l:
                    continue
                for page_num in sorted(page_index.keys()):
                    if term_l in (page_index.get(page_num) or "").lower():
                        return page_num

        # Step 2: DocumentSectionMap — per-document section location
        # Map rule_id prefix to section key names used by DocumentSectionMap
        PREFIX_TO_SECTION = {
            "S":   "subject",    "C":   "contract",   "N":   "neighborhood",
            "ST":  "site",       "I":   "improvements","SCA": "sales_comparison",
            "R":   "reconciliation","CA":"cost_approach","IA": "income_approach",
            "ADD": "addendum",   "COM": "addendum",    "SIG": "signature",
            "PH":  "photos",     "SK":  "sketch",      "M":   "maps",
            "DOC": "signature",  "MF":  "subject",     "XF":  "subject",
            "FHA": "subject",    "USDA":"subject",
        }
        section_prefix = (rule_id or "").split("-", 1)[0].upper()
        doc_map = getattr(context, "doc_section_map", None)
        if doc_map:
            section_key = PREFIX_TO_SECTION.get(section_prefix)
            if section_key:
                location = doc_map.locate(section_key)
                if location:
                    return location[0]   # pdf_page from the document's actual structure

        # Step 3: static fallback — canonical UAD page numbers
        return self._SECTION_DEFAULT_PAGES.get(section_prefix, 1)

    def _rule_search_terms(self, rule_id: str, result: RuleResult) -> List[str]:
        terms = []
        if result.appraisal_value:
            terms.append(result.appraisal_value)
        if result.message:
            terms.extend(re.findall(r"'([^']{3,80})'", result.message))

        defaults = {
            "S-1": ["Property Address", "Subject", "City", "County"],
            "S-2": ["Borrower"],
            "S-3": ["Owner of Public Record"],
            "S-4": ["Legal Description", "Assessor", "Tax Year"],
            "S-5": ["Neighborhood Name", "Neighborhood"],
            "S-6": ["Map Reference", "Census Tract"],
            "S-7": ["Occupant", "Vacant", "Owner", "Tenant"],
            "S-8": ["Special Assessments"],
            "S-9": ["PUD", "HOA"],
            "S-10": ["Lender", "Client"],
            "S-11": ["Property Rights", "Fee Simple", "Leasehold"],
            "S-12": ["offered for sale", "Prior Sale", "Days on Market"],
            "C-1": ["Analyze Contract", "Contract"],
            "C-2": ["Contract Price", "Date of Contract", "Sale Price"],
            "C-3": ["Owner of Record", "Data Source"],
            "N-1": ["Neighborhood Characteristics", "Location", "Built-Up", "Growth"],
            "N-2": ["Housing Trends", "Property Values", "Demand", "Marketing Time"],
            "N-3": ["One-Unit Housing", "PRICE", "AGE"],
            "N-4": ["Present Land Use", "Land Use"],
            "N-5": ["Neighborhood Boundaries"],
            "N-6": ["Neighborhood Description"],
            "N-7": ["Market Conditions"],
            "ST-1": ["Dimensions", "Site Area", "Shape"],
            "ST-2": ["Site Area"],
            "ST-3": ["Shape"],
            "ST-4": ["View"],
            "ST-5": ["Zoning", "Legal"],
            "ST-6": ["Highest and Best Use"],
            "ST-7": ["Utilities", "Off-site Improvements"],
            "ST-8": ["FEMA", "Flood"],
            "ST-9": ["Utilities typical", "Public", "Private"],
            "I-1": ["General Description", "Effective Age"],
            "I-3": ["Exterior", "Roof Surface"],
            "I-5": ["Utilities", "inspection"],
            "I-7": ["Above Grade", "GLA", "Gross Living Area"],
            "SCA-1": ["Comparable", "currently offered", "sold"],
            "SCA-2": ["Comparable", "Sale Price"],
            "SCA-5": ["Data Source", "MLS", "DOM"],
            "PH-1": ["Subject Front", "Subject Rear", "Subject Street"],
            "PH-4": ["Attic", "Crawl", "FHA"],
            "SK-1": ["Sketch", "Floor Plan"],
            "FHA-2": ["FHA Case", "Case Number"],
            "FHA-3": ["FHA", "Intended Use", "Intended User"],
            "COM-2": ["Market Conditions", "1004MC"],
            "COM-3": ["Comparable Selection", "comparables were selected"],
            "COM-4": ["adjustment", "Sales Comparison"],
            "COM-5": ["Reconciliation"],
            "COM-6": ["Addendum", "Additional Comments", "Certification"],
            "COM-7": ["Prior Sale", "offered for sale", "Days on Market"],
        }
        terms.extend(defaults.get(rule_id, []))
        return terms

    def get_improvement_suggestions(self):
        return self.logger.analyze_improvements()


# ── Global engine instance ─────────────────────────────────────────────────────
engine = RuleEngine()


def rule(id: str, name: str):
    """Decorator: mark a function as a QC rule and register it."""
    def decorator(func):
        func.rule_id = id
        func.rule_name = name
        engine.register_rule(func)
        return func
    return decorator
