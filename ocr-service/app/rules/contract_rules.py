"""
Contract Section Rules (C-1 through C-5)
All validation rules for the Contract section of appraisal reports.
NOTE: Contract Section rules apply ONLY to Purchase Transactions.
For Refinance transactions, this entire section must be BLANK.
"""
from typing import Optional
from datetime import datetime
from app.rule_engine.engine import rule, RuleStatus, RuleResult, DataMissingException
from app.models.appraisal import ValidationContext


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
    - Return WARNING if checkbox state unclear
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
    # If checkbox state is unknown (not detected), check if we have analysis commentary
    if ctx.report.contract.did_analyze_contract is None:
        # If we have substantial analysis commentary, infer that contract was analyzed
        comment = ctx.report.contract.contract_analysis_comment or ""
        if len(comment.strip()) >= 20:
            # Commentary exists - infer contract was analyzed
            ctx.report.contract.did_analyze_contract = True
        else:
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
    # Check for contract analysis commentary (optional warning, not failure)
    if not ctx.report.contract.contract_analysis_comment or len(ctx.report.contract.contract_analysis_comment.strip()) < 20:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.WARNING,
            message="Appraiser must provide detailed reasoning and analysis of the contract including sale type and results."
        )
    
    # Check if sale type is identified (optional warning)
    if not ctx.report.contract.sale_type:
        return RuleResult(
            rule_id="C-1",
            rule_name="Contract Analysis Requirement",
            status=RuleStatus.WARNING,
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
    - Never ERROR for missing documents - use WARNING
    """
    # Skip for Refinance
    if ctx.engagement_letter and ctx.engagement_letter.assignment_type == "Refinance":
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.PASS,
            message="Refinance: Contract validation skipped."
        )
    
    rpt_contract = ctx.report.contract
    
    # Check if contract price exists in report
    if rpt_contract.contract_price is None:
        return RuleResult(
            rule_id="C-2",
            rule_name="Contract Price and Date",
            status=RuleStatus.WARNING,
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
            if rpt_contract.date_of_contract != ctx.purchase_agreement.contract_date:
                return RuleResult(
                    rule_id="C-2",
                    rule_name="Contract Price and Date",
                    status=RuleStatus.FAIL,
                    message=f"In contract section, Contract Date noted as {rpt_contract.date_of_contract}; however, purchase contract shows {ctx.purchase_agreement.contract_date}. Please verify.",
                    details={
                        "report_date": rpt_contract.date_of_contract,
                        "pa_date": ctx.purchase_agreement.contract_date
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
            message="Refinance: Owner record validation skipped."
        )
    
    c = ctx.report.contract
    
    if c.is_seller_owner is None:
        # Checkbox not detected - return WARNING not ERROR
        return RuleResult(
            rule_id="C-3",
            rule_name="Owner of Record Data Source",
            status=RuleStatus.WARNING,
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
            message="Refinance: Financial assistance validation skipped."
        )
    
    c = ctx.report.contract
    
    # Check if checkbox was detected
    if c.financial_assistance is None:
        return RuleResult(
            rule_id="C-4",
            rule_name="Financial Assistance",
            status=RuleStatus.WARNING,
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
        if c.financial_assistance_amount is None or c.financial_assistance_amount <= 0:
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.WARNING,
                message="Financial Assistance is marked 'Yes', but no amount is specified."
            )
        
        # Should have description
        if not c.financial_assistance_description or len(c.financial_assistance_description.strip()) < 5:
            return RuleResult(
                rule_id="C-4",
                rule_name="Financial Assistance",
                status=RuleStatus.WARNING,
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
            message="Refinance: Personal property validation skipped."
        )
    
    # Check if Purchase Agreement indicates personal property
    if ctx.purchase_agreement and ctx.purchase_agreement.personal_property_items:
        pa_items = ctx.purchase_agreement.personal_property_items
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
                status=RuleStatus.WARNING,
                message=f"Personal property items from contract may not be fully addressed in commentary. Items: {', '.join(missing_items)}"
            )
        
        # Check if "contribute" or "value" is mentioned
        contributes_keywords = ["CONTRIBUTE", "VALUE", "NO VALUE", "CONTRIBUTORY"]
        has_contribution_statement = any(keyword in comment_upper for keyword in contributes_keywords)
        
        if not has_contribution_statement:
            return RuleResult(
                rule_id="C-5",
                rule_name="Personal Property Analysis",
                status=RuleStatus.WARNING,
                message="Please state whether personal property items contribute to the appraised value."
            )
    
    # Check if report has personal property items documented
    if ctx.report.contract.personal_property_items:
        if ctx.report.contract.personal_property_contributes_to_value is None:
            return RuleResult(
                rule_id="C-5",
                rule_name="Personal Property Analysis",
                status=RuleStatus.WARNING,
                message="Personal property items are listed. Please explicitly state whether they contribute to value."
            )
    
    return RuleResult(
        rule_id="C-5",
        rule_name="Personal Property Analysis",
        status=RuleStatus.PASS,
        message="Personal property analysis is complete."
    )
