"""
Smart QC Processor for Appraisal Documents

Orchestrates the full QC pipeline:
1. OCR extraction (two-pass)
2. Field extraction and normalization
3. NLP checks
4. Rule engine execution
5. Results assembly
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from app.models.appraisal import (
    ValidationContext, AppraisalReport, SubjectSection,
    EngagementLetter, ContractSection, NeighborhoodSection,
    SiteSection, ImprovementSection, SalesComparisonSection, Comparable
)
from app.ocr.ocr_pipeline import OCRPipeline, PageSelector, ExtractionResult
from app.extraction.normalizers import (
    normalize_address, normalize_money, normalize_date,
    normalize_census_tract, normalize_area
)
from app.rule_engine.engine import engine, RuleStatus, RuleResult

# Import rules to ensure registration
import app.rules
from app.services.extraction_service import extraction_service
from app.models.difference_report import SubjectSectionExtract, ContractSectionExtract
from app.services.cache_service import (
    get_cached_ocr, save_ocr_pages,
    save_extracted_fields, save_rule_results,
    DB_AVAILABLE,
)

logger = logging.getLogger(__name__)


class QCResultItem(BaseModel):
    """Individual rule result."""
    rule_id: str
    rule_name: str
    status: str
    message: str
    action_item: Optional[str] = None
    details: Optional[Dict] = None
    # Comparison fields for reviewer UI
    appraisal_value: Optional[str] = None
    engagement_value: Optional[str] = None
    review_required: bool = False


class QCResults(BaseModel):
    """Complete QC results."""
    success: bool
    processing_time_ms: int
    total_pages: int
    extraction_method: str
    document_id: Optional[str] = None     # DB record ID — None if DB unavailable
    cache_hit: bool = False               # True if OCR was served from cache
    
    # Extracted fields summary
    extracted_fields: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    
    # Rule results
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    verify: int = 0  # Merged: VERIFY + WARNING (all need human review)
    skipped: int = 0
    system_errors: int = 0  # Only actual engine crashes
    
    rule_results: List[QCResultItem] = []
    
    # Action items for human review
    action_items: List[str] = []
    
    # Suggestions for improvement
    suggestions: List[str] = []
    
    # Warnings from processing
    processing_warnings: List[str] = []


class SmartQCProcessor:
    """
    Orchestrates the complete QC pipeline for appraisal documents.
    """
    
    def __init__(self, use_tesseract: bool = True, use_nlp_embeddings: bool = False):
        # use_preprocessing=True enables the full 5-step image pipeline:
        # grayscale → denoise → Otsu threshold → table-line removal → deskew
        # force_image_ocr=True is kept so every page is checked via Tesseract,
        # but the pipeline now runs in parallel (4 workers) per Phase 1.
        self.ocr_pipeline = OCRPipeline(
            use_tesseract=use_tesseract,
            force_image_ocr=True,
            use_preprocessing=True,
        )
        self.use_nlp_embeddings = use_nlp_embeddings
    
    def process_document(
        self,
        pdf_path: str,
        engagement_letter_text: Optional[str] = None,
        contract_text: Optional[str] = None,
        file_hash: Optional[str] = None,
        original_filename: str = "unknown.pdf",
    ) -> QCResults:
        """
        Process an appraisal PDF through the complete QC pipeline.

        Args:
            pdf_path:               Path to the appraisal PDF
            engagement_letter_text: Optional text from engagement letter
            contract_text:          Optional text from purchase contract
            file_hash:              SHA-256 of the PDF (for cache lookup/save)
            original_filename:      Original upload filename (for DB record)

        Returns:
            QCResults with all validation outcomes
        """
        start_time = time.time()
        document_id: Optional[str] = None

        # ── Step 1: Check OCR Cache ─────────────────────────────────────────
        import fitz as _fitz
        try:
            _doc = _fitz.open(pdf_path)
            total_pages = len(_doc)
            _doc.close()
        except Exception:
            total_pages = 0

        cache_hit = False
        if file_hash and total_pages > 0:
            cached_pages = get_cached_ocr(file_hash, total_pages)
            if cached_pages:
                logger.info("Cache HIT — skipping OCR for %s", file_hash[:12])
                cache_hit = True
                # Reconstruct ExtractionResult from cached pages
                from app.ocr.ocr_pipeline import ExtractionResult
                extraction_result = ExtractionResult()
                extraction_result.total_pages = total_pages
                for pt in cached_pages:
                    extraction_result.page_index[pt.page_number] = pt.text
                    extraction_result.page_details.append(pt)

        # ── Step 2: OCR Extraction (if not cached) ──────────────────────────
        if not cache_hit:
            logger.info("Cache MISS — running OCR for %s", pdf_path)
            extraction_result = self.ocr_pipeline.extract_all_pages(pdf_path)

            # Save to cache for next time
            if file_hash and extraction_result.page_details:
                document_id = save_ocr_pages(
                    file_hash=file_hash,
                    filename=original_filename,
                    pages=extraction_result.page_details,
                )

        if not extraction_result.page_index:
            return QCResults(
                success=False,
                processing_time_ms=int((time.time() - start_time) * 1000),
                total_pages=0,
                extraction_method="none",
                processing_warnings=["Failed to extract any text from PDF"]
            )

        full_text = self.ocr_pipeline.get_full_text(extraction_result.page_index)

        # Step 2: Multi-Source Extraction
        # Source A: Extraction Service (High Quality for Subject/Contract)
        s_extract = extraction_service.extract_subject_section(full_text)
        c_extract = extraction_service.extract_contract_section(full_text)
        
        # Source B: Advanced Parser (Legacy for Site/Improvements)
        from advanced_parser import extract_advanced_fields
        legacy_fields = extract_advanced_fields(full_text)

        # Step 3: Map to AppraisalReportDomain Model
        report = self._map_extraction_to_report(s_extract, c_extract, legacy_fields)
        
        # Step 4: Handle Engagement Letter
        engagement_letter = None
        if engagement_letter_text:
            # Parse explicitly provided text
            eng_extract = extraction_service.extract_engagement_letter(engagement_letter_text)
            engagement_letter = self._map_engagement_letter(eng_extract)
        else:
            # FALLBACK: Create proxy from Report data
            logger.warning("No Engagement Letter found. Creating proxy from Report data for validation.")
            engagement_letter = EngagementLetter(
                borrower_name=report.subject.borrower,
                property_address=report.subject.address,
                city=report.subject.city,
                state=report.subject.state,
                zip_code=report.subject.zip_code,
                county=report.subject.county,
                lender_name=report.subject.lender_name,
                lender_address=report.subject.lender_address,
                assignment_type=report.contract.assignment_type or "Refinance"
            )

        # Step 5: Parse contract PDF if provided OR if appraisal says it was analyzed
        purchase_agreement = None
        if contract_text:
            pa_extract = extraction_service.extract_purchase_agreement(contract_text)
            purchase_agreement = pa_extract
        elif report.contract.did_analyze_contract:
            logger.info("Appraisal indicates contract was analyzed but no contract PDF provided.")

        # Step 6: Create ValidationContext
        ctx = ValidationContext(
            report=report,
            engagement_letter=engagement_letter,
            purchase_agreement=purchase_agreement
        )
        
        # Step 7: Execute rule engine
        logger.info("Executing rule engine")
        rule_results = engine.execute(ctx)

        # Step 8: Persist fields + rule results to DB (non-blocking — failures logged only)
        if document_id:
            page_confidences = [p.confidence for p in extraction_result.page_details]
            save_extracted_fields(document_id, s_extract.model_dump(), page_confidences)
            save_rule_results(document_id, rule_results)

        # Step 9: Assemble results
        results = self._assemble_results(
            extraction_result=extraction_result,
            s_extract=s_extract,
            rule_results=rule_results,
            start_time=start_time,
            document_id=document_id,
        )

        return results
    
    def _map_extraction_to_report(
        self, 
        s: SubjectSectionExtract, 
        c: ContractSectionExtract,
        legacy: Dict[str, Any]
    ) -> AppraisalReport:
        """Map extracted objects + legacy dict to AppraisalReport model."""
        
        subject = SubjectSection(
            address=s.property_address,
            city=s.city,
            state=s.state,
            zip_code=s.zip_code,
            county=s.county,
            borrower=s.borrower_name,
            co_borrower=s.co_borrower_name,
            owner_of_public_record=s.owner_of_public_record,
            legal_description=s.legal_description,
            apn=s.assessors_parcel_number,
            tax_year=s.tax_year,
            re_taxes=s.real_estate_taxes,
            neighborhood_name=s.neighborhood_name,
            map_reference=s.map_reference,
            census_tract=s.census_tract,
            occupant=s.occupant_status,
            lease_dates=s.lease_dates,
            rental_amount=s.rental_amount,
            utilities_on=s.utilities_on,
            special_assessments=s.special_assessments,
            special_assessments_comment=s.special_assessments_comment,
            hoa_dues=s.hoa_dues,
            hoa_period=s.hoa_period,
            is_pud=s.is_pud_checked or False,
            lender_name=s.lender_name,
            lender_address=s.lender_address,
            property_rights=s.property_rights,
            prior_sale_offered_12mo=s.offered_for_sale_12mo,
            data_sources=s.data_source,
            mls_number=s.mls_number,
            days_on_market=s.days_on_market,
            list_price=s.list_price,
            list_date=s.list_date
        )
        
        contract = ContractSection(
            assignment_type=c.assignment_type,
            did_analyze_contract=c.did_analyze_contract,
            sale_type=c.sale_type,
            contract_analysis_comment=c.contract_analysis_comment,
            contract_price=c.contract_price,
            date_of_contract=c.contract_date,
            is_seller_owner=c.is_seller_owner_of_record,
            owner_record_data_source=c.owner_record_data_source,
            financial_assistance=c.has_financial_assistance,
            financial_assistance_amount=c.financial_assistance_amount,
            financial_assistance_description=c.financial_assistance_description,
            personal_property_items=c.personal_property_items or [],
        )

        # Populate legacy sections
        site = SiteSection(
            dimensions=legacy.get("siteDimensions"),
            area=legacy.get("siteArea"),
            area_unit=legacy.get("siteAreaUnit"),
            zoning_compliance=legacy.get("zoningCompliance"),
            highest_and_best_use=legacy.get("highestAndBestUse"),
        )
        
        improvements = ImprovementSection(
            design_style=legacy.get("designStyle"),
            year_built=legacy.get("yearBuilt"),
        )
        
        sales = SalesComparisonSection(
            comparables_count_sales=legacy.get("comparableCount", 0),
        )

        return AppraisalReport(
            subject=subject,
            contract=contract,
            site=site,
            improvements=improvements,
            sales_comparison=sales,
        )

    def _map_engagement_letter(self, eng_extract) -> EngagementLetter:
        """Map EngagementLetterExtract to EngagementLetter model."""
        return EngagementLetter(
            borrower_name=eng_extract.borrower_name,
            property_address=eng_extract.property_address,
            city=eng_extract.city,
            state=eng_extract.state,
            zip_code=eng_extract.zip_code,
            county=eng_extract.county,
            lender_name=eng_extract.lender_name,
            lender_address=eng_extract.lender_address,
            assignment_type=eng_extract.assignment_type,
            loan_type=eng_extract.loan_type
        )
    
    def _assemble_results(
        self,
        extraction_result,
        s_extract: SubjectSectionExtract,
        rule_results: List[RuleResult],
        start_time: float,
        document_id: Optional[str] = None,
    ) -> QCResults:
        """Assemble final QC results."""
        
        # Count results by status
        status_counts = {
            RuleStatus.PASS: 0,
            RuleStatus.FAIL: 0,
            RuleStatus.VERIFY: 0,
            RuleStatus.WARNING: 0,
            RuleStatus.SKIPPED: 0,
            RuleStatus.SYSTEM_ERROR: 0,
        }
        
        qc_items = []
        action_items = []
        
        for result in rule_results:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1
            
            qc_items.append(QCResultItem(
                rule_id=result.rule_id,
                rule_name=result.rule_name,
                status=result.status.value,
                message=result.message,
                action_item=result.action_item,
                details=result.details,
                appraisal_value=result.appraisal_value,
                engagement_value=result.engagement_value,
                review_required=result.review_required
            ))
            
            # Collect action items from failed/skipped rules
            if result.action_item and result.status in [RuleStatus.FAIL, RuleStatus.SKIPPED, RuleStatus.WARNING]:
                action_items.append(f"[{result.rule_id}] {result.action_item}")
        
        # Get improvement suggestions
        suggestions = engine.get_improvement_suggestions()
        
        # Primary extraction method (most frequent across pages)
        methods = [p.method.value for p in extraction_result.page_details]
        primary_method = max(set(methods), key=methods.count) if methods else "unknown"

        # Per-field confidence: avg OCR page confidence ± field-type adjustment
        avg_conf = (
            sum(p.confidence for p in extraction_result.page_details)
            / len(extraction_result.page_details)
        ) if extraction_result.page_details else 0.7

        HIGH_CONF = {"zip_code", "census_tract", "assessors_parcel_number", "tax_year"}
        LOW_CONF  = {"neighborhood_name", "legal_description", "owner_of_public_record"}

        field_confidence: Dict[str, float] = {}
        for field_name, value in s_extract.model_dump().items():
            if value is None:
                field_confidence[field_name] = 0.0
            elif field_name in HIGH_CONF:
                field_confidence[field_name] = round(min(1.0, avg_conf + 0.10), 3)
            elif field_name in LOW_CONF:
                field_confidence[field_name] = round(max(0.0, avg_conf - 0.10), 3)
            else:
                field_confidence[field_name] = round(avg_conf, 3)

        return QCResults(
            success=True,
            processing_time_ms=int((time.time() - start_time) * 1000),
            total_pages=extraction_result.total_pages,
            extraction_method=primary_method,
            document_id=document_id,
            extracted_fields=s_extract.model_dump(),
            field_confidence=field_confidence,
            total_rules=len(rule_results),
            passed=status_counts[RuleStatus.PASS],
            failed=status_counts[RuleStatus.FAIL],
            verify=status_counts[RuleStatus.VERIFY] + status_counts[RuleStatus.WARNING],
            skipped=status_counts[RuleStatus.SKIPPED],
            system_errors=status_counts[RuleStatus.SYSTEM_ERROR],
            rule_results=qc_items,
            action_items=action_items,
            suggestions=suggestions,
            processing_warnings=extraction_result.warnings,
        )


# Create global processor instance
qc_processor = SmartQCProcessor()
