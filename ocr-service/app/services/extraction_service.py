"""
Extraction Service for QC Document Intelligence

This service extracts FACTS ONLY from appraisal documents.
It performs mechanical comparison but NEVER:
- Decides pass or fail
- Generates rejection questions
- Applies business rules
- Classifies severity

All extracted facts and differences are passed to Java for processing.
"""

import re
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime

import fitz  # PyMuPDF

from app.models.difference_report import (
    DifferenceReport, FieldStatus, FieldDifference,
    SubjectSectionExtract, ContractSectionExtract, EngagementLetterExtract
)
from app.ocr.ocr_pipeline import OCRPipeline

logger = logging.getLogger(__name__)


class ExtractionService:
    """
    Document intelligence service for pure fact extraction.
    Python sees - Java thinks - Humans decide.
    """
    
    def __init__(self):
        self.patterns = self._compile_patterns()
        # Enable image preprocessing for maximum OCR quality
        self.ocr_pipeline = OCRPipeline(
            use_tesseract=True,
            force_image_ocr=False,
            use_preprocessing=True  # Enable preprocessing pipeline
        )
    
    def extract_and_compare(
        self,
        pdf_path: str,
        engagement_letter_text: Optional[str] = None,
        env_content: Optional[bytes] = None
    ) -> DifferenceReport:
        """
        Main extraction method.
        
        Args:
            pdf_path: Path to appraisal PDF
            engagement_letter_text: Optional engagement letter text for comparison
            env_content: Optional ENV file content
            
        Returns:
            DifferenceReport with extracted facts and detected differences
        """
        import time
        start_time = time.time()
        
        report = DifferenceReport()
        
        # Step 1: Determine extraction method
        if env_content:
            report.env_file_present = True
            try:
                extracted_text = self._parse_env(env_content)
                report.env_file_readable = True
                report.extraction_method = "env"
            except Exception as e:
                logger.warning(f"ENV parsing failed: {e}")
                report.env_file_readable = False
                report.add_warning(f"ENV file present but unreadable: {str(e)}")
                extracted_text = self._extract_from_pdf(pdf_path)
                report.extraction_method = "pymupdf"
        else:
            extracted_text, total_pages = self._extract_from_pdf(pdf_path)
            report.total_pages = total_pages
            report.extraction_method = "pymupdf"
        
        if not extracted_text or len(extracted_text.strip()) < 100:
            report.success = False
            report.add_warning("Insufficient text extracted from document")
            report.unreadable_sections.append("ENTIRE_DOCUMENT")
            report.processing_time_ms = int((time.time() - start_time) * 1000)
            return report
        
        # Step 2: Extract Subject Section (S-1 to S-12)
        report.subject_section = self._extract_subject_section(extracted_text)
        
        # Step 3: Extract Contract Section (C-1 to C-5)
        report.contract_section = self._extract_contract_section(extracted_text)
        
        # Step 4: Parse engagement letter if provided
        if engagement_letter_text:
            report.engagement_letter_present = True
            report.engagement_letter = self._extract_engagement_letter(engagement_letter_text)
            
            # Step 5: Detect differences (mechanical comparison only)
            self._detect_differences(report)
        
        report.processing_time_ms = int((time.time() - start_time) * 1000)
        return report
    
    def _extract_from_pdf(self, pdf_path: str) -> Tuple[str, int]:
        """Extract text from PDF using PyMuPDF with optional preprocessing."""
        text_parts = []
        total_pages = 0
        
        try:
            # Use preprocessing pipeline if available for better quality
            result = self.ocr_pipeline.extract_with_preprocessing(pdf_path) if hasattr(self.ocr_pipeline, 'extract_with_preprocessing') else self.ocr_pipeline.extract_all_pages(pdf_path)
            # Combine text
            return self.ocr_pipeline.get_full_text(result.page_index), result.total_pages
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise
        
        return "\n\n".join(text_parts), total_pages
    
    def _parse_env(self, env_content: bytes) -> str:
        """Parse ENV file to extract text. Placeholder for future implementation."""
        # TODO: Implement ENV (XML) parsing
        raise NotImplementedError("ENV parsing not yet implemented")
    
    # =========================================================================
    # Subject Section Extraction (S-1 to S-12)
    # =========================================================================
    
    def extract_subject_section(self, text: str) -> SubjectSectionExtract:
        """Extract facts from Subject Section."""
        subject = SubjectSectionExtract()
        
        # IMPORTANT: Only extract from the actual report section, not table of contents
        # Find the "Uniform Residential Appraisal Report" header and extract from there
        report_start = re.search(r"Uniform Residential Appraisal Report", text, re.IGNORECASE)
        if report_start:
            # Work with text starting from the report header
            text = text[report_start.start():]
        
         
        # S-1: Property Address
        # Anchor-based extraction for tabular layout: "Property Address ... City ... State ... Zip Code"
        # We look for the "Property Address" anchor and then extract the tokens between known column headers.
        
        # 1. Extract the line containing Property Address WITH City/State/Zip components
        # Look for a line that has "Property Address" AND contains "City" and "State" keywords
        # Handle both "Property Address:" and "Property Address ="
        addr_line_match = re.search(
            r"Property Address\s*[=:\s]+(.*?City.*?State.*?(?:Zip|ZIP).*)", 
            text, 
            re.IGNORECASE | re.MULTILINE
        )
        
        if addr_line_match:
            full_line = addr_line_match.group(1).strip()
            
            # Split by known headers found in the line
            # Expected formats: 
            # - "123 Main St   City  Anytown   State  CA   Zip Code  12345"
            # - "25126 N Jack Tone Rd City Acampo State CA ZIP Code 95220"
            
            # Extract Zip (handle both "Zip Code" and "ZIP Code")
            zip_match = re.search(r"(?:Zip\s*Code|ZIP\s*Code|Zip)[:\s]+(\d{5}(?:-\d{4})?)", full_line, re.IGNORECASE)
            if zip_match:
                subject.zip_code = zip_match.group(1)
                full_line = full_line[:zip_match.start()] # Truncate processed part
            
            # Extract State (case insensitive, capture 2 letter state code)
            state_match = re.search(r"(?:State|STATE)[:\s]+([A-Z]{2})", full_line, re.IGNORECASE)
            if state_match:
                subject.state = state_match.group(1).upper()  # Ensure uppercase
                full_line = full_line[:state_match.start()]
            
            # Extract City (everything between "City" keyword and where State starts, or end of remaining line)
            city_match = re.search(r"(?:City|CITY)[:\s]+(.*?)(?:\s+(?:State|STATE)|$)", full_line, re.IGNORECASE)
            if city_match:
                subject.city = city_match.group(1).strip()
                # Remove the City part from full_line
                full_line = re.sub(r"(?:City|CITY)[:\s]+.*", '', full_line, flags=re.IGNORECASE)
            
            # What remains is the Street Address
            subject.property_address = full_line.strip()
            
        else:
             # Fallback to existing logic if simple line extraction fails
             subject.property_address = self._extract_field(text, [
                r"Property Address[:\s]+(?!City|State|Zip|County|Borrower|Lender|File)([^\n]+)",
                r"Subject Property[:\s]+(?!City|State|Zip|County)([^\n]+)",
             ])
        
        subject.county = self._extract_field(text, [
            r"County[:\s]+([A-Za-z\s]+?)(?:\n|$)",
        ])
        
        # S-2: Borrower
        subject.borrower_name = self._extract_field(text, [
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)([^\n]+)",
            r"BORROWER[:\s]+(?!LENDER|CLIENT)([^\n]+)",
            r"Borrower Name[:\s]+(?!Information)([^\n]+)",
        ])
        
        subject.co_borrower_name = self._extract_field(text, [
            r"Co-?Borrower[:\s]+([^\n]+)",
            r"CO-?BORROWER[:\s]+([^\n]+)",
        ])
        
        # S-3: Owner of Public Record
        # Try multiple patterns - the field may appear in different formats
        subject.owner_of_public_record = self._extract_field(text, [
            r"Owner of Public Record[:\s]+([^\n]+)",
            r"Current Owner[:\s]+([^\n]+)",
            # In some forms, owner appears in URAR addenda 
            r"URAR:\s*Owner[:\s]+([^\n]+)",
            # For purchase transactions where seller=owner, extract seller name
            r"Seller[:\s]+(?!the owner)([^\n]{3,50})(?!\s*is|\s*the)",
        ])
        
        # Also check if "seller is owner of public record" checkbox is marked
        if not subject.owner_of_public_record:
            seller_is_owner = re.search(
                r"property seller the owner of public record\?\s*(?:XX|x|\[X\]|\[x\])\s*Yes",
                text, re.IGNORECASE
            )
            if seller_is_owner:
                # Seller is owner - try to find seller name
                seller_match = self._extract_field(text, [
                    r"Seller[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
                    r"SELLERS?[:\s]+([^\n]{5,50})",
                ])
                if seller_match:
                    subject.owner_of_public_record = seller_match
                else:
                    # Mark as confirmed via contract checkbox
                    subject.owner_of_public_record = "[Confirmed via Contract - Seller is Owner]"
        
        # S-4: Legal Description, APN, Taxes
        subject.legal_description = self._extract_field(text, [
            r"Legal Description[:\s]+([^\n]+)",
        ])
        
        subject.assessors_parcel_number = self._extract_field(text, [
            r"(?:Assessor'?s?\s*)?Parcel\s*(?:#|Number|No\.?)[:\s]+([^\n]+)",
            r"APN[:\s]+([^\n]+)",
        ])
        
        subject.tax_year = self._extract_field(text, [
            r"Tax Year[:\s]+(\d{4})",
        ])
        
        # S-4: R.E. Taxes - Handle multiple formats including "$ 487" with space
        taxes_str = self._extract_field(text, [
            r"R\.?E\.?\s*Taxes\s*\$?\s*([\d,]+)",  # Handle "R.E. Taxes $ 487" (with space after $)
            r"Real Estate Taxes\s*\$?\s*([\d,]+)",
            # Combined line format: "Tax Year 2024 R.E. Taxes $ 487"
            r"Tax Year\s+\d{4}\s+R\.?E\.?\s*Taxes\s*\$?\s*([\d,]+)",
        ])
        if taxes_str:
            subject.real_estate_taxes = self._parse_money(taxes_str)
        
        # S-5: Neighborhood Name
        subject.neighborhood_name = self._extract_field(text, [
            r"Neighborhood Name[:\s]+([^\n]+)",
            r"Neighborhood[:\s]+([^\n]+?)(?:\s*Location|$)",
        ])
        
        # S-6: Map Reference and Census Tract
        subject.map_reference = self._extract_field(text, [
            r"Map Reference[:\s]+([^\n]+)",
            r"Map Ref[:\s]+([^\n]+)",
        ])
        
        subject.census_tract = self._extract_field(text, [
            r"Census Tract[:\s]+(?!Occupant)(\d{4}\.\d{2})",
            r"Census Tract[:\s]+(?!Occupant)([^\n]+)",
            r"(?m)^(\d{4}\.\d{2})$",
        ])
        
        # S-7: Occupant Status
        occupant_text = text.lower()
        # Expanded patterns for OCR noise: [x], [X], X, ><, ]X, X]
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        
        if re.search(rf"{check_pattern}\s*owner|owner\s*{check_pattern}", occupant_text):
            subject.occupant_status = "Owner"
        elif re.search(rf"{check_pattern}\s*tenant|tenant\s*{check_pattern}", occupant_text):
            subject.occupant_status = "Tenant"
        elif re.search(rf"{check_pattern}\s*vacant|vacant\s*{check_pattern}", occupant_text):
            subject.occupant_status = "Vacant"
        
        # S-8: Special Assessments
        special_str = self._extract_field(text, [
            r"Special Assessments[:\s]*\$?([\d,]+)",
        ])
        if special_str:
            subject.special_assessments = self._parse_money(special_str)
        
        # S-9: PUD and HOA
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        subject.is_pud_checked = bool(re.search(rf"{check_pattern}\s*PUD|PUD\s*{check_pattern}", text, re.I))
        
        hoa_str = self._extract_field(text, [
            r"HOA[:\s]*\$?([\d,]+)",
            r"HOA Dues[:\s]*\$?([\d,]+)",
        ])
        if hoa_str:
            subject.hoa_dues = self._parse_money(hoa_str)
        
        if "per month" in text.lower():
            subject.hoa_period = "Per Month"
        elif "per year" in text.lower() or "annual" in text.lower():
            subject.hoa_period = "Per Year"
        
        # S-10: Lender/Client - Extract from appraisal report
        # Format can be: "Lender/Client — United American Mortgage Corporation Address ..."
        # Need to stop before "Address" and remove prefix characters like "—"
        subject.lender_name = self._extract_field(text, [
            # Capture company name, stop before "Address"
            r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union))(?:\s+Address|$|\n)",
            # Fallback: just capture until Address keyword
            r"Lender/?Client[\s—:-]+([^A]+)(?:Address|\n)",
        ])
        
        # Clean up lender name - remove leading/trailing noise
        if subject.lender_name:
            # Remove any prefix like "—" or extra spaces
            subject.lender_name = re.sub(r'^[\s—-]+', '', subject.lender_name).strip()
            # Remove "Address" if it got captured
            subject.lender_name = re.sub(r'\s*Address.*$', '', subject.lender_name, flags=re.IGNORECASE).strip()
        
        subject.lender_address = self._extract_field(text, [
            r"(?:Lender/?Client|Lender)\s+Address[:\s]+([^\n]+)",
            r"Address\s+(\d+[^\n]+)",
        ])
        
        # S-11: Property Rights
        rights_text = text.lower()
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        
        if re.search(rf"{check_pattern}\s*fee simple|fee simple\s*{check_pattern}", rights_text):
            subject.property_rights = "Fee Simple"
        elif re.search(rf"{check_pattern}\s*leasehold|leasehold\s*{check_pattern}", rights_text):
            subject.property_rights = "Leasehold"
        elif re.search(rf"{check_pattern}\s*de minimis|de minimis\s*{check_pattern}", rights_text):
            subject.property_rights = "De Minimis PUD"
        
        # S-12: Prior Listing/Sale History - Checkbox Detection
        # OCR formats can be:
        #   "x Yes | | No" (x before Yes = Yes checked)
        #   "| | Yes x No" (x before No = No checked)
        #   ">< Yes | | No" (>< is filled checkbox)
        #   "[X] Yes [ ] No" or similar
        
        # Look for the specific question text and nearby checkbox indicators
        prior_sale_match = re.search(
            r"offered for sale.*?(?:in the twelve months|12 months).*?\?"
            r".*?(x|X|><|\[x\]|\[X\])\s*(Yes|No)",
            text, re.IGNORECASE | re.DOTALL
        )
        
        if prior_sale_match:
            answer = prior_sale_match.group(2).upper()
            subject.offered_for_sale_12mo = (answer == "YES")
        else:
            # Try alternative pattern: checkbox symbol directly before Yes/No
            yes_checked = re.search(r"(x|X|><|\[x\]|\[X\])\s*Yes\s*\|?\s*\|?\s*No", text)
            no_checked = re.search(r"Yes\s*\|?\s*\|?\s*(x|X|><|\[x\]|\[X\])\s*No", text)
            
            if yes_checked:
                subject.offered_for_sale_12mo = True
            elif no_checked:
                subject.offered_for_sale_12mo = False
            # else: remains None (not detected)
        
        subject.data_source = self._extract_field(text, [
            r"Data Source[s]?[:\s]+([^\n]+)",
        ])
        
        subject.mls_number = self._extract_field(text, [
            r"MLS[:\s#]+([A-Z0-9]+)",
        ])
        
        dom_str = self._extract_field(text, [
            r"DOM[:\s]+(\d+)",
            r"Days on Market[:\s]+(\d+)",
        ])
        if dom_str:
            try:
                subject.days_on_market = int(dom_str)
            except ValueError:
                pass
        
        list_price_str = self._extract_field(text, [
            r"List(?:ing)? Price[:\s]*\$?([\d,]+)",
        ])
        if list_price_str:
            subject.list_price = self._parse_money(list_price_str)
        
        subject.list_date = self._extract_field(text, [
            r"List(?:ing)? Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
        ])
        
        return subject
    
    # =========================================================================
    # Contract Section Extraction (C-1 to C-5)
    # =========================================================================
    
    def extract_contract_section(self, text: str) -> ContractSectionExtract:
        """Extract facts from Contract Section."""
        contract = ContractSectionExtract()
        
        # C-1: Assignment Type and Contract Analysis
        text_lower = text.lower()
        
        # Detect assignment type
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        
        purchase_checked = bool(re.search(rf"{check_pattern}\s*purchase|purchase\s*{check_pattern}", text_lower))
        refinance_checked = bool(re.search(rf"{check_pattern}\s*refin|refin\s*{check_pattern}", text_lower))
        
        if purchase_checked and refinance_checked:
            contract.assignment_type = "Both_Checked"  # Flag for Java to handle
        elif purchase_checked:
            contract.assignment_type = "Purchase"
        elif refinance_checked:
            contract.assignment_type = "Refinance"
        
        # Did analyze contract
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        if re.search(rf"{check_pattern}\s*did\s*analyze|did\s*analyze\s*{check_pattern}", text_lower) and not "did not" in text_lower:
            contract.did_analyze_contract = True
        elif re.search(rf"{check_pattern}\s*did not\s*analyze|did not\s*analyze\s*{check_pattern}", text_lower):
            contract.did_analyze_contract = False
        # Fallback for missing boolean boxes (text search)
        elif "did not analyze" in text_lower:
             contract.did_analyze_contract = False
        elif "did analyze" in text_lower or "i did analyze" in text_lower:
             contract.did_analyze_contract = True
        
        # Sale type
        sale_types = ["Arms-Length", "Non Arms-Length", "REO", "Short Sale", "Court Ordered"]
        check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
        for sale_type in sale_types:
            if re.search(rf"{check_pattern}\s*{sale_type}|{sale_type}\s*{check_pattern}", text, re.I):
                contract.sale_type = sale_type
                break
        
        # C-2: Contract Price and Date
        price_str = self._extract_field(text, [
            r"Contract Price[:\s]*\$?([\d,]+)",
            r"Sale Price[:\s]*\$?([\d,]+)",
        ])
        if price_str:
            contract.contract_price = self._parse_money(price_str)
        # C-3: Owner of Record - Is seller owner of public record?
        # OCR format: "Is the property seller the owner of public record? XX Yes | No Data Source(s) County / Contract"
        # XX before Yes = Yes checked, XX before No = No checked
        owner_check_pattern = r"seller.*owner.*(?:public record|record)\?\s*(XX|X|><|\[X\]|\[x\])\s*(Yes|No)"
        owner_match = re.search(owner_check_pattern, text, re.IGNORECASE)
        if owner_match:
            answer = owner_match.group(2).upper()
            contract.is_seller_owner_of_record = (answer == "YES")
        else:
            # Alternative patterns
            if re.search(r"seller.*owner.*\?\s*(?:XX|X|><)\s*Yes", text, re.IGNORECASE):
                contract.is_seller_owner_of_record = True
            elif re.search(r"seller.*owner.*\?\s*(?:XX|X|><)\s*No", text, re.IGNORECASE):
                contract.is_seller_owner_of_record = False
            # Fallback: check if Yes is marked anywhere near the question
            elif re.search(r"owner of public record.*XX\s*Yes", text, re.IGNORECASE):
                contract.is_seller_owner_of_record = True
        
        # C-3: Data Source extraction - "Data Source(s) County / Contract"
        contract.owner_record_data_source = self._extract_field(text, [
            r"Data Source\(?s?\)?[:\s]+([^\n]+?)(?:\s*\||$|\n)",
            r"Data Source\(?s?\)?[:\s]+(.+?)(?:Is the|$)",
        ])
        # Clean up data source
        if contract.owner_record_data_source:
            # Remove trailing checkbox artifacts
            contract.owner_record_data_source = re.sub(r'\s*\[?\s*\|?\s*$', '', contract.owner_record_data_source).strip()
        
        # C-4: Financial Assistance - checkbox detection
        # OCR format: "|s there any financial assistance...? [| Yes No" (No checked when | before Yes)
        # Or: "financial assistance...? [| Yes  x No" (x before No = No checked)
        
        # Look for the financial assistance question
        fin_assist_match = re.search(
            r"financial assistance.*\?.*?(x|X|XX|><|\[x\]|\[X\])\s*(Yes|No)",
            text, re.IGNORECASE
        )
        if fin_assist_match:
            answer = fin_assist_match.group(2).upper()
            contract.has_financial_assistance = (answer == "YES")
        else:
            # Alternative: check for "No" with amount $0 as indicator of No
            if re.search(r"financial assistance.*\$\s*0|no financial assistance", text, re.IGNORECASE):
                contract.has_financial_assistance = False
            # Check for Yes checkbox near financial assistance
            elif re.search(r"financial assistance.*(?:XX|X|><)\s*Yes", text, re.IGNORECASE):
                contract.has_financial_assistance = True
        
        # C-4: Financial Assistance Amount
        assist_str = self._extract_field(text, [
            r"items to be paid\.\s*\$?\s*([\d,]+)",
            r"(?:Financial Assistance|Concessions?)[:\s]*\$?\s*([\d,]+)",
            r"\$\s*([\d,]+)\s*;.*financial assistance",
        ])
        if assist_str:
            contract.financial_assistance_amount = self._parse_money(assist_str)
        
        # C-5: Personal Property
        # Look for personal property items in text
        pp_match = re.search(r"Personal Property[:\s]+([^\n]+)", text, re.I)
        if pp_match:
            items_text = pp_match.group(1)
            # Split by common delimiters
            items = [i.strip() for i in re.split(r"[,;]", items_text) if i.strip()]
            contract.personal_property_items = items
        
        return contract
    
    # =========================================================================
    # Engagement Letter Extraction
    # =========================================================================
    
    def extract_engagement_letter(self, text: str) -> EngagementLetterExtract:
        """Extract facts from engagement letter text."""
        letter = EngagementLetterExtract()
        
        # Property Address
        letter.property_address = self._extract_field(text, [
            r"Property Address[:\s]+(?!City|State|Zip|County|Property)(?:\( Additional Resources \) )?([^\n]+)",
            r"Subject Property[:\s]+(?!City|State|Zip|County)([^\n]+)",
            # Fallback
            r"(?m)^(\d+\s+[A-Za-z0-9\.\s]+(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|Road|Street|Avenue|Drive).*?)$"
        ])
        
        if letter.property_address:
            parts = self._parse_address_components(letter.property_address)
            letter.city = parts.get("city")
            letter.state = parts.get("state")
            letter.zip_code = parts.get("zip_code")
        
        letter.county = self._extract_field(text, [r"County[:\s]+([^\n]+)"])
        
        # Borrower - Find "Borrower Name:" and capture names
        # May span multiple lines, stop at:
        # 1. Any field label with colon (Phone:, Cell Phone:, Work Phone:, etc.)
        # 2. "Equity Solutions" section
        # Format examples:
        #   "Borrower Name: Name1; Name2\n\nName3; Name4\n\nEquity Solutions..."
        #   "Borrower Name: Name1\nPhone: ..."
        borrower_match = re.search(
            r"Borrower\s+Name[:\s]+"   # Match "Borrower Name:"
            r"([\s\S]+?)"              # Capture content (including newlines) non-greedy
            r"(?=\n\s*(?:"             # Lookahead: stop before...
            r"[A-Z][a-z]*(?:\s+[A-Z][a-z]*)?\s*:"  # Any label with colon (Phone:, Cell Phone:, etc.)
            r"|Equity Solutions"        # Or "Equity Solutions" 
            r"))",
            text,
            re.IGNORECASE
        )
        if borrower_match:
            raw = borrower_match.group(1)
            # Normalize: remove extra whitespace, split by semicolon, clean, rejoin
            names = [n.strip() for n in ' '.join(raw.split()).split(';') if n.strip()]
            letter.borrower_name = '; '.join(names)
        
        letter.co_borrower_name = self._extract_field(text, [
            r"Co-?Borrower[:\s]+([^\n]+)",
        ])
        
        # Lender/Client - Extract from engagement letter
        # Format: "Client: United American Mortgage Corporation Client Address: ..."
        # Need to stop before "Client Address" or "Address"
        letter.lender_name = self._extract_field(text, [
            # Match "Client:" and capture until "Client Address" or newline
            r"Client[:\s]+([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union)[A-Za-z\s]*)(?=\s+Client Address|\s*$|\n)",
            # Simpler: Client: followed by company name, stop at Address
            r"Client[:\s]+([^:]+?)(?:\s+Client Address|\s+Address|\n)",
            # Lender/Client pattern
            r"Lender/?Client[:\s]+(?!Address)([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union))",
        ])
        
        # Clean up lender name - remove trailing noise
        if letter.lender_name:
            # Remove any "Client Address" that might have been captured
            letter.lender_name = re.sub(r'\s*Client Address.*$', '', letter.lender_name, flags=re.IGNORECASE).strip()
            # Remove trailing punctuation
            letter.lender_name = letter.lender_name.rstrip('.,;:')
        
        letter.lender_address = self._extract_field(text, [
            r"Client Address[:\s]+([^\n]+)",
            r"Lender Address[:\s]+([^\n]+)",
        ])
        
        # Transaction type
        text_lower = text.lower()
        if "purchase" in text_lower:
            letter.assignment_type = "Purchase"
        elif "refinance" in text_lower or "refi" in text_lower:
            letter.assignment_type = "Refinance"
        
        # Loan type
        if "fha" in text_lower:
            letter.loan_type = "FHA"
        elif "usda" in text_lower:
            letter.loan_type = "USDA"
        elif "va" in text_lower:
            letter.loan_type = "VA"
        else:
            letter.loan_type = "Conventional"
        
        # Contract details (if purchase)
        price_str = self._extract_field(text, [
            r"(?:Contract|Purchase|Sale) Price[:\s]*\$?([\d,]+)",
        ])
        if price_str:
            letter.contract_price = self._parse_money(price_str)
        
        letter.seller_name = self._extract_field(text, [
            r"Seller[:\s]+([^\n]+)",
        ])
        
        conc_str = self._extract_field(text, [
            r"Concessions?[:\s]*\$?([\d,]+)",
        ])
        if conc_str:
            letter.concessions_amount = self._parse_money(conc_str)
        
        return letter
    
    # =========================================================================
    # Difference Detection (Mechanical Comparison Only)
    # =========================================================================
    
    def _detect_differences(self, report: DifferenceReport):
        """
        Detect differences between appraisal report and engagement letter.
        This is MECHANICAL COMPARISON ONLY - no business logic or decisions.
        """
        subject = report.subject_section
        contract = report.contract_section
        letter = report.engagement_letter
        
        if not letter:
            return
        
        # S-1: Property Address comparison
        self._compare_field(
            report, "property_address",
            subject.property_address, letter.property_address
        )
        self._compare_field(report, "city", subject.city, letter.city)
        self._compare_field(report, "state", subject.state, letter.state)
        self._compare_field(report, "zip_code", subject.zip_code, letter.zip_code)
        self._compare_field(report, "county", subject.county, letter.county)
        
        # S-2: Borrower comparison
        self._compare_field(
            report, "borrower_name",
            subject.borrower_name, letter.borrower_name
        )
        self._compare_field(
            report, "co_borrower_name",
            subject.co_borrower_name, letter.co_borrower_name
        )
        
        # S-10: Lender comparison
        self._compare_field(
            report, "lender_name",
            subject.lender_name, letter.lender_name
        )
        self._compare_field(
            report, "lender_address",
            subject.lender_address, letter.lender_address
        )
        
        # C-1: Assignment type comparison
        self._compare_field(
            report, "assignment_type",
            contract.assignment_type, letter.assignment_type
        )
        
        # C-2: Contract price comparison (if purchase)
        if letter.assignment_type == "Purchase":
            self._compare_field(
                report, "contract_price",
                str(contract.contract_price) if contract.contract_price else None,
                str(letter.contract_price) if letter.contract_price else None
            )
        
        # C-4: Concessions comparison
        self._compare_field(
            report, "concessions_amount",
            str(contract.financial_assistance_amount) if contract.financial_assistance_amount else None,
            str(letter.concessions_amount) if letter.concessions_amount else None
        )
        
        # Flag special conditions for Java to handle
        # S-11: Property Rights (Leasehold triggers escalation - but Java decides that)
        if subject.property_rights:
            report.add_difference(
                field_name="property_rights",
                status=FieldStatus.PRESENT,
                report_value=subject.property_rights,
                details={"section": "S-11"}
            )
        
        # S-4: Real Estate Taxes
        if subject.real_estate_taxes is None:
            report.add_difference(
                field_name="real_estate_taxes",
                status=FieldStatus.MISSING,
                details={"section": "S-4"}
            )
        
        # S-5: Neighborhood Name validation
        if not subject.neighborhood_name or subject.neighborhood_name.lower() in ["n/a", "none", "unknown", ""]:
            report.add_difference(
                field_name="neighborhood_name",
                status=FieldStatus.MISSING,
                report_value=subject.neighborhood_name,
                details={"section": "S-5"}
            )
        
        # S-9: PUD/HOA consistency check
        if subject.hoa_period and not subject.is_pud_checked:
            report.add_difference(
                field_name="pud_hoa_consistency",
                status=FieldStatus.DIFFERENT,
                report_value=f"HOA period: {subject.hoa_period}, PUD checked: {subject.is_pud_checked}",
                details={"section": "S-9", "issue": "hoa_period_without_pud"}
            )
        
        # C-1: Contract section should be blank for refinance
        if letter.assignment_type == "Refinance":
            if contract.contract_price or contract.contract_date:
                report.add_difference(
                    field_name="contract_section_refinance",
                    status=FieldStatus.DIFFERENT,
                    report_value="Contract section has data",
                    expected_value="Contract section should be blank for refinance",
                    details={"section": "C-1"}
                )
        
        # S-12: Data source check
        if subject.offered_for_sale_12mo is False and not subject.data_source:
            report.add_difference(
                field_name="listing_data_source",
                status=FieldStatus.MISSING,
                details={"section": "S-12", "issue": "no_data_source_for_12mo_history"}
            )
    
    def _compare_field(
        self,
        report: DifferenceReport,
        field_name: str,
        report_value: Optional[str],
        expected_value: Optional[str]
    ):
        """Compare a single field and add difference if needed."""
        
        # Normalize values for comparison
        norm_report = self._normalize_for_comparison(report_value)
        norm_expected = self._normalize_for_comparison(expected_value)
        
        if not norm_report and norm_expected:
            # Field missing in report but expected
            report.add_difference(
                field_name=field_name,
                status=FieldStatus.MISSING,
                report_value=report_value,
                expected_value=expected_value
            )
        elif norm_report and norm_expected and norm_report != norm_expected:
            # Values differ
            report.add_difference(
                field_name=field_name,
                status=FieldStatus.DIFFERENT,
                report_value=report_value,
                expected_value=expected_value
            )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _compile_patterns(self) -> Dict:
        """Compile regex patterns for reuse."""
        return {}  # Patterns compiled on demand
    
    def _extract_field(self, text: str, patterns: list) -> Optional[str]:
        """Try multiple patterns and return first match."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None
    
    def _parse_address_components(self, address: str) -> Dict:
        """Parse address into city, state, zip components."""
        result = {}
        
        # Clean extra text like "Property County:" that might be appended
        address = re.sub(r'\s+Property County:.*$', '', address, flags=re.IGNORECASE)
        address = re.sub(r'\s+\(.*?\)\s*', ' ', address)  # Remove parenthetical notes
        
        # Try Pattern 1: "Street City, State Zip" (with comma)
        # Example: "123 Main St, Anytown, CA 12345"
        match = re.search(r'([A-Za-z\s]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', address)
        if match:
            result["city"] = match.group(1).strip()
            result["state"] = match.group(2)
            result["zip_code"] = match.group(3)
            return result
        
        # Try Pattern 2: "Street City State Zip" (no comma, more greedy city capture)
        # Example: "25126 N Jack Tone Rd Acampo CA 95220"
        # This pattern captures: City name before State abbreviation CA 95220
        match = re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', address)
        if match:
            result["city"] = match.group(1).strip()
            result["state"] = match.group(2)
            result["zip_code"] = match.group(3)
            return result
        
        return result
    
    def _parse_money(self, value_str: str) -> Optional[float]:
        """Parse money string to float."""
        try:
            cleaned = re.sub(r'[,$]', '', value_str)
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    
    def _normalize_for_comparison(self, value: Optional[str]) -> Optional[str]:
        """Normalize a value for comparison (lowercase, strip whitespace, etc.)"""
        if not value:
            return None
        return re.sub(r'\s+', ' ', value.strip().lower())


# Global instance
extraction_service = ExtractionService()
