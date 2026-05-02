"""Cross-field validation rules that require the full extracted report."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from app.models.appraisal import ValidationContext
from app.rule_engine.outcome import evaluate_rule
from app.rule_engine.smart_identifier import RuleResult, RuleSeverity, RuleStatus


class CrossFieldValidator:
    def validate(self, context: ValidationContext) -> List[RuleResult]:
        results: List[RuleResult] = []
        for check in (
            self._housing_trend_vs_time_adjustments,
            self._comp_prices_vs_neighborhood_range,
            self._condition_vs_effective_age,
            self._subject_address_three_way,
            self._pud_vs_hoa,
            self._refinance_contract_blank,
            self._fha_case_number_all_pages,
            self._fha_comp_recency,
            self._fha_remaining_economic_life,
        ):
            result = check(context)
            if result:
                results.append(result)
        return results

    def _housing_trend_vs_time_adjustments(self, context: ValidationContext) -> Optional[RuleResult]:
        trend = (context.report.neighborhood.property_values or "").lower()
        if trend not in {"increasing", "declining"}:
            return None
        text = context.raw_text or ""
        adjustments = [float(v.replace(",", "")) for v in re.findall(r"(?:time|date).*?\$?\(?(-?[\d,]+)\)?", text, re.I)]
        if adjustments and any(v != 0 for v in adjustments):
            return None
        return RuleResult(
            rule_id="XF-1",
            rule_name="Housing Trend vs Time Adjustments",
            status=RuleStatus.FAIL,
            message=f"Neighborhood trend is {trend}, but time/date-of-sale adjustments were not detected.",
            rejection_text=f"Neighborhood trend is {trend}, but no non-zero time/date-of-sale adjustments were detected.",
            review_required=True,
            severity=RuleSeverity.BLOCKING,
            evidence=["Neighborhood property values", "Sales comparison grid date/time adjustments"],
        )

    def _comp_prices_vs_neighborhood_range(self, context: ValidationContext) -> Optional[RuleResult]:
        low = context.report.neighborhood.price_low
        high = context.report.neighborhood.price_high
        comps = context.report.sales_comparison.comparables or []
        if not low or not high or not comps:
            return None
        outliers = [
            f"Comp {idx}: ${comp.sale_price:,.0f}"
            for idx, comp in enumerate(comps, start=1)
            if comp.sale_price and (comp.sale_price < low or comp.sale_price > high)
        ]
        if not outliers:
            return None
        return RuleResult(
            rule_id="XF-2",
            rule_name="Comparable Prices vs Neighborhood Range",
            status=RuleStatus.VERIFY,
            message="Comparable sale price outside stated neighborhood range.",
            verify_question=(
                f"{'; '.join(outliers)} is outside the stated one-unit housing price range "
                f"${low:,.0f}-${high:,.0f}. Please confirm whether the comparable is from a competing "
                "neighborhood and whether the report explains the outlier."
            ),
            review_required=True,
            evidence=["Neighborhood One-Unit Housing Prices", "Sales comparison grid"],
        )

    def _condition_vs_effective_age(self, context: ValidationContext) -> Optional[RuleResult]:
        rating = (context.report.improvements.condition_rating or "").upper()
        effective_age = context.report.improvements.effective_age
        actual_age = None
        if context.report.improvements.year_built:
            actual_age = max(0, datetime.utcnow().year - context.report.improvements.year_built)
        if not rating or effective_age is None:
            return self._vision_condition_check(context)
        inconsistent = (rating == "C1" and effective_age > 5) or (rating in {"C5", "C6"} and actual_age and effective_age < actual_age * 0.5)
        if not inconsistent:
            return self._vision_condition_check(context)
        return RuleResult(
            rule_id="XF-3",
            rule_name="Condition Rating vs Effective Age",
            status=RuleStatus.VERIFY,
            message="Condition rating and effective age may be inconsistent.",
            verify_question=(
                f"The report states condition {rating} with effective age {effective_age}"
                + (f" and actual age about {actual_age}" if actual_age is not None else "")
                + ". Please verify these are internally consistent."
            ),
            review_required=True,
            evidence=["Improvements condition rating", "Effective age"],
        )

    def _vision_condition_check(self, context: ValidationContext) -> Optional[RuleResult]:
        reported = (context.report.improvements.condition_rating or "").upper()
        if not reported or not context.vision_results:
            return None
        condition_notes = [r for r in context.vision_results if getattr(r, "task", "") == "condition"]
        severe = [r for r in condition_notes if re.search(r"\bC[45]\b|\bC6\b", getattr(r, "response", ""), re.I)]
        if reported in {"C1", "C2"} and severe:
            first = severe[0]
            return RuleResult(
                rule_id="XF-VIS-1",
                rule_name="Vision Condition vs Reported Condition",
                status=RuleStatus.VERIFY,
                message="Vision model condition evidence differs from reported condition.",
                verify_question=(
                    f"The report states condition {reported}, but LLaVA analysis on page {first.page} returned: "
                    f"{first.response}. Please confirm the reported condition rating."
                ),
                review_required=True,
                evidence=[f"Vision page {first.page}", "Reported improvement condition rating"],
            )
        return None

    def _subject_address_three_way(self, context: ValidationContext) -> Optional[RuleResult]:
        subject = context.report.subject.address
        engagement = context.engagement_letter.property_address if context.engagement_letter else None
        grid = None
        comps = context.report.sales_comparison.comparables or []
        if comps:
            grid = comps[0].address if (comps[0].address or "").lower().startswith("subject") else None
        if not subject or not engagement:
            return None
        outcome = evaluate_rule(
            rule_id="XF-4",
            rule_name="Subject Address Across Sources",
            extracted=subject,
            expected=engagement,
            extraction_confidence=0.99,
            match_type="fuzzy",
            field_name="Subject address",
            evidence=["Page 1 subject address", "Engagement letter property address"],
            fail_message=f"Subject address '{subject}' does not match engagement letter address '{engagement}'.",
            severity=RuleSeverity.BLOCKING,
        )
        result = outcome.to_rule_result()
        if result.status == RuleStatus.PASS and grid:
            result.message = "Subject address matched across available sources."
        return result if result.status != RuleStatus.PASS else None

    def _pud_vs_hoa(self, context: ValidationContext) -> Optional[RuleResult]:
        dues = context.report.subject.hoa_dues or 0
        is_pud = bool(context.report.subject.is_pud)
        if dues > 0 and not is_pud:
            return RuleResult(
                rule_id="XF-5",
                rule_name="PUD Checkbox vs HOA Dues",
                status=RuleStatus.FAIL,
                message=f"HOA dues are ${dues:,.0f}, but PUD checkbox is not marked.",
                rejection_text=f"HOA dues are ${dues:,.0f}, but PUD checkbox is not marked.",
                review_required=True,
                severity=RuleSeverity.BLOCKING,
            )
        if dues == 0 and is_pud:
            return RuleResult(
                rule_id="XF-5",
                rule_name="PUD Checkbox vs HOA Dues",
                status=RuleStatus.VERIFY,
                message="PUD marked with zero HOA dues.",
                verify_question="PUD is marked but HOA dues are zero. Please verify whether dues are missing or the PUD checkbox is incorrect.",
                review_required=True,
            )
        return None

    def _refinance_contract_blank(self, context: ValidationContext) -> Optional[RuleResult]:
        assignment = (context.engagement_letter.assignment_type if context.engagement_letter else None) or context.report.contract.assignment_type or ""
        if assignment.lower() != "refinance":
            return None
        contract = context.report.contract
        populated = [
            name for name, value in contract.model_dump().items()
            if name != "assignment_type" and value not in (None, "", [], False, 0)
        ]
        if not populated:
            return None
        return RuleResult(
            rule_id="XF-6",
            rule_name="Refinance Contract Section Blank",
            status=RuleStatus.FAIL,
            message=f"Refinance assignment has populated contract fields: {', '.join(populated)}.",
            rejection_text=f"Refinance assignment requires the contract section to be blank/default, but these fields are populated: {', '.join(populated)}.",
            review_required=True,
            severity=RuleSeverity.BLOCKING,
        )

    def _fha_case_number_all_pages(self, context: ValidationContext) -> Optional[RuleResult]:
        if not self._is_fha(context):
            return None
        missing = []
        pattern = re.compile(r"\b\d{3}-\d{7}\b")
        for page, text in (context.page_index or {}).items():
            header = " ".join((text or "").split()[:80])
            if not pattern.search(header):
                missing.append(str(page))
        if not missing:
            return None
        return RuleResult(
            rule_id="XF-FHA-1",
            rule_name="FHA Case Number On Every Page",
            status=RuleStatus.FAIL,
            message=f"FHA case number missing from page header on page(s): {', '.join(missing)}.",
            rejection_text=f"FHA case number is missing from the page header on page(s): {', '.join(missing)}.",
            review_required=True,
            severity=RuleSeverity.BLOCKING,
        )

    def _fha_comp_recency(self, context: ValidationContext) -> Optional[RuleResult]:
        if not self._is_fha(context):
            return None
        effective = self._date_from_text(context.raw_text or "")
        if not effective:
            return None
        old = []
        for idx, comp in enumerate((context.report.sales_comparison.comparables or [])[:3], start=1):
            sale_date = self._date(comp.sale_date)
            if sale_date and (effective - sale_date).days > 365:
                old.append(f"Comp {idx} sale date {comp.sale_date}")
        if not old:
            return None
        return RuleResult(
            rule_id="XF-FHA-2",
            rule_name="FHA Comparable Recency",
            status=RuleStatus.FAIL,
            message="Primary FHA comparable sale date is older than 12 months.",
            rejection_text=f"Primary FHA comparable(s) exceed 12 months from effective date: {', '.join(old)}.",
            review_required=True,
            severity=RuleSeverity.BLOCKING,
        )

    def _fha_remaining_economic_life(self, context: ValidationContext) -> Optional[RuleResult]:
        if not self._is_fha(context):
            return None
        match = re.search(r"remaining economic life[^0-9]{0,20}(\d{1,3})", context.raw_text or "", re.I)
        if not match:
            return None
        years = int(match.group(1))
        if years >= 30:
            return None
        has_comment = "remaining economic life" in (context.raw_text or "").lower() and any(
            word in (context.raw_text or "").lower() for word in ("explain", "because", "due to", "support")
        )
        if has_comment:
            return None
        return RuleResult(
            rule_id="XF-FHA-3",
            rule_name="FHA Remaining Economic Life",
            status=RuleStatus.FAIL,
            message=f"Remaining economic life is {years} years with no supporting explanation detected.",
            rejection_text=f"FHA remaining economic life is below 30 years ({years}) and no supporting explanation was detected.",
            review_required=True,
            severity=RuleSeverity.BLOCKING,
        )

    def _is_fha(self, context: ValidationContext) -> bool:
        loan_type = (context.engagement_letter.loan_type if context.engagement_letter else "") or ""
        return "fha" in loan_type.lower() or bool(re.search(r"\bFHA\b", context.raw_text or ""))

    def _date_from_text(self, text: str) -> Optional[datetime]:
        match = re.search(r"effective date[^0-9]{0,30}(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
        return self._date(match.group(1)) if match else None

    def _date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        return None
