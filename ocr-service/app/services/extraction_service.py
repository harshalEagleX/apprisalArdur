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
from typing import Optional, Dict, Tuple, List, Any
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
        report.subject_section = self.extract_subject_section(extracted_text, pdf_path)
        
        # RETRY LOGIC: If Property Address is missing and we used Text-First (pymupdf),
        # it likely means the text layer is bad/garbage. Retry with Forced OCR.
        if (not report.subject_section.property_address and report.extraction_method == "pymupdf"):
            logger.warning("Critical field 'Property Address' missing after text extraction. Retrying with Forced Image OCR...")
            
            # Re-run extraction with forced OCR
            extracted_text, total_pages = self._extract_from_pdf(pdf_path, force_ocr=True)
            report.extraction_method = "ocr_retry"
            
            # Re-extract sections
            report.subject_section = self.extract_subject_section(extracted_text, pdf_path)
            report.contract_section = self._extract_contract_section(extracted_text)
        else:
            # Step 3: Extract Contract Section (only if we didn't just do it in retry)
            report.contract_section = self._extract_contract_section(extracted_text)
        
        # Step 4: Parse engagement letter if provided
        if engagement_letter_text:
            report.engagement_letter_present = True
            report.engagement_letter = self._extract_engagement_letter(engagement_letter_text)
            
            # Step 5: Detect differences (mechanical comparison only)
            self._detect_differences(report)
        
        report.processing_time_ms = int((time.time() - start_time) * 1000)
        return report
    
    def _extract_from_pdf(self, pdf_path: str, force_ocr: bool = False) -> Tuple[str, int]:
        """
        Extract text from PDF using a Text-First strategy.
        
        Args:
            pdf_path: Path to PDF file
            force_ocr: If True, bypass text check and force Image OCR (used for retry)
            
        Rule: "Never OCR text-based PDFs" (unless forced by retry logic)
        1. Check each page for selectable text.
        2. If text exists (>50 chars) AND not force_ocr, extract it directly.
        3. Only use OCR for pages that are truly image-only OR if force_ocr=True.
        """
        text_parts = []
        total_pages = 0
        
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Step 1: Check for existing text
                # We use "text" flag which preserves natural reading order
                embedded_text = page.get_text("text")
                
                # Clean up text to check real content
                clean_text = embedded_text.strip()
                
                # Heuristic: If we have > 50 characters, assume it's a text PDF
                # This avoids OCR on pages that are just text-based forms
                # BUT if force_ocr is True, we skip this check
                if len(clean_text) > 50 and not force_ocr:
                    logger.info(f"Page {page_num + 1}: Text detected ({len(clean_text)} chars). Skipping OCR.")
                    text_parts.append(embedded_text)
                else:
                    # Step 2: Image-only page OR Forced Retry - use OCR
                    reason = "Forced Retry" if force_ocr else f"Insufficient text ({len(clean_text)} chars)"
                    logger.info(f"Page {page_num + 1}: {reason}. Using OCR.")
                    
                    # Use our OCR pipeline for this specific page
                    # Note: We extract just this page to avoid reprocessing the whole doc if mixed
                    try:
                        # We need to extract this page visually. 
                        # Using extraction_method="tesseract" logic from OCRPipeline
                        # Since pipeline is page-agnostic in current design, we'll ask it to process this page
                        # For now, we reuse the pipeline's internal methods if accessible, or just let it process
                        # efficiently. Ideally, we'd have a method `process_single_page`.
                        # As a fallback, we can use the pipeline on the whole doc if we must, but here we build parts.
                        
                        # Let's use the pipeline's page extraction logic directly
                        page_text_obj = self.ocr_pipeline._extract_page(page, page_num + 1, force_image=True)
                        text_parts.append(page_text_obj.text)
                        
                    except Exception as ocr_error:
                        logger.error(f"OCR failed for page {page_num + 1}: {ocr_error}")
                        # Fallback to whatever embedded text we had, even if empty
                        text_parts.append(embedded_text)
            
            doc.close()
            
            return "\n\n".join(text_parts), total_pages
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise
    
    def _parse_env(self, env_content: bytes) -> str:
        """Parse ENV file to extract text. Placeholder for future implementation."""
        # TODO: Implement ENV (XML) parsing
        raise NotImplementedError("ENV parsing not yet implemented")
    
    # =========================================================================
    # Subject Section Extraction (S-1 to S-12)
    # =========================================================================
    
    def extract_subject_section(self, text: str, pdf_path: str = None) -> SubjectSectionExtract:
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
             # IMPROVED: Stricter pattern that searches for standard address formats
             # (Number + Name + Suffix)
             
             # Pattern 1: Address with Street Suffix (Very High Confidence)
             # e.g. "123 Main St", "456 North Avenue"
             match_suffix = re.search(
                r"Property Address[:\s]+(?![A-Za-z]+:).*?(\d+\s+[A-Za-z0-9\.\s]+(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|Road|Street|Avenue|Drive|Terrace|Place|Court|Lane|Loop|Trail|Parkway)[a-z\.]*)", 
                text, re.IGNORECASE | re.DOTALL
             )
             
             # Pattern 2: Address starting with digits (High confidence)
             match_digit = re.search(
                r"Property Address[:\s]+(?![A-Za-z]+:)(\d+\s+[^\n]+)", 
                text, re.IGNORECASE
             )
             
             if match_suffix:
                 subject.property_address = match_suffix.group(1).strip()
                 # Clean up newlines if DOTALL captured them
                 subject.property_address = subject.property_address.split('\n')[0].strip()
             elif match_digit:
                 subject.property_address = match_digit.group(1).strip()
             else:
                 # Pattern 3: General fallback but stop at known "next question" triggers
                 subject.property_address = self._extract_field(text, [
                    r"Property Address[:\s]+(?!City|State|Zip|County|Borrower|Lender|File)(.*?)(?=\s*City|\s*State|\s*Zip|\s*Borrower|\s*currently offered|\n)",
                    r"Subject Property[:\s]+(?!City|State|Zip|County)(.*?)(?=\s*City|\s*State|\s*Zip|\n)",
                 ])
        
        # Validate extracted address - reject gibberish
        if subject.property_address and not self._validate_address(subject.property_address):
            # Invalid address - clear it (will be flagged as VERIFY)
            logger.warning(f"Invalid property address extracted: '{subject.property_address}' - rejecting")
            subject.property_address = None
            
        # LAST RESORT: Heuristic Scan for "Orphan" Address
        # In some digital PDFs (like total_report.pdf or appraisal_004), the values appear 
        # at the very top of the text stream, disconnected from the "Property Address" label.
        # We scan the first 2000 characters for a vertical address block.
        if not subject.property_address:
            orphan_data = self._scan_vertical_address_block(text[:2000])
            if orphan_data.get('property_address'):
                 subject.property_address = orphan_data['property_address']
                 # Only override other fields if they were not found by standard extraction
                 # (Standard extraction likely found nothing if address failed)
                 subject.city = orphan_data.get('city') or subject.city
                 subject.state = orphan_data.get('state') or subject.state
                 subject.zip_code = orphan_data.get('zip_code') or subject.zip_code
                 
                 logger.info(f"Recovered property address via heuristic scan: '{subject.property_address}' "
                             f"(City: {subject.city}, State: {subject.state}, Zip: {subject.zip_code})")
        
        subject.county = self._extract_field(text, [
            r"County[:\s]+([A-Za-z\s]+?)(?:\n|$)",
        ])
        
        # S-2: Borrower
        # Field terminators to prevent capturing next field's content
        BORROWER_TERMINATORS = r"(?=\s*Owner of Public Record|\s*County|\s*Legal|\s*Assessor|\s*APN|\n)"

        subject_block = text
        subject_idx = re.search(r"(?m)^SUBJECT\s*$", text)
        contract_idx = re.search(r"(?m)^CONTRACT\s*$", text)
        if subject_idx and contract_idx and contract_idx.start() > subject_idx.end():
            subject_block = text[subject_idx.end():contract_idx.start()]
        else:
            subject_block = text[:2500]

        subject.borrower_name = self._extract_field(subject_block, [
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner|See attached)([^:\n]+?)" + BORROWER_TERMINATORS,
            r"BORROWER[:\s]+(?!LENDER|CLIENT)([^:\n]+?)" + BORROWER_TERMINATORS,
            r"Borrower Name[:\s]+(?!Information)([^:\n]+?)" + BORROWER_TERMINATORS,
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)([^\n]+)",
        ])

        borrower_low = (subject.borrower_name or "").lower().strip()
        invalid_borrower_phrases = [
            "secure a professional inspection",
            "evaluate the property",
            "subject of this appraisal",
            "for a mortgage",
        ]
        borrower_suspicious = any(p in borrower_low for p in invalid_borrower_phrases)

        if (not subject.borrower_name) or ("see attached" in borrower_low) or borrower_suspicious:
            addendum_match = re.search(
                r"(?is)(?:^|\n)\s*(?:[\-\*\u2022•]\s*)?URAR:\s*Borrower\s*\n+([\s\S]+?)(?=\n\s*(?:[\-\*\u2022•]\s*)?URAR:|\n\s*$)",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
            if addendum_match:
                raw = re.sub(r"\s+", " ", addendum_match.group(1)).strip()
                names = [n.strip(" .") for n in re.split(r"[;~]", raw) if n.strip()]
                subject.borrower_name = "; ".join(names) if names else raw
        
        # Clean up borrower name - remove trailing noise
        if subject.borrower_name:
            # Remove "Owner of Public Record" if it got captured
            subject.borrower_name = re.sub(
                r'\s*Owner of Public Record.*$', '', 
                subject.borrower_name, flags=re.IGNORECASE
            ).strip()
            # Remove trailing periods
            subject.borrower_name = subject.borrower_name.rstrip('.')
        
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

        # Fallback: Look for explicit occupant tokens without checkbox marks.
        if not subject.occupant_status:
            m = re.search(r"(?is)\bOccupant\b[\s\S]{0,80}?\b(Owner\s*Occupied|Owner|Tenant|Vacant)\b", text, re.IGNORECASE)
            if m:
                v = re.sub(r"\s+", " ", m.group(1)).strip().lower()
                if "tenant" in v:
                    subject.occupant_status = "Tenant"
                elif "vacant" in v:
                    subject.occupant_status = "Vacant"
                else:
                    subject.occupant_status = "Owner"
        
        # Fallback: Spatial Checkbox Detection (for disjointed digital PDFs)
        if not subject.occupant_status and pdf_path:
            # Look for checkmarks near these labels across first pages (occupancy block can shift).
            for page_num in range(0, 4):
                spatial_result = self._resolve_checkbox_spatial(pdf_path, page_num, ["Owner", "Tenant", "Vacant"])
                if spatial_result:
                    subject.occupant_status = spatial_result.title()
                    logger.info(f"Resolved S-7 Occupant Status via spatial check: {subject.occupant_status}")
                    break
        
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
        
        # Blacklist for known placeholder/template text
        INVALID_LENDER_NAMES = [
            "section of the signature area",
            "see attached",
            "n/a",
            "none",
            "to be determined",
            "tbd",
        ]
        
        letter.lender_name = self._extract_field(text, [
            # Match "Client:" and capture until "Client Address" or newline
            r"Client[:\s]+([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union)[A-Za-z\s]*)(?=\s+Client Address|\s*$|\n)",
            # Simpler: Client: followed by company name, stop at Address
            r"Client[:\s]+([^:]+?)(?:\s+Client Address|\s+Address|\n)",
            # Lender/Client pattern
            r"Lender/?Client[:\s]+(?!Address)([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union))",
        ])
        
        # Clean up and validate lender name
        if letter.lender_name:
            # Remove any "Client Address" that might have been captured
            letter.lender_name = re.sub(r'\s*Client Address.*$', '', letter.lender_name, flags=re.IGNORECASE).strip()
            # Remove trailing punctuation
            letter.lender_name = letter.lender_name.rstrip('.,;:')
            
            # Reject placeholder/invalid text
            if letter.lender_name.lower().strip() in INVALID_LENDER_NAMES:
                letter.lender_name = None
            # Reject if too short (real lender names are typically longer)
            elif len(letter.lender_name) < 5:
                letter.lender_name = None
        
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
    
    def _extract_field(self, text: str, patterns: List[str]) -> Optional[str]:
        """Extract field using prioritized regex patterns."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return None
        
    def _resolve_checkbox_spatial(self, pdf_path: str, page_num: int, candidates: List[str]) -> Optional[str]:
        """
        Spatially resolve which checkbox is selected on a given page.
        
        Args:
            pdf_path: Path to PDF
            page_num: 0-based page index
            candidates: List of label strings to look for (e.g. ["Owner", "Tenant", "Vacant"])
            
        Returns:
            The candidate string that has an 'X' checked next to it, or None.
        """
        try:
            doc = fitz.open(pdf_path)
            if page_num >= len(doc):
                return None
            page = doc[page_num]
            
            # Get all words with coordinates: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            words = page.get_text("words")
            
            # Find candidate label locations
            candidate_locs = {}
            for cand in candidates:
                cand_lower = cand.lower()
                # Simple matching: find first word that matches candidate (approximate)
                for w in words:
                    if cand_lower in w[4].lower():
                        # Store bbox: (x0, y0, x1, y1)
                        candidate_locs[cand] = fitz.Rect(w[0], w[1], w[2], w[3])
                        break # Found this candidate
            
            if not candidate_locs:
                return None
            
            # Find all "X" marks
            # We look for "X", "x", or sometimes specific glyphs if we knew them.
            # We assume 'X' is a standalone word or very short string
            x_marks = []
            for w in words:
                text = w[4].strip()
                if text.lower() == 'x' or text == 'X':
                    x_marks.append(fitz.Rect(w[0], w[1], w[2], w[3]))
            
            if not x_marks:
                return None
                
            # Check proximity
            # A checkmark for a label is usually:
            # 1. To the LEFT of the label (within ~50 units)
            # 2. Roughly on the same Y-axis (vertical center aligned)
            
            best_match = None
            min_dist = float('inf')
            
            for cand, rect in candidate_locs.items():
                cand_center_y = (rect.y0 + rect.y1) / 2
                
                for x_rect in x_marks:
                    x_center_y = (x_rect.y0 + x_rect.y1) / 2
                    
                    # Vertical alignment check (allow small slack, e.g. 5-10 units)
                    if abs(cand_center_y - x_center_y) < 10:
                        # Horizontal check: X should be to the left, but close
                        # x_rect.x1 (right edge of X) should be < rect.x0 (left edge of Label)
                        # Distance gap
                        dist = rect.x0 - x_rect.x1
                        
                        # Allow X to be slightly inside the label area too (overlapping) or just to left
                        # Accept dist between -5 (overlap) and 60 (gap)
                        if -5 <= dist <= 60:
                            if dist < min_dist:
                                min_dist = dist
                                best_match = cand
                                
            return best_match
            
        except Exception as e:
            logger.error(f"Spatial checkbox resolution failed: {e}")
            return None
    
    def _validate_address(self, address: str) -> bool:
        """Validate if a string looks like a real address."""
        if not address or len(address) < 5:
            return False
            
        # Must have at least one digit
        if not re.search(r"\d", address):
            return False
            
        # Should not contain "offered for sale" or "did not analyze"
        if re.search(r"(?:offered for sale|did not analyze|appraisal report|property address)", address, re.IGNORECASE):
            return False
            
        return True

    def _scan_vertical_address_block(self, text_chunk: str) -> Dict[str, Optional[str]]:
        """
        Scan for a vertical address block (Street, City, State, Zip on separate lines).
        Returns a dict with found components.
        """
        lines = text_chunk.split('\n')
        result = {
            'property_address': None,
            'city': None,
            'state': None,
            'zip_code': None
        }
        
        # Strict Regex for US Street Address
        strict_addr_pattern = re.compile(
            r"^\s*(\d+\s+[A-Za-z0-9\.\s]+(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|Road|Street|Avenue|Drive|Terrace|Place|Court|Lane|Loop|Trail|Parkway))",
            re.IGNORECASE
        )
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Skip common non-address lines starting with digits
            if re.match(r"^\d{4}$", line): continue # Year
            if re.match(r"^\d+\.?\d*$", line): continue # Just numbers
                
            match = strict_addr_pattern.match(line)
            if match and self._validate_address(match.group(1).strip()):
                # Found Street Address
                result['property_address'] = match.group(1).strip()
                
                # Look-ahead for City, State, Zip in the next 3 lines
                # Pattern: Line i+1=City, i+2=State, i+3=Zip OR variations
                lookahead_lines = lines[i+1:i+4]
                
                for next_line in lookahead_lines:
                    next_line = next_line.strip()
                    if not next_line: continue
                    
                    # Check for Zip Code (Strongest signal)
                    if not result['zip_code'] and re.match(r"^\d{5}(?:-\d{4})?$", next_line):
                        result['zip_code'] = next_line
                        continue
                        
                    # Check for State (2-letter code)
                    if not result['state'] and re.match(r"^[A-Z]{2}$", next_line, re.IGNORECASE):
                        if next_line.upper() in ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]:
                            result['state'] = next_line.upper()
                            continue
                    
                    # Check for City (Alpha text, usually title case, not "Subject" or "File")
                    if not result['city'] and re.match(r"^[A-Za-z\s\.]+$", next_line):
                        if len(next_line) > 2 and next_line.lower() not in ["subject", "contract", "neighborhood", "site", "improvements"]:
                            result['city'] = next_line
                            continue
                            
                return result
        
        return result
    
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
