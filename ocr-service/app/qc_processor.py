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
from app.extraction.layout_extractor import extract_urar_layout_fields

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
        self.ocr_pipeline = OCRPipeline(use_tesseract=use_tesseract, force_image_ocr=False)
        self.use_nlp_embeddings = use_nlp_embeddings
    
    def process_document(
        self,
        pdf_path: str,
        engagement_letter_text: Optional[str] = None,
        contract_text: Optional[str] = None,
        full_text: Optional[str] = None,
        extraction_result: Optional[ExtractionResult] = None,
    ) -> QCResults:
        """
        Process an appraisal PDF through the complete QC pipeline.
        
        Args:
            pdf_path: Path to the appraisal PDF
            engagement_letter_text: Optional text from engagement letter
            contract_text: Optional text from purchase contract
            
        Returns:
            QCResults with all validation outcomes
        """
        start_time = time.time()
        
        if full_text is None:
            logger.info(f"Starting OCR extraction for: {pdf_path}")
            extraction_result = self.ocr_pipeline.extract_all_pages(pdf_path)
            
            if not extraction_result.page_index:
                return QCResults(
                    success=False,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    total_pages=0,
                    extraction_method="none",
                    processing_warnings=["Failed to extract any text from PDF"]
                )
            
            full_text = self.ocr_pipeline.get_full_text(extraction_result.page_index)
        else:
            if extraction_result is None:
                try:
                    import fitz
                    doc = fitz.open(pdf_path)
                    total_pages = len(doc)
                    doc.close()
                except Exception:
                    total_pages = 0
                extraction_result = ExtractionResult(total_pages=total_pages)

        # Step 2: Multi-Source Extraction
        # Source A: Extraction Service (High Quality for Subject/Contract)
        # Pass pdf_path to enable spatial fallback extraction where implemented.
        s_extract = extraction_service.extract_subject_section(full_text, pdf_path=pdf_path)
        c_extract = extraction_service.extract_contract_section(full_text)
        
        # Source B: Advanced Parser (Legacy for Site/Improvements)
        from advanced_parser import extract_advanced_fields
        legacy_fields = extract_advanced_fields(full_text)

        # Source C: Lightweight Layout Extractor (Text PDFs) for checkbox/table fields
        try:
            layout_fields = extract_urar_layout_fields(pdf_path, full_text=full_text)
            if layout_fields:
                legacy_fields.update(layout_fields)
        except Exception as e:
            logger.warning(f"Layout extraction failed: {e}")

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

        # Step 5: Create ValidationContext
        ctx = ValidationContext(
            report=report,
            engagement_letter=engagement_letter,
            addenda_text=full_text,
        )
        
        # Step 6: Execute rule engine
        logger.info("Executing rule engine")
        rule_results = engine.execute(ctx)
        
        # Step 7: Assemble results
        results = self._assemble_results(
            extraction_result=extraction_result,
            s_extract=s_extract,
            rule_results=rule_results,
            start_time=start_time
        )
        
        return results
    
    def _map_extraction_to_report(
        self, 
        s: SubjectSectionExtract, 
        c: ContractSectionExtract,
        legacy: dict,
    ) -> AppraisalReport:
        """Map extracted objects + legacy dict to AppraisalReport model."""
        
        def _legacy_first_non_null(*keys):
            for k in keys:
                if k in legacy and legacy.get(k) is not None:
                    return legacy.get(k)
            return None
        
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
        neighborhood = NeighborhoodSection(
            location=legacy.get("location"),
            built_up=legacy.get("builtUp"),
            growth_rate=legacy.get("growthRate"),
            property_values=legacy.get("propertyValues"),
            demand_supply=legacy.get("demandSupply"),
            marketing_time=legacy.get("marketingTime"),
            price_low=_legacy_first_non_null("priceLow", "price_low"),
            price_high=_legacy_first_non_null("priceHigh", "price_high"),
            predominant_price=_legacy_first_non_null("predominantPrice", "predominant_price"),
            age_low=_legacy_first_non_null("ageLow", "age_low"),
            age_high=_legacy_first_non_null("ageHigh", "age_high"),
            predominant_age=_legacy_first_non_null("predominantAge", "predominant_age"),
            land_use_one_unit=_legacy_first_non_null("landUseOneUnit", "land_use_one_unit"),
            land_use_2_4_family=_legacy_first_non_null("landUse2_4Family", "landUse2_4", "land_use_2_4_family"),
            land_use_multi_family=_legacy_first_non_null("landUseMultiFamily", "land_use_multi_family"),
            land_use_commercial=_legacy_first_non_null("landUseCommercial", "land_use_commercial"),
            land_use_industrial=_legacy_first_non_null("landUseIndustrial", "land_use_industrial"),
            land_use_other=_legacy_first_non_null("landUseOther", "land_use_other"),
            land_use_other_description=_legacy_first_non_null("landUseOtherDescription", "land_use_other_description"),
            boundaries_description=legacy.get("neighborhoodBoundaries"),
            description_commentary=legacy.get("neighborhoodDescription"),
            market_conditions_comment=legacy.get("marketConditions"),
        )

        site = SiteSection(
            dimensions=legacy.get("siteDimensions"),
            area=legacy.get("siteArea"),
            area_unit=legacy.get("siteAreaUnit"),
            shape=legacy.get("siteShape"),
            view=legacy.get("siteView"),
            zoning_classification=legacy.get("zoningClassification"),
            zoning_compliance=legacy.get("zoningCompliance"),
            highest_and_best_use=legacy.get("highestAndBestUse"),
            fema_flood_hazard=legacy.get("femaFloodHazard"),
            fema_flood_zone=legacy.get("femaFloodZone") or legacy.get("fema_flood_zone"),
            fema_map_number=legacy.get("femaMapNumber") or legacy.get("fema_map_number"),
            fema_map_date=legacy.get("femaMapDate") or legacy.get("fema_map_date"),
            utilities_typical=legacy.get("utilitiesTypical"),
            adverse_site_conditions=legacy.get("adverseSiteConditions"),
        )
        
        improvements = ImprovementSection(
            units_count=legacy.get("unitsCount") if legacy.get("unitsCount") is not None else 1,
            stories=legacy.get("stories"),
            improvement_type=legacy.get("improvementType"),
            construction_status=legacy.get("constructionStatus"),
            design_style=legacy.get("designStyle"),
            year_built=legacy.get("yearBuilt"),
            effective_age=legacy.get("effectiveAge"),

            foundation=legacy.get("foundation"),
            sump_pump=legacy.get("sumpPump"),
            evidence_dampness=legacy.get("evidenceDampness"),
            evidence_settlement=legacy.get("evidenceSettlement"),
            evidence_infestation=legacy.get("evidenceInfestation"),

            foundation_walls=legacy.get("foundationWalls"),
            exterior_walls=legacy.get("exteriorWalls"),
            roof_surface=legacy.get("roofSurface"),
            gutters_downspouts=legacy.get("guttersDownspouts"),
            window_type=legacy.get("windowType"),
            storm_sash_screens=legacy.get("stormSashScreens"),

            floors=legacy.get("floors"),
            walls=legacy.get("walls"),
            trim_finish=legacy.get("trimFinish"),
            bath_floor=legacy.get("bathFloor"),
            bath_wainscot=legacy.get("bathWainscot"),

            car_storage=legacy.get("carStorage"),
            driveway_surface=legacy.get("drivewaySurface"),

            utilities_status=legacy.get("utilitiesStatus") or legacy.get("utilities_status"),

            total_rooms=legacy.get("totalRooms") or legacy.get("total_rooms"),
            bedrooms=legacy.get("bedrooms"),
            baths=legacy.get("baths"),
            gla=legacy.get("gla"),

            additional_features=legacy.get("additionalFeatures") or legacy.get("additional_features"),

            condition_rating=legacy.get("conditionRating"),
            condition_commentary=legacy.get("conditionCommentary"),
            adverse_conditions_affecting_livability=legacy.get("adverseConditionsAffectingLivability"),
            conforms_to_neighborhood=legacy.get("conformsToNeighborhood"),
        )
        
        comp_dicts = legacy.get("comparables") or []
        comps: List[Comparable] = []
        for c in comp_dicts:
            if not isinstance(c, dict):
                continue
            comps.append(
                Comparable(
                    address=c.get("address"),
                    proximity=c.get("proximity"),
                    sale_price=c.get("sale_price"),
                    sale_financing_concessions=c.get("sale_financing_concessions"),
                    data_source=c.get("data_source"),
                    verification_source=c.get("verification_source"),
                    sale_date=c.get("sale_date"),
                    location_rating=c.get("location_rating"),
                    leasehold_fee_simple=c.get("leasehold_fee_simple"),
                    site_size=c.get("site_size"),
                    view=c.get("view"),
                    design_style=c.get("design_style"),
                    quality_rating=c.get("quality_rating"),
                    actual_age=c.get("actual_age"),
                    condition_rating=c.get("condition_rating"),
                    functional_utility=c.get("functional_utility"),
                    room_count_total=c.get("room_count_total"),
                    room_count_bed=c.get("room_count_bed"),
                    room_count_bath=c.get("room_count_bath"),
                    gla=c.get("gla"),
                    basement_gla=c.get("basement_gla"),
                    heating_cooling=c.get("heating_cooling"),
                    garage_carport=c.get("garage_carport"),
                    porch_patio_deck=c.get("porch_patio_deck"),
                    net_adjustment=c.get("net_adjustment"),
                    adjusted_sale_price=c.get("adjusted_sale_price"),
                    is_listing=bool(c.get("is_listing", False)),
                )
            )

        subj_comp_data = legacy.get("subject_comparable")
        subject_comp = None
        if subj_comp_data and isinstance(subj_comp_data, dict):
             subject_comp = Comparable(
                address=subj_comp_data.get("address"),
                sale_price=subj_comp_data.get("sale_price"),
                site_size=subj_comp_data.get("site_size"),
                quality_rating=subj_comp_data.get("quality_rating"),
                actual_age=subj_comp_data.get("actual_age"),
                condition_rating=subj_comp_data.get("condition_rating"),
                room_count_total=subj_comp_data.get("room_count_total"),
                room_count_bed=subj_comp_data.get("room_count_bed"),
                room_count_bath=subj_comp_data.get("room_count_bath"),
                gla=subj_comp_data.get("gla"),
             )

        sales = SalesComparisonSection(
            comparables_count_sales=legacy.get("comparables_count_sales") or legacy.get("comparableCount"),
            comparables_count_listings=legacy.get("comparables_count_listings"),
            comparables=comps,
            subject_comparable=subject_comp,
        )

        return AppraisalReport(
            subject=subject,
            contract=contract,
            neighborhood=neighborhood,
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
        
        # Calculate primary method
        methods = [p.method.value for p in extraction_result.page_details]
        primary_method = max(set(methods), key=methods.count) if methods else "unknown"

        return QCResults(
            success=True,
            processing_time_ms=int((time.time() - start_time) * 1000),
            total_pages=extraction_result.total_pages,
            extraction_method=primary_method,
            extracted_fields=s_extract.model_dump(), # Use Subject Extract as summary
            field_confidence={}, # TODO: map legacy confidence
            total_rules=len(rule_results),
            passed=status_counts[RuleStatus.PASS],
            failed=status_counts[RuleStatus.FAIL],
            verify=status_counts[RuleStatus.VERIFY],
            skipped=status_counts[RuleStatus.SKIPPED],
            system_errors=status_counts[RuleStatus.SYSTEM_ERROR],
            rule_results=qc_items,
            action_items=action_items,
            suggestions=suggestions,
            processing_warnings=extraction_result.warnings,
        )


# Create global processor instance
qc_processor = SmartQCProcessor()
