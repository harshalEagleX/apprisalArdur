"""
Rule Engine — Phase 3 upgrade.

Improvements over previous version:
  - Rules execute in DB-configured order (structural → logic → commentary)
  - Inactive rules are skipped (toggle via DB, no code restart)
  - Severity (BLOCKING / STANDARD / ADVISORY) attached to every result
  - source_page and field_confidence passed from Phase 2 field_meta
  - Single rule crash never stops other rules
"""

import logging
import re
from typing import List, Callable, Dict, Optional

from app.models.appraisal import ValidationContext
from app.rule_engine.smart_identifier import (
    SmartLogger, RuleResult, RuleStatus, RuleSeverity, DataMissingException
)

logger = logging.getLogger(__name__)


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

            # Skip inactive rules
            if cfg and not cfg.is_active:
                results.append(RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.SKIPPED,
                    message="Rule disabled via configuration.",
                    severity=RuleSeverity(cfg.severity) if cfg else RuleSeverity.STANDARD,
                ))
                continue

            # Skip rules that do not apply to this assignment or loan type.
            if cfg and not self._is_applicable(context, cfg.applicable_loan_types):
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.SKIPPED,
                    message=f"Rule not applicable for this assignment/loan type ({cfg.applicable_loan_types}).",
                    severity=RuleSeverity(cfg.severity),
                )
                results.append(res)
                self.logger.log_result(res)
                continue

            # Attach field metadata for source_page + bbox + confidence lookup
            field_conf, src_page, field_meta = self._extract_meta(context, rule_id)

            try:
                result = rule_func(context)

                # Attach Phase 3 metadata if not set by the rule itself
                if cfg:
                    if result.severity == RuleSeverity.STANDARD:
                        result.severity = RuleSeverity(cfg.severity)
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

                results.append(result)
                self.logger.log_result(result)

            except DataMissingException as e:
                res = RuleResult(
                    rule_id=rule_id,
                    rule_name=getattr(rule_func, "rule_name", rule_id),
                    status=RuleStatus.VERIFY,
                    message=str(e),
                    details={"field": e.field_name},
                    action_item=f"Manually verify field '{e.field_name}' in the document.",
                    review_required=True,
                    severity=RuleSeverity(cfg.severity) if cfg else RuleSeverity.STANDARD,
                )
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
                )
                results.append(res)
                self.logger.log_result(res)

        return results

    def _extract_meta(
        self, context: ValidationContext, rule_id: str
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

        field_name = RULE_FIELD_MAP.get(rule_id)
        if not field_name or not context.field_meta:
            return None, None, None

        meta = context.field_meta.get(field_name)
        if meta and hasattr(meta, "effective_confidence"):
            return meta.effective_confidence, meta.source_page, meta
        return None, None, None

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

    def _infer_source_page(self, context: ValidationContext, rule_id: str, result: RuleResult):
        """Best-effort page fallback for rules that do not map to a single extracted field."""
        page_index = context.page_index or {}
        if not page_index:
            return None

        for term in self._rule_search_terms(rule_id, result):
            term_l = term.lower().strip()
            if not term_l:
                continue
            for page_num in sorted(page_index.keys()):
                if term_l in (page_index.get(page_num) or "").lower():
                    return page_num
        return None

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
