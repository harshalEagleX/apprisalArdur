import re
import fitz
import logging
from typing import Dict, Any, Optional

from app.ocr.ocr_pipeline import OCRPipeline

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from all pages of a PDF using specialized OCR Pipeline."""
    pipeline = OCRPipeline(force_image_ocr=True)
    try:
        result = pipeline.extract_all_pages(pdf_path)
        return pipeline.get_full_text(result.page_index)
    except Exception as e:
        logger.error(f"OCR Pipeline failed: {e}")
        # Fallback to simple extraction if something catastrophic happens
        doc = fitz.open(pdf_path)
        text = "\n\n".join([page.get_text() for page in doc])
        doc.close()
        return text


def extract_fields(text: str) -> Dict[str, Any]:
    """Extract appraisal fields using regex patterns."""
    fields = {}
    
    # Borrower Name patterns
    borrower_patterns = [
        r"Borrower[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
        r"BORROWER[:\s]+([A-Z\s]+)",
        r"Borrower Name[:\s]+([^\n]+)",
    ]
    fields['borrowerName'] = extract_first_match(text, borrower_patterns)
    
    # Property Address patterns
    address_patterns = [
        r"Property Address[:\s]+([^\n]+)",
        r"Subject Property[:\s]+([^\n]+)",
        r"Address[:\s]+(\d+[^,\n]+(?:,\s*[^,\n]+){0,2})",
    ]
    fields['propertyAddress'] = extract_first_match(text, address_patterns)
    
    # Parse address components if found
    if fields['propertyAddress']:
        address_parts = parse_address(fields['propertyAddress'])
        fields.update(address_parts)
    
    # Appraised Value patterns
    value_patterns = [
        r"Appraised Value[:\s]*\$?([\d,]+)",
        r"APPRAISED VALUE[:\s]*\$?([\d,]+)",
        r"Market Value[:\s]*\$?([\d,]+)",
        r"Opinion of Value[:\s]*\$?([\d,]+)",
    ]
    value_str = extract_first_match(text, value_patterns)
    if value_str:
        fields['appraisedValue'] = parse_money(value_str)
    
    # Sale Price patterns
    sale_patterns = [
        r"Sale Price[:\s]*\$?([\d,]+)",
        r"Contract Price[:\s]*\$?([\d,]+)",
        r"Purchase Price[:\s]*\$?([\d,]+)",
    ]
    sale_str = extract_first_match(text, sale_patterns)
    if sale_str:
        fields['salePrice'] = parse_money(sale_str)
    
    # Effective Date patterns
    date_patterns = [
        r"Effective Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"Date of Value[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        r"As of[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    fields['effectiveDate'] = extract_first_match(text, date_patterns)
    
    # Lender Name patterns
    lender_patterns = [
        r"Lender[:\s]+([^\n]+)",
        r"Client[:\s]+([^\n]+)",
        r"Lender/Client[:\s]+([^\n]+)",
    ]
    fields['lenderName'] = extract_first_match(text, lender_patterns)
    
    # Appraiser patterns
    appraiser_patterns = [
        r"Appraiser[:\s]+([^\n]+)",
        r"Signed[:\s]+([^\n]+)",
    ]
    fields['appraiserName'] = extract_first_match(text, appraiser_patterns)
    
    # License number patterns
    license_patterns = [
        r"License\s*#?\s*:?\s*([A-Z]{2}[-\s]?\d+)",
        r"State License[:\s]+([^\n]+)",
        r"Certification\s*#?\s*:?\s*([A-Z0-9-]+)",
    ]
    fields['appraiserLicenseNumber'] = extract_first_match(text, license_patterns)
    
    return fields


def extract_first_match(text: str, patterns: list) -> Optional[str]:
    """Try multiple regex patterns and return the first match."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def parse_address(address: str) -> Dict[str, str]:
    """Parse address into components."""
    result = {}
    
    # Try to extract city, state, zip
    state_zip = re.search(r'([A-Za-z\s]+),?\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)', address)
    if state_zip:
        result['city'] = state_zip.group(1).strip()
        result['state'] = state_zip.group(2)
        result['zipCode'] = state_zip.group(3)
    
    return result


def parse_money(value_str: str) -> Optional[float]:
    """Parse a money string to float."""
    try:
        # Remove commas and dollar signs
        cleaned = re.sub(r'[,$]', '', value_str)
        return float(cleaned)
    except:
        return None


def detect_form_type(text: str) -> Optional[str]:
    """Detect the appraisal form type."""
    form_patterns = {
        "1004": [r"Uniform Residential Appraisal Report", r"URAR", r"Form 1004"],
        "1025": [r"Small Residential Income Property", r"Form 1025"],
        "1073": [r"Individual Condominium", r"Form 1073"],
        "2055": [r"Exterior-Only Inspection", r"Form 2055"],
    }
    
    text_upper = text.upper()
    for form_type, patterns in form_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return form_type
    
    return None


def extract_checkboxes(text: str) -> Dict[str, bool]:
    """Extract checkbox/boolean fields from text."""
    checkboxes = {
        'isInFloodZone': False,
        'isForSale': False,
        'hasPoolOrSpa': False,
        'isCondoOrPUD': False,
        'isPud': False,
        'isManufacturedHome': False,
        'didAnalyzeContract': False,
    }
    
    text_lower = text.lower()
    
    if re.search(r'flood\s*(zone|area|hazard).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isInFloodZone'] = True
    
    if re.search(r'(for sale|currently listed|on market).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isForSale'] = True
    
    if re.search(r'(pool|spa).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['hasPoolOrSpa'] = True
    
    if re.search(r'(condo|pud|planned unit).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isCondoOrPUD'] = True
    
    if re.search(r'(manufactured|mobile|modular).{0,20}(yes|x|\[x\])', text_lower):
        checkboxes['isManufacturedHome'] = True
    
    return checkboxes


def calculate_confidence(fields: Dict[str, Any], raw_text: str) -> float:
    """Calculate a confidence score based on extraction quality."""
    score = 0.5  # Base score
    
    key_fields = ['borrowerName', 'propertyAddress', 'appraisedValue']
    for field in key_fields:
        if fields.get(field):
            score += 0.1
            
    optional_fields = ['lenderName', 'effectiveDate', 'salePrice', 'appraiserName']
    for field in optional_fields:
        if fields.get(field):
            score += 0.05
    
    if len(raw_text) < 1000:
        score -= 0.2
    
    return max(0.0, min(1.0, score))
