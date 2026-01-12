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

def extract_pdf_text(pdf_path: str, logger: logging.Logger) -> tuple[str, Any]:
    """
    Extract text from PDF using ExtractionService logic (Text-First).
    
    Returns:
        Tuple of (full_text, extraction_result_placeholder)
    """
    logger.info(f"=" * 60)
    logger.info(f"EXTRACTING: {os.path.basename(pdf_path)}")
    logger.info(f"=" * 60)
    
    if not os.path.exists(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Use ExtractionService to simulate actual production flow
    from app.services.extraction_service import ExtractionService
    service = ExtractionService()
    
    logger.info("Starting extraction using ExtractionService (Text-First)...")
    start_time = datetime.now()
    
    # Call internal method _extract_from_pdf to get text
    # Note: We don't get detailed page-by-page OCR stats here easily without modifying service,
    # but we care about the TEXT result matching production.
    full_text, total_pages = service._extract_from_pdf(pdf_path)
    
    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"Extraction time: {duration:.0f}ms")
    logger.info(f"Total pages: {total_pages}")
    
    # Mock a result object to satisfy the test script interface
    class MockResult:
        def __init__(self, pages):
            self.total_pages = pages
            self.extraction_time_ms = 0
            self.page_details = []
            self.warnings = []
            self.page_index = {}
            
    result = MockResult(total_pages)
    
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
            elif result.status == RuleStatus.VERIFY:
                logger.warning(f"  🔍 VERIFY: {result.message}")
            elif result.status == RuleStatus.SKIPPED:
                logger.info(f"  ⏭️  SKIPPED: {result.message}")
                
        return results
        
    except Exception as e:
        logger.error(f"Failed to execute rules: {e}")
        return []



# ============================================================================
# MAIN TEST FUNCTION
# ============================================================================

def run_single_test(appraisal_pdf: Path, engagement_pdf: Path, output_dir: Path, logger) -> dict:
    """
    Run test for a single appraisal/engagement pair.
    Returns test results summary.
    """
    test_name = appraisal_pdf.stem  # e.g., "apprisal_002"
    
    logger.info("=" * 70)
    logger.info(f"TESTING: {test_name}")
    logger.info("=" * 70)
    
    result = {
        "test_name": test_name,
        "appraisal_file": appraisal_pdf.name,
        "engagement_file": engagement_pdf.name,
        "ocr_success": False,
        "rules_executed": 0,
        "pass_count": 0,
        "fail_count": 0,
        "warning_count": 0,
        "verify_count": 0,
        "skipped_count": 0,
        "errors": []
    }
    
    try:
        # STEP 1: OCR EXTRACTION
        logger.info("  Step 1: OCR Extraction...")
        appraisal_text, appraisal_result = extract_pdf_text(str(appraisal_pdf), logger)
        engagement_text, engagement_result = extract_pdf_text(str(engagement_pdf), logger)
        
        result["ocr_success"] = True
        result["appraisal_pages"] = appraisal_result.total_pages
        result["appraisal_chars"] = len(appraisal_text)
        result["engagement_pages"] = engagement_result.total_pages
        result["engagement_chars"] = len(engagement_text)

        
        # Save extracted text
        save_extracted_text(
            appraisal_text,
            output_dir / f"{test_name}_appraisal.txt",
            appraisal_pdf.name,
            logger
        )
        save_extracted_text(
            engagement_text,
            output_dir / f"{test_name}_engagement.txt",
            engagement_pdf.name,
            logger
        )
        
        # STEP 2: FIELD EXTRACTION
        logger.info("  Step 2: Field Extraction...")
        extracted_data = extract_fields_from_text_new(appraisal_text, engagement_text, logger)
        
        # Save fields
        with open(output_dir / f"{test_name}_fields.json", 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, indent=2)
        
        # STEP 3: BUILD CONTEXT
        logger.info("  Step 3: Building Validation Context...")
        ctx = build_validation_context(
            extracted_data['appraisal_fields'], 
            extracted_data['engagement_fields'], 
            logger
        )
        
        # STEP 4: EXECUTE RULES
        logger.info("  Step 4: Executing QC Rules...")
        rules_results = run_all_rules(ctx, logger)
        
        # Count by status
        for r in rules_results:
            status = r.status.value if hasattr(r.status, 'value') else str(r.status)
            if status == "PASS":
                result["pass_count"] += 1
            elif status == "FAIL":
                result["fail_count"] += 1
            elif status == "WARNING":
                result["warning_count"] += 1
            elif status == "VERIFY":
                result["verify_count"] += 1
            elif status == "SKIPPED":
                result["skipped_count"] += 1
        
        result["rules_executed"] = len(rules_results)
        
        # Save rule results
        results_json = [{
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
            "message": r.message,
        } for r in rules_results]
        
        with open(output_dir / f"{test_name}_rules.json", 'w') as f:
            json.dump(results_json, f, indent=2)
        
        logger.info(f"  ✓ Completed: {result['pass_count']} PASS, {result['fail_count']} FAIL, "
                    f"{result['warning_count']} WARNING, {result['verify_count']} VERIFY")
        
    except Exception as e:
        result["errors"].append(str(e))
        logger.exception(f"  ✗ Test failed: {e}")
    
    return result


def run_test():
    """Main test function - runs tests on all file pairs in testFile directory."""
    
    # Paths
    test_dir = Path(__file__).parent / "testFile"
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    # Setup logging
    logger = setup_logging(output_dir)
    
    logger.info("=" * 70)
    logger.info("OCR EXTRACTION AND QC RULES TEST - ALL FILES")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 70)
    
    # Find all appraisal/engagement pairs
    appraisal_files = sorted(test_dir.glob("apprisal_*.pdf"))
    
    all_results = []
    
    for appraisal_pdf in appraisal_files:
        # Find matching engagement file
        file_num = appraisal_pdf.stem.split("_")[-1]  # e.g., "002"
        engagement_pdf = test_dir / f"engagement_{file_num}.pdf"
        
        if not engagement_pdf.exists():
            logger.warning(f"No matching engagement file for {appraisal_pdf.name}")
            continue
        
        try:
            result = run_single_test(appraisal_pdf, engagement_pdf, output_dir, logger)
            all_results.append(result)
        except Exception as e:
            logger.exception(f"Fatal error testing {appraisal_pdf.name}: {e}")
    
    # =========================================================================
    # SUMMARY REPORT
    # =========================================================================
    
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY REPORT")
    logger.info("=" * 70)
    
    total_pass = sum(r["pass_count"] for r in all_results)
    total_fail = sum(r["fail_count"] for r in all_results)
    total_warning = sum(r["warning_count"] for r in all_results)
    total_verify = sum(r["verify_count"] for r in all_results)
    total_skipped = sum(r["skipped_count"] for r in all_results)
    total_rules = sum(r["rules_executed"] for r in all_results)
    
    print("\n" + "=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)
    
    for r in all_results:
        status = "✓ OK" if not r["errors"] else "✗ FAILED"
        print(f"\n{r['test_name']}:")
        print(f"  Status: {status}")
        print(f"  OCR: {r.get('appraisal_pages', '?')} appraisal pages, "
              f"{r.get('engagement_pages', '?')} engagement pages")
        print(f"  Rules: {r['rules_executed']} executed")
        print(f"    PASS: {r['pass_count']}")
        print(f"    FAIL: {r['fail_count']}")
        print(f"    WARNING: {r['warning_count']}")
        print(f"    VERIFY: {r['verify_count']}")
        print(f"    SKIPPED: {r['skipped_count']}")
        if r["errors"]:
            print(f"  Errors: {r['errors']}")
    
    print("\n" + "-" * 70)
    print("TOTALS:")
    print(f"  Files tested: {len(all_results)}")
    print(f"  Total rules executed: {total_rules}")
    print(f"  Total PASS: {total_pass}")
    print(f"  Total FAIL: {total_fail}")
    print(f"  Total WARNING: {total_warning}")
    print(f"  Total VERIFY: {total_verify}")
    print(f"  Total SKIPPED: {total_skipped}")
    print("=" * 70)
    
    # Save summary to JSON
    summary = {
        "timestamp": datetime.now().isoformat(),
        "files_tested": len(all_results),
        "total_rules": total_rules,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "total_warning": total_warning,
        "total_verify": total_verify,
        "total_skipped": total_skipped,
        "results": all_results
    }
    
    with open(output_dir / "test_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"\nSummary saved to: {output_dir / 'test_summary.json'}")
    logger.info("TEST COMPLETED")
    
    return all_results


if __name__ == "__main__":
    run_test()

