"""
Difference Report Models for QC Extraction

This module defines the output contract for Python's document intelligence.
Python ONLY detects facts and differences - it NEVER:
- Decides pass or fail
- Decides rejection vs escalation
- Generates rejection question text
- Applies client policy or USPAP rules

All business logic and question generation is handled by Java.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    """Status of an extracted field compared to engagement letter."""
    PRESENT = "PRESENT"          # Field exists and matches expected value
    MISSING = "MISSING"          # Field is blank or not found in document
    DIFFERENT = "DIFFERENT"      # Field exists but differs from expected value
    UNREADABLE = "UNREADABLE"    # Field could not be extracted due to OCR/parsing issues


class ExtractedField(BaseModel):
    """A single extracted field with its value and metadata."""
    field_name: str
    value: Optional[str] = None
    confidence: float = 0.0
    source_page: Optional[int] = None
    raw_text: Optional[str] = None  # Original OCR text before normalization


class FieldDifference(BaseModel):
    """Comparison result between appraisal report and engagement letter."""
    field_name: str
    status: FieldStatus
    report_value: Optional[str] = None       # Value extracted from appraisal report
    expected_value: Optional[str] = None     # Value from engagement letter/order
    confidence: float = 0.0
    details: Optional[Dict[str, Any]] = None  # Additional context (e.g., source section)


# ============================================================================
# Subject Section Extracted Fields (S-1 to S-12)
# ============================================================================

class SubjectSectionExtract(BaseModel):
    """Extracted facts from Subject Section of appraisal report."""
    
    # S-1: Property Address
    property_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    
    # S-2: Borrower
    borrower_name: Optional[str] = None
    co_borrower_name: Optional[str] = None
    
    # S-3: Owner of Public Record
    owner_of_public_record: Optional[str] = None
    
    # S-4: Legal Description, APN, Taxes
    legal_description: Optional[str] = None
    assessors_parcel_number: Optional[str] = None
    tax_year: Optional[str] = None
    real_estate_taxes: Optional[float] = None
    
    # S-5: Neighborhood Name
    neighborhood_name: Optional[str] = None
    
    # S-6: Map Reference and Census Tract
    map_reference: Optional[str] = None
    census_tract: Optional[str] = None
    
    # S-7: Occupant Status
    occupant_status: Optional[str] = None  # Owner, Tenant, Vacant
    lease_dates: Optional[str] = None
    rental_amount: Optional[float] = None
    utilities_on: Optional[bool] = None
    
    # S-8: Special Assessments
    special_assessments: Optional[float] = None
    special_assessments_comment: Optional[str] = None
    
    # S-9: PUD and HOA
    is_pud_checked: Optional[bool] = None
    hoa_dues: Optional[float] = None
    hoa_period: Optional[str] = None  # Per Year, Per Month
    
    # S-10: Lender/Client
    lender_name: Optional[str] = None
    lender_address: Optional[str] = None
    
    # S-11: Property Rights
    property_rights: Optional[str] = None  # Fee Simple, Leasehold, De Minimis PUD
    
    # S-12: Prior Listing/Sale History
    offered_for_sale_12mo: Optional[bool] = None
    data_source: Optional[str] = None
    mls_number: Optional[str] = None
    days_on_market: Optional[int] = None
    list_price: Optional[float] = None
    list_date: Optional[str] = None


# ============================================================================
# Contract Section Extracted Fields (C-1 to C-5)
# ============================================================================

class ContractSectionExtract(BaseModel):
    """Extracted facts from Contract Section of appraisal report."""
    
    # C-1: Contract Analysis
    assignment_type: Optional[str] = None  # Purchase, Refinance
    did_analyze_contract: Optional[bool] = None
    sale_type: Optional[str] = None  # Arms-Length, REO, Short Sale, etc.
    contract_analysis_comment: Optional[str] = None
    
    # C-2: Contract Price and Date
    contract_price: Optional[float] = None
    contract_date: Optional[str] = None
    
    # C-3: Owner of Record Data Source
    is_seller_owner_of_record: Optional[bool] = None
    owner_record_data_source: Optional[str] = None
    
    # C-4: Financial Assistance/Concessions
    has_financial_assistance: Optional[bool] = None
    financial_assistance_amount: Optional[float] = None
    financial_assistance_description: Optional[str] = None
    
    # C-5: Personal Property
    personal_property_items: List[str] = Field(default_factory=list)
    personal_property_contributes_to_value: Optional[bool] = None


# ============================================================================
# Engagement Letter / Order Data
# ============================================================================

class EngagementLetterExtract(BaseModel):
    """Extracted facts from Engagement Letter / Order Form."""
    
    # Property
    property_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    
    # People
    borrower_name: Optional[str] = None
    co_borrower_name: Optional[str] = None
    
    # Lender
    lender_name: Optional[str] = None
    lender_address: Optional[str] = None
    
    # Transaction
    assignment_type: Optional[str] = None  # Purchase, Refinance
    loan_type: Optional[str] = None  # Conventional, FHA, VA, USDA
    
    # Contract (if purchase)
    contract_price: Optional[float] = None
    seller_name: Optional[str] = None
    concessions_amount: Optional[float] = None


# ============================================================================
# Difference Report - Main Output
# ============================================================================

class DifferenceReport(BaseModel):
    """
    The complete output from Python's document intelligence.
    
    This is the OUTPUT CONTRACT between Python and Java:
    - Python outputs facts and differences ONLY
    - Java converts differences into questions
    - Java applies business rules and severity classification
    """
    
    # Processing metadata
    success: bool = True
    processing_time_ms: int = 0
    extraction_method: str = "pymupdf"  # pymupdf, tesseract, env
    total_pages: int = 0
    
    # Document presence flags
    env_file_present: bool = False
    env_file_readable: bool = False
    engagement_letter_present: bool = False
    
    # Extracted sections
    subject_section: SubjectSectionExtract = Field(default_factory=SubjectSectionExtract)
    contract_section: ContractSectionExtract = Field(default_factory=ContractSectionExtract)
    engagement_letter: Optional[EngagementLetterExtract] = None
    
    # Differences detected (mechanical comparison only)
    differences: List[FieldDifference] = Field(default_factory=list)
    
    # Processing issues (not decisions)
    extraction_warnings: List[str] = Field(default_factory=list)
    unreadable_sections: List[str] = Field(default_factory=list)
    
    # Field-level extraction confidence
    field_confidence: Dict[str, float] = Field(default_factory=dict)
    
    def add_difference(
        self,
        field_name: str,
        status: FieldStatus,
        report_value: Optional[str] = None,
        expected_value: Optional[str] = None,
        confidence: float = 1.0,
        details: Optional[Dict[str, Any]] = None
    ):
        """Helper to add a difference to the report."""
        self.differences.append(FieldDifference(
            field_name=field_name,
            status=status,
            report_value=report_value,
            expected_value=expected_value,
            confidence=confidence,
            details=details
        ))
    
    def add_warning(self, warning: str):
        """Helper to add a processing warning."""
        self.extraction_warnings.append(warning)
