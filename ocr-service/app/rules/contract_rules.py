"""
Contract Section Rules (C-1 through C-5)
All validation rules for the Contract section of appraisal reports.
NOTE: Contract Section rules apply ONLY to Purchase Transactions.
For Refinance transactions, this entire section must be BLANK.
"""
import re
from typing import Optional
from datetime import datetime
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


_GAR_PERSONAL_PROPERTY_BOILERPLATE = (
    "firewood shall not be considered debris",
    "property to be delivered in clean condition",
    "property being sold as-is",
    "property is being sold as-is",
    "of the otherwise identified in this agreement as remaining with the property",
)


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%m/%d/%Y")
        except ValueError:
            pass
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", value)
    if not match:
        return value
    month, day, year = match.groups()
    if len(year) == 2:
        year = f"20{year}" if int(year) < 70 else f"19{year}"
    try:
        return datetime(int(year), int(month), int(day)).strftime("%m/%d/%Y")
    except ValueError:
        return value


def _filter_personal_property_items(items: list[str]) -> list[str]:
    filtered = []
    for item in items or []:
        cleaned = re.sub(r"\s+", " ", str(item)).strip(" .;:,")
        lower = cleaned.lower()
        if not cleaned:
            continue
        if any(phrase in lower for phrase in _GAR_PERSONAL_PROPERTY_BOILERPLATE):
            continue
        if re.search(r"\b(?:as-is|debris|clean condition|otherwise identified in this agreement)\b", lower):
            continue
        filtered.append(cleaned)
    return filtered


def _contract_dates_in_text(text: Optional[str]) -> list[str]:
    dates = []
    for match in re.finditer(r"\b(?:Date\s+of\s+Contract|Contract\s+Date)\b[^0-9]{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text or "", re.I):
        normalized = _normalize_date(match.group(1))
        if normalized and normalized not in dates:
            dates.append(normalized)
    return dates


@rule(id="C-1", name="Contract Analysis Requirement")
def validate_contract_analysis(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Did/Did Not Analyze Contract checkbox
    If Purchase: Contract MUST be analyzed; section MUST be completed
    If Refinance: Entire contract section MUST be blank
    Commentary: Must show Analysis of Contract, Sale Type, and Results
    Sale Types to Identify: Arms-Length, Non Arms-Length, REO, Short Sale, Court Ordered
    
    HomeVision Logic:
    - NEVER return ERROR for checkbox detection failure
    - Return VERIFY if checkbox state unclear
    - Return FAIL only for definite business rule violation
    """
    # Check if this is a Refinance transaction
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        # Contract section should be blank for refinance
        if ctx.report.contract.contract_price is not None:
            return RuleResult(
                rule_id="C-1",
                rule_name="Contract Analysis Requirement",
                status=RuleStatus.FAIL,
                message="Assignment is meant for a refinance transaction; per UAD requirements, the contract section should be left blank."
            )
        
        # Skip remaining checks for refinance - PASS
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.PASS,
            message="Refinance: Contract section correctly blank."
        )
    
    # For Purchase transactions
    # If checkbox state is unknown (not detected), return VERIFY not ERROR
    if ctx.report.contract.did_analyze_contract is None:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message="Did/Did Not Analyze Contract checkbox not detected. Please verify manually."
        )
    
    if ctx.report.contract.did_analyze_contract is False:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.FAIL,
            message="Contract must be analyzed for purchase transactions. Please mark 'Did Analyze Contract'."
        )
    
    # Did Analyze Contract = True - check for additional requirements
    # Unclear contract analysis goes to VERIFY.
    if not ctx.report.contract.contract_analysis_comment or len(ctx.report.contract.contract_analysis_comment.strip()) < 20:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message="Appraiser must provide detailed reasoning and analysis of the contract including sale type and results."
        )
    
    # Missing sale type goes to VERIFY.
    if not ctx.report.contract.sale_type:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.VERIFY,
            message="Please identify the sale type (Arms-Length, Non Arms-Length, REO, Short Sale, or Court Ordered Sale)."
        )
    
    return RuleResult(
        rule_id="C-1",
        rule_name="Contract Analysis Requirement",
        status=RuleStatus.PASS,
        message=f"Contract analyzed. Sale type: {ctx.report.contract.sale_type}"
    )


@rule(id="C-2", name="Contract Price and Date")
def validate_contract_price_date(ctx: ValidationContext) -> RuleResult:
    """
    Target Fields: Contract Price, Date of Contract
    Rule: Must match Purchase Agreement EXACTLY (if available)
    Contract Date: Date of LAST signature (fully executed date)
    
    HomeVision Logic:
    - Skip for Refinance transactions
    - If Purchase Agreement not provided, verify contract fields exist in report
    - Compare with engagement letter if available
    - Never ERROR for missing documents - use VERIFY
    """
    # Skip for Refinance
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.PASS,
            message="Refinance: Contract validation not applicable."
        )
    
    rpt_contract = ctx.report.contract
    
    # Check if contract price exists in report
    if rpt_contract.contract_price is None:
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.VERIFY,
            message="Contract Price not extracted from report. Please verify manually."
        )
    
    # If Purchase Agreement is available, compare
    if ctx.purchase_agreement and ctx.purchase_agreement.contract_price is not None:
        if rpt_contract.contract_price != ctx.purchase_agreement.contract_price:
            return RuleResult(
                rule_id="C-2",
                rule_name="Contract Price and Date",
                status=RuleStatus.FAIL,
                message=f"In contract section, Contract Price noted as ${rpt_contract.contract_price:,.2f}; however, purchase contract shows ${ctx.purchase_agreement.contract_price:,.2f}. Please verify.",
                details={
                    "report_price": rpt_contract.contract_price,
                    "pa_price": ctx.purchase_agreement.contract_price
                }
            )
        
        # Validate Contract Date if both available
        if rpt_contract.date_of_contract and ctx.purchase_agreement.contract_date:
            report_date = _normalize_date(rpt_contract.date_of_contract)
            pa_date = _normalize_date(ctx.purchase_agreement.contract_date)
            if report_date != pa_date:
                internal_dates = [d for d in _contract_dates_in_text(ctx.raw_text) if d != report_date]
                internal_note = ""
                if internal_dates:
                    internal_note = (
                        f" The appraisal also references contract date(s) {', '.join(internal_dates)}, "
                        "creating an internal inconsistency."
                    )
                return RuleResult(
                    rule_id="C-2",
                    rule_name="Contract Price and Date",
                    status=RuleStatus.FAIL,
                    message=(
                        f"Contract section shows Date of Contract as {report_date}; however, the purchase "
                        f"agreement shows the fully executed/binding agreement date as {pa_date}.{internal_note} "
                        f"Please revise the contract date field to reflect {pa_date}."
                    ),
                    details={
                        "report_date": report_date,
                        "pa_date": pa_date
                    }
                )
    
    # If engagement letter has contract price, compare (check attribute exists)
    elif ctx.engagement_letter and hasattr(ctx.engagement_letter, 'contract_price') and ctx.engagement_letter.contract_price is not None:
        if rpt_contract.contract_price != ctx.engagement_letter.contract_price:
            return RuleResult(
                rule_id="C-2",
                rule_name="Contract Price and Date",
                status=RuleStatus.FAIL,
                message=f"In contract section, Contract Price noted as ${rpt_contract.contract_price:,.2f}; however, engagement letter shows ${ctx.engagement_letter.contract_price:,.2f}. Please verify.",
                details={
                    "report_price": rpt_contract.contract_price,
                    "engagement_price": ctx.engagement_letter.contract_price
                }
            )
    
    # No Purchase Agreement to compare - just verify fields exist
    message = f"Contract Price: ${rpt_contract.contract_price:,.2f}"
    if rpt_contract.date_of_contract:
        message += f", Date: {rpt_contract.date_of_contract}"
    
    return RuleResult(
        rule_id="C-2",
        rule_name="Contract Price and Date",
        status=RuleStatus.PASS,
        message=message
    )


@rule(id="C-3", name="Owner of Record Data Source")
def validate_owner_record_source(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Is the property seller the owner of public record?
    Rule: Must check Yes or No with data source
    If No: Commentary MUST be provided
    """
    # Skip for Refinance
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.PASS,
            message="Refinance: Owner record validation not applicable."
        )
    
    c = ctx.report.contract
    
    if c.is_seller_owner is None:
        # Checkbox not detected - return VERIFY not ERROR
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.VERIFY,
            message="Is Seller Owner of Public Record checkbox not detected. Please verify manually."
        )
    
    # Check for data source
    if not c.owner_record_data_source or len(c.owner_record_data_source.strip()) < 2:
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.FAIL,
            message='Please provide data source for "Is the property seller the owner of public record?" under contract section.'
        )
    
    # If seller is NOT the owner, commentary is required
    if c.is_seller_owner is False:
        if not c.owner_record_commentary or len(c.owner_record_commentary.strip()) < 10:
            return RuleResult(
                rule_id="C-3",
                rule_name="Owner of Record Data Source",
                status=RuleStatus.FAIL,
                message="Seller is not the owner of public record. Please provide commentary explaining this discrepancy."
            )
    
    return RuleResult(
        rule_id="C-3",
        rule_name="Owner of Record Data Source",
        status=RuleStatus.PASS,
        message="Owner of record data source is provided."
    )


@rule(id="C-4", name="Financial Assistance")
def validate_financial_assistance(ctx: ValidationContext) -> RuleResult:
    """
    Target Field: Financial Assistance (loan charges, sale concessions, gift or down payment assistance)
    Rule: Yes or No checkbox MUST be marked
    If Yes: Report total dollar amount and describe items
    If No: Dollar amount field should show "0"
    Validation: Cross-check with Purchase Agreement
    """
    # Skip for Refinance
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        return RuleResult(
            rule_id="C-4",
            rule_name="Financial Assistance",
            status=RuleStatus.PASS,
            message="Refinance: Financial assistance validation not applicable."
        )
    
    c = ctx.report.contract
    
    # Check if checkbox was detected
    if c.financial_assistance is None:
        return RuleResult(
            rule_id="C-4",
            rule_name="Financial Assistance",
            status=RuleStatus.VERIFY,
            message="Financial Assistance checkbox (Yes/No) not detected. Please verify manually."
        )
    
    # If No, amount should be 0
    if c.financial_assistance is False:
        if c.financial_assistance_amount is not None and c.financial_assistance_amount > 0:
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.FAIL,
                message=f"Financial Assistance is marked 'No', but amount shows ${c.financial_assistance_amount:,.2f}. Please verify."
            )
    
    # If Yes, amount should be provided and > 0
    if c.financial_assistance is True:
        if re.search(r"\$\s*0(?:\.00)?\s*;{1,2}\s*closing\s+costs|\bclosing\s+costs\b.{0,40}\$\s*0(?:\.00)?", ctx.raw_text or "", re.I):
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.PASS,
                message="Report text indicates $0 closing-cost concessions/financial assistance.",
                details={"checkbox_extracted_as": "Yes", "amount_evidence": "$0 closing costs"}
            )
        if ctx.purchase_agreement and ctx.purchase_agreement.concessions_amount is not None:
            pa_amount = ctx.purchase_agreement.concessions_amount
            rpt_amount = c.financial_assistance_amount or 0
            if abs(pa_amount) <= 0.01 and abs(rpt_amount) <= 0.01:
                return RuleResult(
                    rule_id="C-4",
                    rule_name="Financial Assistance",
                    status=RuleStatus.PASS,
                    message="Purchase agreement and report amount both indicate $0 financial assistance/concessions.",
                    details={
                        "pa_amount": pa_amount,
                        "report_amount": rpt_amount,
                        "checkbox_extracted_as": "Yes"
                    }
                )
        if c.financial_assistance_amount is None or c.financial_assistance_amount <= 0:
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.VERIFY,
                message="Financial Assistance is marked 'Yes', but no amount is specified."
            )
        
        # Should have description
        if not c.financial_assistance_description or len(c.financial_assistance_description.strip()) < 5:
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.VERIFY,
                message=f"Financial assistance amount (${c.financial_assistance_amount:,.2f}) is noted, but description of items is missing or incomplete."
            )
    
    # Cross-check with Purchase Agreement if available
    if ctx.purchase_agreement and ctx.purchase_agreement.concessions_amount is not None:
        pa_amount = ctx.purchase_agreement.concessions_amount
        rpt_amount = c.financial_assistance_amount or 0
        
        if abs(pa_amount - rpt_amount) > 0.01:  # Allow for small floating point differences
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.FAIL,
                message=f"Purchase agreement shows concession as ${pa_amount:,.2f}; however, report shows concession as ${rpt_amount:,.2f}. Please verify.",
                details={
                    "pa_amount": pa_amount,
                    "report_amount": rpt_amount
                }
            )
    
    return RuleResult(
        rule_id="C-4",
        rule_name="Financial Assistance",
        status=RuleStatus.PASS,
        message="Financial assistance information is consistent."
    )


@rule(id="C-5", name="Personal Property Analysis")
def validate_personal_property(ctx: ValidationContext) -> RuleResult:
    """
    Target: Concessions Commentary
    Rule: Identify all personal property items from contract
    Requirement: State whether personal property items contribute to value
    """
    # Skip for Refinance
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        return RuleResult(
            rule_id="C-5",
            rule_name="Personal Property Analysis",
            status=RuleStatus.PASS,
            message="Refinance: Personal property validation not applicable."
        )
    
    # Check if Purchase Agreement indicates personal property
    if ctx.purchase_agreement and ctx.purchase_agreement.personal_property_items:
        pa_items = _filter_personal_property_items(ctx.purchase_agreement.personal_property_items)
        if pa_items:
            comment = ctx.report.contract.sales_concessions_comment or ""
            
            # Check if commentary exists
            if len(comment.strip()) < 10:
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.FAIL,
                    message=f"Purchase Agreement indicates personal property items ({', '.join(pa_items)}), but report commentary is missing or incomplete."
                )
            
            # Check if items are mentioned in commentary (basic check)
            comment_upper = comment.upper()
            missing_items = []
            for item in pa_items:
                if item.upper() not in comment_upper:
                    missing_items.append(item)
            
            if missing_items:
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.VERIFY,
                    message=f"Personal property items from contract may not be fully addressed in commentary. Items: {', '.join(missing_items)}"
                )
            
            # Check if "contribute" or "value" is mentioned
            contributes_keywords = ["CONTRIBUTE", "VALUE", "NO VALUE", "CONTRIBUTORY"]
            has_contribution_statement = any(keyword in comment_upper for keyword in contributes_keywords)
            
            if not has_contribution_statement:
                return RuleResult(
                    rule_id="C-5",
                    rule_name="Personal Property Analysis",
                    status=RuleStatus.VERIFY,
                    message="Please state whether personal property items contribute to the appraised value."
                )
    
    # Check if report has personal property items documented
    report_items = _filter_personal_property_items(ctx.report.contract.personal_property_items)
    if report_items:
        if ctx.report.contract.personal_property_contributes_to_value is None:
            return RuleResult(
                rule_id="C-5",
                rule_name="Personal Property Analysis",
                status=RuleStatus.VERIFY,
                message="Personal property items are listed. Please explicitly state whether they contribute to value."
            )
    
    return RuleResult(
        rule_id="C-5",
        rule_name="Personal Property Analysis",
        status=RuleStatus.PASS,
        message="Personal property analysis is complete."
    )
