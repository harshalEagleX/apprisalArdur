#!/usr/bin/env python3
"""
OCR Extraction and Rules Test Script

This script:
1. Extracts text from appraisal and engagement letter PDFs using OCR
2. Saves extracted text to separate files
3. Applies QC rules (S-1 to S-12 and C-1 to C-5)
4. Logs all results with proper formatting
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.ocr.ocr_pipeline import OCRPipeline, ExtractionResult
from app.qc_processor import SmartQCProcessor, QCResults
from app.rule_engine.engine import engine, RuleStatus, RuleResult
from app.models.appraisal import (
    AppraisalReport, EngagementLetter, PurchaseAgreement,
    ValidationContext, SubjectSection, ContractSection
)

# Import rules to register them
import app.rules

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(output_dir: Path) -> logging.Logger:
    """Configure logging with both console and file handlers."""
    
    # Create logs directory within output
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create formatter
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter('%(levelname)s: %(message)s')
    
    # Get root logger
    logger = logging.getLogger('OCRTest')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []  # Clear existing handlers
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # File handler for all logs
    file_handler = logging.FileHandler(log_dir / "test_run.log", mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Separate file for rule results only
    rule_handler = logging.FileHandler(log_dir / "rule_results.log", mode='w')
    rule_handler.setLevel(logging.INFO)
    rule_handler.setFormatter(detailed_formatter)
    
    rule_logger = logging.getLogger('RuleResults')
    rule_logger.setLevel(logging.INFO)
    rule_logger.handlers = []
    rule_logger.addHandler(rule_handler)
    rule_logger.addHandler(console_handler)
    
    return logger


# ============================================================================
# OCR EXTRACTION
# ============================================================================

def extract_pdf_text(pdf_path: str, logger: logging.Logger) -> tuple[str, ExtractionResult]:
    """
    Extract text from PDF using OCR pipeline.
    
    Returns:
        Tuple of (full_text, extraction_result)
    """
    logger.info(f"=" * 60)
    logger.info(f"EXTRACTING: {os.path.basename(pdf_path)}")
    logger.info(f"=" * 60)
    
    if not os.path.exists(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Create OCR pipeline with forced image mode for better layout handling
    pipeline = OCRPipeline(use_tesseract=True, use_cloud=False, force_image_ocr=True)
    
    # Extract all pages
    logger.info("Starting OCR extraction...")
    result = pipeline.extract_all_pages(pdf_path)
    
    # Log extraction statistics
    logger.info(f"Total pages: {result.total_pages}")
    logger.info(f"Extraction time: {result.extraction_time_ms}ms")
    
    for page_detail in result.page_details:
        logger.debug(f"  Page {page_detail.page_number}: "
                    f"method={page_detail.method}, "
                    f"confidence={page_detail.confidence:.2f}, "
                    f"words={page_detail.word_count}")
    
    if result.warnings:
        for warning in result.warnings:
            logger.warning(f"  {warning}")
    
    # Get full text
    full_text = pipeline.get_full_text(result.page_index)
    logger.info(f"Total characters extracted: {len(full_text)}")
    logger.info(f"Total words extracted: {len(full_text.split())}")
    
    return full_text, result


def save_extracted_text(text: str, output_path: Path, doc_name: str, logger: logging.Logger):
    """Save extracted text to a file."""
    logger.info(f"Saving extracted text to: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"{'=' * 60}\n")
        f.write(f"EXTRACTED TEXT FROM: {doc_name}\n")
        f.write(f"Extraction Date: {datetime.now().isoformat()}\n")
        f.write(f"Total Characters: {len(text)}\n")
        f.write(f"Total Words: {len(text.split())}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(text)
    
    logger.info(f"  Saved {len(text)} characters to {output_path.name}")


# ============================================================================
# FIELD EXTRACTION
# ============================================================================

def extract_fields_from_text_new(appraisal_text: str, engagement_text: str, logger: logging.Logger) -> Dict[str, Any]:
    """Extract structured fields using the actual ExtractionService."""
    from app.services.extraction_service import ExtractionService
    
    logger.info("Extracting structured fields using ExtractionService...")
    
    service = ExtractionService()
    
    # Extract from appraisal report
    subject = service.extract_subject_section(appraisal_text)
    contract = service.extract_contract_section(appraisal_text)
    
    # Extract from engagement letter
    engagement = service.extract_engagement_letter(engagement_text)
    
    # Convert to dict format (only include non-None values to match expected format)
    fields = {}
    if subject.property_address: fields['property_address'] = subject.property_address
    if subject.city: fields['city'] = subject.city
    if subject.state: fields['state'] = subject.state
    if subject.zip_code: fields['zip_code'] = subject.zip_code
    if subject.county: fields['county'] = subject.county
    if subject.borrower_name: fields['borrower_name'] = subject.borrower_name
    if subject.owner_of_public_record: fields['owner_of_public_record'] = subject.owner_of_public_record
    if subject.legal_description: fields['legal_description'] = subject.legal_description
    if subject.assessors_parcel_number: fields['apn'] = subject.assessors_parcel_number
    if subject.tax_year: fields['tax_year'] = subject.tax_year
    if subject.real_estate_taxes: fields['re_taxes'] = str(subject.real_estate_taxes)
    if subject.neighborhood_name: fields['neighborhood_name'] = subject.neighborhood_name
    if subject.map_reference: fields['map_reference'] = subject.map_reference
    if subject.census_tract: fields['census_tract'] = subject.census_tract
    if subject.occupant_status: fields['occupant'] = subject.occupant_status
    if subject.lender_name: fields['lender_name'] = subject.lender_name
    if subject.property_rights: fields['property_rights'] = subject.property_rights
    if contract.did_analyze_contract: fields['did_analyze_contract'] = contract.did_analyze_contract
    if contract.contract_price: fields['contract_price'] = str(contract.contract_price)
    if contract.contract_date: fields['contract_date'] = contract.contract_date
    if contract.is_seller_owner_of_record is not None: fields['is_seller_owner'] = contract.is_seller_owner_of_record
    if hasattr(contract, 'has_financial_assistance') and contract.has_financial_assistance is not None:
        fields['has_financial_assistance'] = contract.has_financial_assistance
    if contract.financial_assistance_amount: fields['financial_assistance_amount'] = str(contract.financial_assistance_amount)
    # C-3 fields for owner record data source
    if contract.owner_record_data_source: fields['owner_record_data_source'] = contract.owner_record_data_source
    # S-12 fields for prior sale history
    if subject.offered_for_sale_12mo is not None: fields['offered_for_sale_12mo'] = subject.offered_for_sale_12mo
    if subject.data_source: fields['data_source'] = subject.data_source
    
    engagement_fields = {}
    if engagement.borrower_name: engagement_fields['borrower_name'] = engagement.borrower_name
    if engagement.property_address: engagement_fields['property_address'] = engagement.property_address
    if engagement.lender_name: engagement_fields['lender_name'] = engagement.lender_name
    if engagement.assignment_type: engagement_fields['assignment_type'] = engagement.assignment_type
    if engagement.city: engagement_fields['city'] = engagement.city
    if engagement.state: engagement_fields['state'] = engagement.state
    if engagement.zip_code: engagement_fields['zip_code'] = engagement.zip_code
    
    logger.info(f"Extracted {len(fields)} appraisal fields and {len(engagement_fields)} engagement fields")
    
    return {
        'appraisal_fields': fields,
        'engagement_fields': engagement_fields
    }


def extract_fields_from_text(text: str, logger: logging.Logger) -> Dict[str, Any]:
    """Extract structured fields from OCR text using regex patterns (OLD METHOD - DEPRECATED)."""
    import re
    
    logger.info("Extracting structured fields from text...")
    
    fields = {}
    
    # -------------------------------------------------------------------------
    # SUBJECT SECTION FIELDS (S-1 to S-12)
    # -------------------------------------------------------------------------
    
    # S-1: Property Address
    patterns = {
        'property_address': [
            r"Property Address[:\s]+(?!City|State|Zip|County|Borrower|Lender|File)([^\n]+)",
            r"Subject Property[:\s]+(?!City|State|Zip|County)([^\n]+)",
            r"Address[:\s]+(?!City|State)(\d+[^\n]+)",
            r"(?m)^(\d+\s+[A-Za-z0-9\.\s]+(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|Road|Street|Avenue|Drive).*?)$"
        ],
        'city': [
            r"City[:\s]+([A-Za-z\s]+?)(?:\s+State|\s+County)",
            r"City[:\s]+([^\n,]+)",
        ],
        'state': [
            r"State[:\s]+([A-Z]{2})",
            r"State[:\s]+([A-Za-z]+)",
        ],
        'zip_code': [
            r"Zip Code[:\s]+(\d{5}(?:-\d{4})?)",
            r"Zip[:\s]+(\d{5})",
        ],
        'county': [
            r"County[:\s]+([A-Za-z\s]+)",
        ],
        
        # S-2: Borrower
        'borrower_name': [
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)([^\n]+)",
            r"BORROWER[:\s]+(?!LENDER|CLIENT)([^\n]+)",
            r"Borrower Name[:\s]+(?!Information)([^\n]+)",
        ],
        
        # S-3: Owner of Public Record
        'owner_of_public_record': [
            r"Owner of Public Record[:\s]+([^\n]+)",
            r"Current Owner[:\s]+([^\n]+)",
        ],
        
        # S-4: Legal Description and Tax
        'legal_description': [
            r"Legal Description[:\s]+([^\n]+)",
        ],
        'apn': [
            r"(?:Assessor['']?s? Parcel|APN)[:\s#]+([^\n]+)",
            r"Parcel (?:Number|#|No)[:\s]+([^\n]+)",
        ],
        'tax_year': [
            r"Tax Year[:\s]+(\d{4})",
        ],
        're_taxes': [
            r"R\.?E\.? Tax(?:es)?[:\s\$]+([0-9,]+(?:\.\d{2})?)",
            r"Real Estate Taxes?[:\s\$]+([0-9,]+(?:\.\d{2})?)",
        ],
        
        # S-5: Neighborhood
        'neighborhood_name': [
            r"Neighborhood Name[:\s]+([^\n]+)",
            r"Neighborhood[:\s]+([^\n]+)",
        ],
        
        # S-6: Map Reference and Census
        'map_reference': [
            r"Map Reference[:\s]+([^\n]+)",
        ],
        'census_tract': [
            r"Census Tract[:\s]+(?!Occupant)(\d{4}\.\d{2})",
            r"Census Tract[:\s]+(?!Occupant)([^\n]+)",
            r"(?m)^(\d{4}\.\d{2})$",
        ],
        
        # S-7: Occupant
        'occupant': [
            r"Occupant[:\s]+(Owner|Tenant|Vacant)",
            r"Occupancy[:\s]+(Owner|Tenant|Vacant)",
        ],
        
        # S-10: Lender/Client
        'lender_name': [
            r"(?m)^Lender/?Client[:\s]+(?!Address|File|Property)([^\n]+)",
            r"Lender[:\s]+(?!Address|Client)([^\n]+)",
            r"(?m)^Client[:\s]+(?!Address|Lender)([^\n]+)",
        ],
        
        # S-11: Property Rights
        'property_rights': [
            r"Property Rights Appraised[:\s]+([^\n]+)",
            r"Property Rights[:\s]+(Fee Simple|Leasehold)",
        ],
        
        # -------------------------------------------------------------------------
        # CONTRACT SECTION FIELDS (C-1 to C-5)
        # -------------------------------------------------------------------------
        
        # C-1: Contract Analysis
        'did_analyze_contract': [
            r"((?:did|I did|appraiser did)\s+(?:not\s+)?analyze.*contract)",
            r"Contract Analysis[:\s]+(Yes|No|Did|Did Not)",
        ],
        
        # C-2: Contract Price
        'contract_price': [
            r"Contract Price[:\s\$]+([0-9,]+(?:\.\d{2})?)",
            r"Sale Price[:\s\$]+([0-9,]+(?:\.\d{2})?)",
        ],
        'contract_date': [
            r"Date of Contract[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Contract Date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ],
        
        # C-3: Owner of Record
        'is_seller_owner': [
            r"Is.*seller.*owner of public record[:\s]*(Yes|No)",
            r"Seller.*Owner[:\s]*(Yes|No)",
        ],
        
        # C-4: Financial Assistance
        'financial_assistance': [
            r"Financial Assistance[:\s]*(Yes|No)",
            r"Loan Charges.*Concessions[:\s]*(Yes|No)",
        ],
        'financial_assistance_amount': [
            r"Financial Assistance.*\$([0-9,]+)",
            r"Concessions.*\$([0-9,]+)",
        ],
    }
    
    for field_name, field_patterns in patterns.items():
        value = None
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                break
        
        fields[field_name] = value
        if value:
            logger.debug(f"  Extracted {field_name}: {value[:50]}..." if len(str(value)) > 50 else f"  Extracted {field_name}: {value}")
        else:
            logger.debug(f"  Missing {field_name}")
    
    # Count extracted vs missing
    extracted = sum(1 for v in fields.values() if v)
    total = len(fields)
    logger.info(f"Extracted {extracted}/{total} fields")
    
    return fields


def extract_engagement_fields(text: str, logger: logging.Logger) -> Dict[str, Any]:
    """Extract fields from engagement letter text."""
    import re
    
    logger.info("Extracting engagement letter fields...")
    
    fields = {}
    
    patterns = {
        'borrower_name': [
            r"Borrower(?: Name)?[:\s]+(?!Lender|Client|File|Property|Information)([^\n]+)",
            r"Client Name[:\s]+([^\n]+)",
        ],
        'property_address': [
            r"Property Address[:\s]+(?!City|State|Zip|County|Property)(?:\( Additional Resources \) )?([^\n]+)",
            r"Subject Property[:\s]+(?!City|State|Zip|County)([^\n]+)",
            r"(?m)^(\d+\s+[A-Za-z0-9\.\s]+(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|Road|Street|Avenue|Drive).*?)$"
        ],
        'lender_name': [
            r"Lender/?Client[:\s]+(?!Address|File|Property)([^\n]+)",
            r"Lender[:\s]+(?!Address|Client)([^\n]+)",
            r"Client[:\s]+(?!Address|Lender)([^\n]+)",
        ],
        'assignment_type': [
            r"Purpose[:\s]+(Purchase|Refinance)",
            r"Transaction Type[:\s]+(Purchase|Refinance)",
        ],
    }
    
    for field_name, field_patterns in patterns.items():
        value = None
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                break
        
        fields[field_name] = value
        if value:
            logger.debug(f"  Engagement {field_name}: {value}")
    
    return fields


# ============================================================================
# RULE EXECUTION
# ============================================================================

def build_validation_context(
    appraisal_fields: Dict[str, Any],
    engagement_fields: Dict[str, Any],
    logger: logging.Logger
) -> ValidationContext:
    """Build ValidationContext from extracted fields."""
    
    logger.info("Building validation context...")
    
    # Build SubjectSection
    subject = SubjectSection(
        address=appraisal_fields.get('property_address'),
        city=appraisal_fields.get('city'),
        state=appraisal_fields.get('state'),
        zip_code=appraisal_fields.get('zip_code'),
        county=appraisal_fields.get('county'),
        borrower=appraisal_fields.get('borrower_name'),
        owner_of_public_record=appraisal_fields.get('owner_of_public_record'),
        legal_description=appraisal_fields.get('legal_description'),
        apn=appraisal_fields.get('apn'),
        tax_year=appraisal_fields.get('tax_year'),
        re_taxes=_parse_money(appraisal_fields.get('re_taxes')),
        neighborhood_name=appraisal_fields.get('neighborhood_name'),
        map_reference=appraisal_fields.get('map_reference'),
        census_tract=appraisal_fields.get('census_tract'),
        occupant=appraisal_fields.get('occupant'),
        lender_name=appraisal_fields.get('lender_name'),
        property_rights=appraisal_fields.get('property_rights'),
        # S-12 fields
        prior_sale_offered_12mo=appraisal_fields.get('offered_for_sale_12mo'),
        data_sources=appraisal_fields.get('data_source'),
    )
    
    # Build ContractSection
    contract = ContractSection(
        did_analyze_contract=_parse_bool(appraisal_fields.get('did_analyze_contract')),
        contract_price=_parse_money(appraisal_fields.get('contract_price')),
        date_of_contract=appraisal_fields.get('contract_date'),
        is_seller_owner=_parse_bool(appraisal_fields.get('is_seller_owner')),
        owner_record_data_source=appraisal_fields.get('owner_record_data_source'),
        financial_assistance=appraisal_fields.get('has_financial_assistance'),
        financial_assistance_amount=_parse_money(appraisal_fields.get('financial_assistance_amount')),
    )
    
    # Build AppraisalReport
    report = AppraisalReport(
        subject=subject,
        contract=contract,
    )
    
    # Build EngagementLetter (include parsed address components)
    engagement = EngagementLetter(
        borrower_name=engagement_fields.get('borrower_name'),
        property_address=engagement_fields.get('property_address'),
        city=engagement_fields.get('city'),  # Parsed from address
        state=engagement_fields.get('state'),  # Parsed from address
        zip_code=engagement_fields.get('zip_code'),  # Parsed from address
        lender_name=engagement_fields.get('lender_name'),
        assignment_type=engagement_fields.get('assignment_type'),
    )
    
    ctx = ValidationContext(
        report=report,
        engagement_letter=engagement,
    )
    
    logger.info("Validation context built successfully")
    return ctx


def _parse_money(value: Optional[str]) -> Optional[float]:
    """Parse money string to float."""
    if not value:
        return None
    try:
        clean = value.replace('$', '').replace(',', '').strip()
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    """Parse boolean string."""
    if not value:
        return None
    v = str(value).upper()
    if v in ('YES', 'TRUE', 'DID', '1'):
        return True
    if v in ('NO', 'FALSE', 'DID NOT', '0'):
        return False
        
    # Sentence parsing
    if 'DID NOT ANALYZE' in v:
        return False
    if 'DID ANALYZE' in v:
        return True
        
    return None


def run_all_rules(ctx: ValidationContext, logger: logging.Logger) -> list[RuleResult]:
    """Execute all registered rules against the validation context."""
    
    logger.info("=" * 60)
    logger.info("EXECUTING QC RULES (S-1 to S-12, C-1 to C-5)")
    logger.info("=" * 60)
    
    # Use the engine to execute all rules
    try:
        results = engine.execute(ctx)
        logger.info(f"Executed {len(results)} rules")
        
        # Log results
        for result in results:
            if result.status == RuleStatus.PASS:
                logger.info(f"  ✅ PASS: {result.message}")
            elif result.status == RuleStatus.FAIL:
                logger.warning(f"  ❌ FAIL: {result.message}")
            elif result.status == RuleStatus.WARNING:
                logger.warning(f"  ⚠️  WARNING: {result.message}")
            elif result.status == RuleStatus.ERROR:
                logger.error(f"  🔴 ERROR: {result.message}")
            elif result.status == RuleStatus.SKIPPED:
                logger.info(f"  ⏭️  SKIPPED: {result.message}")
                
        return results
        
    except Exception as e:
        logger.error(f"Failed to execute rules: {e}")
        return []


# ============================================================================
# MAIN TEST FUNCTION
# ============================================================================

def run_test():
    """Main test function."""
    
    # Paths
    test_dir = Path(__file__).parent / "testFile"
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    appraisal_pdf = test_dir / "apprisal_002.pdf"
    engagement_pdf = test_dir / "engagement_002.pdf"
    
    # Setup logging
    logger = setup_logging(output_dir)
    
    logger.info("=" * 70)
    logger.info("OCR EXTRACTION AND QC RULES TEST")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 70)
    
    try:
        # =====================================================================
        # STEP 1: OCR EXTRACTION
        # =====================================================================
        
        logger.info("\n" + "=" * 70)
        logger.info("STEP 1: OCR EXTRACTION")
        logger.info("=" * 70)
        
        # Extract appraisal PDF
        appraisal_text, appraisal_result = extract_pdf_text(str(appraisal_pdf), logger)
        save_extracted_text(
            appraisal_text,
            output_dir / "appraisal_extracted_text.txt",
            "apprisal_002.pdf",
            logger
        )
        
        # Extract engagement letter PDF
        engagement_text, engagement_result = extract_pdf_text(str(engagement_pdf), logger)
        save_extracted_text(
            engagement_text,
            output_dir / "engagement_extracted_text.txt",
            "engagement_002.pdf",
            logger
        )
        
        # =====================================================================
        # STEP 2: FIELD EXTRACTION
        # =====================================================================
        # Extract fields using the actual ExtractionService
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 2: EXTRACT STRUCTURED FIELDS")
        logger.info("=" * 70)
        
        extracted_data = extract_fields_from_text_new(appraisal_text, engagement_text, logger)
        
        # Save extracted fields to JSON for inspection
        fields_json_path = output_dir / "extracted_fields.json"
        with open(fields_json_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, indent=2)
        logger.info(f"Saved extracted fields to: {fields_json_path}")
        
        # Debug: Log the extracted fields
        logger.debug("Appraisal Fields:")
        for key, value in extracted_data['appraisal_fields'].items():
            logger.debug(f"  {key}: {value}")
        
        logger.debug("Engagement Fields:")
        for key, value in extracted_data['engagement_fields'].items():
            logger.debug(f"  {key}: {value}")
        
        logger.info("\n" + "=" * 70)
        logger.info("STEP 3: BUILD VALIDATION CONTEXT")
        logger.info("=" * 70)
        
        ctx = build_validation_context(extracted_data['appraisal_fields'], extracted_data['engagement_fields'], logger)
        
        # =====================================================================
        # STEP 4: EXECUTE RULES
        # =====================================================================
        
        logger.info("\n" + "=" * 70)
        logger.info("STEP 4: EXECUTE QC RULES (S-1 to S-12, C-1 to C-5)")
        logger.info("=" * 70)
        
        results = run_all_rules(ctx, logger)
        
        # Save results as JSON
        results_json = []
        for r in results:
            results_json.append({
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                "message": r.message,
                "details": r.details,
            })
        
        with open(output_dir / "rule_results.json", 'w') as f:
            json.dump(results_json, f, indent=2)
        logger.info(f"Saved rule results to: rule_results.json")
        
        # =====================================================================
        # COMPLETION
        # =====================================================================
        
        logger.info("\n" + "=" * 70)
        logger.info("TEST COMPLETED SUCCESSFULLY")
        logger.info(f"Output directory: {output_dir}")
        logger.info("=" * 70)
        logger.info("Generated files:")
        logger.info(f"  1. {output_dir / 'appraisal_extracted_text.txt'}")
        logger.info(f"  2. {output_dir / 'engagement_extracted_text.txt'}")
        logger.info(f"  3. {output_dir / 'extracted_fields.json'}")
        logger.info(f"  4. {output_dir / 'rule_results.json'}")
        logger.info(f"  5. {output_dir / 'logs' / 'test_run.log'}")
        logger.info(f"  6. {output_dir / 'logs' / 'rule_results.log'}")
        
    except Exception as e:
        logger.exception(f"Test failed with error: {e}")
        raise


if __name__ == "__main__":
    run_test()
