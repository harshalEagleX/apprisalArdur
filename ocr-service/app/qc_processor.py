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
import os
import re
import time
from typing import Callable, Dict, List, Optional, Any, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

# Optional callback signature: (stage, message, sub_percent_0_to_1) -> None
ProgressReporter = Callable[[str, str, float], None]

from pydantic import BaseModel, Field as PydanticField

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
    get_cached_ocr, get_document_id, save_ocr_pages,
    save_extracted_fields, save_rule_results, save_fields_and_rules_atomically,
    DB_AVAILABLE,
    NULL_TEXT_SENTINEL, NOT_FOUND_SENTINEL, NO_PAGE_SENTINEL, NO_BBOX_SENTINEL,
    _clean_text, _clean_json, _clean_page, _clean_float, _rule_target_field,
)
from app.services import processing_lifecycle

DEFAULT_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "llava:7b")
DEFAULT_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")
from app.services.phase2_extraction import phase2_engine

logger = logging.getLogger(__name__)


class QCResultItem(BaseModel):
    """Individual rule result — Phase 3 adds severity and source_page."""
    rule_id: str
    rule_name: str
    status: str
    message: str
    action_item: Optional[str] = None
    details: Optional[Dict] = None
    appraisal_value: Optional[str] = None
    engagement_value: Optional[str] = None
    confidence: Optional[float] = None
    extracted_value: Optional[Any] = None
    expected_value: Optional[Any] = None
    verify_question: Optional[str] = None
    rejection_text: Optional[str] = None
    evidence: List[str] = PydanticField(default_factory=list)
    review_required: bool = False
    source_documents: List[str] = PydanticField(default_factory=list)
    compared_fields: List[str] = PydanticField(default_factory=list)
    compared_values: Optional[Dict[str, Any]] = None
    comparison_method: Optional[str] = None
    decision_path: List[str] = PydanticField(default_factory=list)
    exception_type: Optional[str] = None
    exception_trace: Optional[str] = None
    stage: Optional[str] = None
    retry_eligible: bool = False
    # Phase 3 additions
    severity: str = "STANDARD"
    source_page: Optional[int] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None
    target_field: Optional[str] = None
    field_confidence: Optional[float] = None
    auto_correctable: bool = False
    rule_version: str = "1.0"


class QCResults(BaseModel):
    """Complete QC results."""
    success: bool
    processing_time_ms: int
    total_pages: int
    extraction_method: str
    document_id: Optional[str] = None     # DB record ID — None if DB unavailable
    processing_job_id: Optional[str] = None
    cache_hit: bool = False               # True if OCR was served from cache
    model_provider: str = "ollama"
    model_name: str = DEFAULT_TEXT_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    
    # Extracted fields summary
    extracted_fields: Dict[str, Any] = {}
    extracted_field_details: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    
    # Rule results
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    verify: int = 0         # Legacy alias for review count
    review: int = 0
    not_executed: int = 0
    not_applicable: int = 0
    extraction_failed: int = 0
    ocr_low_confidence: int = 0
    system_error: int = 0
    source_missing: int = 0
    cross_doc_mismatch: int = 0
    status_counts: Dict[str, int] = {}
    
    rule_results: List[QCResultItem] = []
    
    # Action items for human review
    action_items: List[str] = []
    
    # Suggestions for improvement
    suggestions: List[str] = []
    
    # Non-rule processing notices, such as OCR fallback messages.
    processing_notices: List[str] = []
    supporting_document_missing: bool = False
    missing_supporting_documents: List[str] = []


class SmartQCProcessor:
    """
    Orchestrates the complete QC pipeline for appraisal documents.
    """
    
    def __init__(self, use_tesseract: bool = True, use_nlp_embeddings: bool = False):
        # use_preprocessing=True enables the full 5-step image pipeline:
        # grayscale → denoise → Otsu threshold → table-line removal → deskew
        # Digital PDFs should keep their embedded text layer; scanned/low-text
        # pages fall back to preprocessed Tesseract OCR.
        self.ocr_pipeline = OCRPipeline(
            use_tesseract=use_tesseract,
            force_image_ocr=False,
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
        model_provider: str = "ollama",
        model_name: Optional[str] = None,
        vision_model: Optional[str] = None,
        report_progress: Optional[ProgressReporter] = None,
        processing_job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        batch_file_id: Optional[str] = None,
        qc_result_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        traceparent: Optional[str] = None,
        tracestate: Optional[str] = None,
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
        model_provider = (model_provider or "ollama").strip().lower()
        model_name = (model_name or DEFAULT_TEXT_MODEL).strip()
        vision_model = (vision_model or DEFAULT_VISION_MODEL).strip()
        if not processing_job_id:
            created_job_id, _, _ = processing_lifecycle.create_or_get_job(
                idempotency_key=idempotency_key,
                source_document_hash=file_hash,
                original_filename=original_filename,
                correlation_id=correlation_id,
                batch_id=batch_id,
                batch_file_id=batch_file_id,
                qc_result_id=qc_result_id,
                model_provider=model_provider,
                model_name=model_name,
                vision_model=vision_model,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            processing_job_id = created_job_id
        if not processing_job_id:
            raise RuntimeError("Durable processing job is required before OCR processing can start")

        def _emit(stage: str, message: str, sub_percent: float) -> None:
            if report_progress is None:
                return
            try:
                report_progress(stage, message, sub_percent)
            except Exception as cb_exc:  # callback must never break the pipeline
                logger.debug("progress callback failed: %s", cb_exc)

        with processing_lifecycle.processing_context(processing_job_id, correlation_id, traceparent):
            processing_lifecycle.mark_job_started(processing_job_id, "cache_check")

            # ── Step 1: Check OCR Cache ─────────────────────────────────────
            _emit("appraisal_ocr", "Checking OCR cache for appraisal", 0.30)
            import fitz as _fitz
            with processing_lifecycle.stage("pdf_open"):
                try:
                    _doc = _fitz.open(pdf_path)
                    total_pages = len(_doc)
                    _doc.close()
                except Exception:
                    total_pages = 0

            cache_hit = False
            with processing_lifecycle.stage("cache_lookup", {"file_hash": file_hash, "total_pages": total_pages}):
                if file_hash and total_pages > 0:
                    cached_pages = get_cached_ocr(file_hash, total_pages)
                    if cached_pages:
                        logger.info("Cache HIT — skipping OCR for %s", file_hash[:12])
                        cache_hit = True
                        document_id = get_document_id(file_hash)
                        if not document_id:
                            raise RuntimeError("OCR cache hit has no durable document record")
                        # Reconstruct ExtractionResult from cached pages
                        from app.ocr.ocr_pipeline import ExtractionResult
                        extraction_result = ExtractionResult()
                        extraction_result.total_pages = total_pages
                        for pt in cached_pages:
                            extraction_result.page_index[pt.page_number] = pt.text
                            extraction_result.page_details.append(pt)
                            if getattr(pt, "words", None):
                                extraction_result.word_index[pt.page_number] = pt.words
                        missing_word_pages = [
                            page_num for page_num in range(1, total_pages + 1)
                            if not extraction_result.word_index.get(page_num)
                        ]
                        if missing_word_pages:
                            with processing_lifecycle.stage("word_geometry_rebuild", {"missing_pages": len(missing_word_pages)}):
                                rebuilt_word_index = self.ocr_pipeline.extract_word_geometry(pdf_path)
                            for page_num in missing_word_pages:
                                words = rebuilt_word_index.get(page_num)
                                if words:
                                    extraction_result.word_index[page_num] = words
                            for pt in extraction_result.page_details:
                                if not getattr(pt, "words", None):
                                    pt.words = extraction_result.word_index.get(pt.page_number, [])
                            logger.info(
                                "Rebuilt word geometry for %d cached page(s): %s",
                                len(missing_word_pages),
                                ",".join(str(p) for p in missing_word_pages[:20]),
                            )

            # ── Step 2: OCR Extraction (if not cached) ──────────────────────
            if cache_hit:
                _emit("appraisal_ocr", "Reusing cached OCR pages", 0.45)
            else:
                logger.info("Cache MISS — running OCR for %s", pdf_path)
                _emit("appraisal_ocr", "Running OCR on appraisal PDF", 0.32)
                with processing_lifecycle.stage("ocr_extract", {"total_pages": total_pages}):
                    extraction_result = self.ocr_pipeline.extract_all_pages(pdf_path)

                # Save to cache for next time
                if file_hash and extraction_result.page_details:
                    with processing_lifecycle.stage("ocr_cache_save"):
                        document_id = save_ocr_pages(
                            file_hash=file_hash,
                            filename=original_filename,
                            pages=extraction_result.page_details,
                        )
                    if not document_id:
                        raise RuntimeError("OCR cache persistence failed; durable document record is required")
                elif not file_hash:
                    raise RuntimeError("Source document hash is required for durable OCR processing")

            if not extraction_result.page_index:
                results = QCResults(
                    success=False,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    total_pages=0,
                    extraction_method="none",
                    processing_job_id=processing_job_id,
                    model_provider=model_provider,
                    model_name=model_name,
                    vision_model=vision_model,
                    processing_notices=["Failed to extract any text from PDF"]
                )
                processing_lifecycle.fail_job(processing_job_id, "Failed to extract any text from PDF", "ocr_extract")
                return results

            # Raw OCR/native extraction output remains the default source of truth.
            full_text = self.ocr_pipeline.get_full_text(extraction_result.page_index)

            _emit("phase2_extraction", "Extracting structured fields", 0.55)

            # Step 2: Phase 2 Multi-Layer Extraction
            with processing_lifecycle.stage("field_extraction_subject"):
                # Pass the PDF path so the Camelot comparable grid extractor can
                # access the file directly (Camelot requires the file path, not
                # the text stream).
                phase2_engine._pdf_path = pdf_path
                s_extract, field_meta = phase2_engine.extract_subject(
                    full_text,
                    extraction_result.page_index,
                    page_images=extraction_result.page_images,
                    word_index=extraction_result.word_index,
                )
            # Contract: still uses original extraction service (not yet Phase 2)
            with processing_lifecycle.stage("field_extraction_contract"):
                c_extract = extraction_service.extract_contract_section(full_text)
        
        # Source B: Site/Improvement extractor (dimensions, zoning, year built, comp count)
            from app.services.site_extractor import extract_advanced_fields
            with processing_lifecycle.stage("field_extraction_site_legacy"):
                legacy_fields = extract_advanced_fields(full_text)

        # Step 3: Map to AppraisalReportDomain Model
            report = self._map_extraction_to_report(s_extract, c_extract, legacy_fields)
            self._apply_comparables_from_field_meta(report, field_meta)
            self._apply_comparables_from_text(report, full_text)
        
        with processing_lifecycle.processing_context(processing_job_id, correlation_id, traceparent):
            # Step 4: Handle Engagement Letter
            engagement_letter = None
            supporting_document_missing = False
            missing_supporting_documents: List[str] = []
            with processing_lifecycle.stage("supporting_document_parse"):
                if engagement_letter_text:
                    eng_extract = extraction_service.extract_engagement_letter(engagement_letter_text)
                    engagement_letter = self._map_engagement_letter(eng_extract)
                else:
                    logger.info("No Engagement Letter found. Creating tagged proxy from Report data for non-cross-reference context.")
                    supporting_document_missing = True
                    missing_supporting_documents.append("ENGAGEMENT")
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

            # Step 4b: Populate neighborhood/site commentary from Phase 2 extraction
            with processing_lifecycle.stage("domain_mapping"):
                nbr_desc = field_meta.get("neighborhood_description")
                mkt_cmt  = field_meta.get("market_conditions_commentary")
                if nbr_desc and nbr_desc.value:
                    report.neighborhood.description_commentary = nbr_desc.value
                if mkt_cmt and mkt_cmt.value:
                    report.neighborhood.market_conditions_comment = mkt_cmt.value
                self._apply_neighborhood_from_field_meta(report, field_meta)
                self._apply_site_from_field_meta(report, field_meta)

            # Step 5: Parse contract PDF if provided OR if appraisal says it was analyzed
            purchase_agreement = None
            with processing_lifecycle.stage("purchase_agreement_parse"):
                if contract_text:
                    pa_extract = extraction_service.extract_purchase_agreement(contract_text)
                    purchase_agreement = pa_extract
                elif report.contract.did_analyze_contract:
                    logger.info("Appraisal indicates contract was analyzed but no contract PDF provided.")
                    supporting_document_missing = True
                    missing_supporting_documents.append("CONTRACT")

            vision_results = []
            if (vision_model or "").lower().startswith("llava"):
                _emit("vision", f"Running vision model {vision_model}", 0.65)
                try:
                    from app.services.vision_pipeline import analyze_pages_sync
                    with processing_lifecycle.stage("vision_analysis"):
                        vision_results = analyze_pages_sync(extraction_result.page_images)
                except Exception as e:
                    logger.info("llava:13b vision pipeline not run: %s", e)

            # Step 6: Create ValidationContext (pass field_meta for source_page + confidence)
            ctx = ValidationContext(
                report=report,
                engagement_letter=engagement_letter,
                purchase_agreement=purchase_agreement,
                field_meta=field_meta,
                raw_text=full_text,
                page_index=extraction_result.page_index,
                vision_results=vision_results,
                supporting_document_missing=supporting_document_missing,
                missing_supporting_documents=missing_supporting_documents,
                # Cross-page section map: rules can query section page locations
                # via ctx.doc_section_map.locate("neighborhood") etc.
                doc_section_map=getattr(phase2_engine, "_doc_section_map", None),
            )

            _emit("llm_enrichment", f"Enriching context with {model_name}", 0.70)
            try:
                from app.services.llm_enrichment import enrich_context_sync
                with processing_lifecycle.stage("llm_enrichment"):
                    enrich_context_sync(ctx)
            except Exception as e:
                logger.info("LLM enrichment not run before rules: %s", e)

            # Step 7: Execute rule engine
            logger.info("Executing rule engine")
            _emit("rules", "Executing QC rules", 0.90)
            with processing_lifecycle.stage("rule_engine"):
                rule_results = engine.execute(ctx)
                from app.rule_engine.cross_field_validator import CrossFieldValidator
                rule_results.extend(CrossFieldValidator().validate(ctx))

                # P2.8 — Mark field_meta entries as cross_validated when a rule
                # PASS result includes compared_values.  This is the signal for the
                # ML training loop that a field's extracted value was confirmed
                # against an external document (engagement letter, contract, etc.).
                if field_meta:
                    _CROSS_VALIDATED_RULE_FIELDS = {
                        "S-1":  ["property_address", "city", "state", "zip_code", "county"],
                        "S-2":  ["borrower_name"],
                        "S-3":  ["owner_of_public_record"],
                        "S-10": ["lender_name", "lender_address"],
                        "C-2":  ["contract_price", "contract_date"],
                        "XF-4": ["property_address"],
                    }
                    for r in rule_results:
                        if (getattr(r, "status", None) == RuleStatus.PASS
                                and getattr(r, "compared_values", None)):
                            for field_name in _CROSS_VALIDATED_RULE_FIELDS.get(
                                getattr(r, "rule_id", ""), []
                            ):
                                fm = field_meta.get(field_name)
                                if fm is not None and hasattr(fm, "cross_validated"):
                                    fm.cross_validated = True
                                    fm.cross_validated_source = "engagement_letter"

            _emit("persist", "Saving extracted fields and rule results", 0.96)
            # Step 8: Persist fields + rule results atomically so a partial
            # write (fields saved, rules not, or vice-versa) never reaches the DB.
            if document_id:
                page_confidences = [p.confidence for p in extraction_result.page_details]
                with processing_lifecycle.stage("persist_results"):
                    save_fields_and_rules_atomically(
                        document_id, field_meta, page_confidences, rule_results,
                        processing_job_id=processing_job_id
                    )

            _emit("assemble", "Assembling QC results", 0.99)
            # Step 9: Assemble results
            with processing_lifecycle.stage("assemble_response"):
                results = self._assemble_results(
                    extraction_result=extraction_result,
                    s_extract=s_extract,
                    rule_results=rule_results,
                    start_time=start_time,
                    document_id=document_id,
                    processing_job_id=processing_job_id,
                    cache_hit=cache_hit,
                    field_meta=field_meta,
                    model_provider=model_provider,
                    model_name=model_name,
                    vision_model=vision_model,
                    supporting_document_missing=supporting_document_missing,
                    missing_supporting_documents=missing_supporting_documents,
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
            is_pud=s.is_pud_checked,
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
        
        sales_count = legacy.get("comparableCount")
        sales = SalesComparisonSection(
            comparables_count_sales=sales_count if sales_count else None,
        )

        return AppraisalReport(
            subject=subject,
            contract=contract,
            site=site,
            improvements=improvements,
            sales_comparison=sales,
        )

    def _apply_neighborhood_from_field_meta(self, report: AppraisalReport, field_meta: dict) -> None:
        def value(key: str):
            meta = field_meta.get(key)
            return meta.value if meta and meta.value not in (None, "") else None

        def float_value(key: str):
            raw = value(key)
            if raw is None:
                return None
            try:
                return float(str(raw).replace(",", "").replace("$", ""))
            except (TypeError, ValueError):
                return None

        def int_value(key: str):
            raw = float_value(key)
            return int(raw) if raw is not None else None

        neighborhood = report.neighborhood
        for key, attr in {
            "location": "location",
            "built_up": "built_up",
            "growth_rate": "growth_rate",
            "property_values": "property_values",
            "demand_supply": "demand_supply",
            "marketing_time": "marketing_time",
            "neighborhood_boundaries": "boundaries_description",
        }.items():
            extracted = value(key)
            if extracted:
                setattr(neighborhood, attr, extracted)

        for key, attr in {
            "price_low": "price_low",
            "price_high": "price_high",
            "predominant_price": "predominant_price",
            "land_use_one_unit": "land_use_one_unit",
            "land_use_total": "land_use_total",
        }.items():
            extracted = float_value(key)
            if extracted is not None:
                setattr(neighborhood, attr, extracted)

        for key, attr in {
            "age_low": "age_low",
            "age_high": "age_high",
            "predominant_age": "predominant_age",
        }.items():
            extracted = int_value(key)
            if extracted is not None:
                setattr(neighborhood, attr, extracted)

    def _apply_site_from_field_meta(self, report: AppraisalReport, field_meta: dict) -> None:
        def value(key: str):
            meta = field_meta.get(key)
            return meta.value if meta and meta.value not in (None, "") else None

        def float_value(key: str):
            raw = value(key)
            if raw is None:
                return None
            try:
                return float(str(raw).replace(",", "").replace("$", ""))
            except (TypeError, ValueError):
                return None

        site = report.site
        if value("site_dimensions"):
            site.dimensions = value("site_dimensions")
        if float_value("site_area") is not None:
            site.area = float_value("site_area")
        if value("site_area_unit"):
            site.area_unit = value("site_area_unit")
        if value("site_shape"):
            site.shape = value("site_shape")
        if value("site_view"):
            site.view = value("site_view")

    def _apply_comparables_from_field_meta(
        self,
        report: AppraisalReport,
        field_meta: Optional[Dict[str, object]],
    ) -> None:
        """Populate comparable sales from Phase 2 extraction instead of defaulting to zero."""
        if not field_meta:
            return

        comparables: List[Comparable] = []
        for i in range(1, 4):
            address_meta = field_meta.get(f"comp_{i}_address")
            price_meta = field_meta.get(f"comp_{i}_sale_price")
            address = getattr(address_meta, "value", None)
            price_raw = getattr(price_meta, "value", None)

            if not address and not price_raw:
                continue

            price = None
            if price_raw:
                try:
                    price = float(re.sub(r"[,$]", "", str(price_raw)))
                except (TypeError, ValueError):
                    price = None

            comparables.append(Comparable(address=address, sale_price=price))

        if comparables:
            report.sales_comparison.comparables = comparables
            report.sales_comparison.comparables_count_sales = len(comparables)

    def _apply_comparables_from_text(self, report: AppraisalReport, full_text: str) -> None:
        """Fallback comparable parser for sales-grid rows when Phase 2 row parsing is weak."""
        existing = report.sales_comparison.comparables or []
        existing_prices = [comp.sale_price for comp in existing if comp.sale_price]
        if len(existing_prices) >= 3:
            return

        try:
            from app.services.comparable_extraction import comparable_grid_extractor
            extracted = comparable_grid_extractor.extract(full_text)
        except Exception as exc:
            logger.info("Comparable grid fallback not applied: %s", exc)
            return

        if not extracted.comparables:
            return

        report.sales_comparison.comparables = extracted.comparables
        report.sales_comparison.comparables_count_sales = len(extracted.comparables)

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
        processing_job_id: Optional[str] = None,
        cache_hit: bool = False,
        field_meta: Optional[Dict] = None,
        model_provider: str = "ollama",
        model_name: Optional[str] = None,
        vision_model: Optional[str] = None,
        supporting_document_missing: bool = False,
        missing_supporting_documents: Optional[List[str]] = None,
    ) -> QCResults:
        """Assemble final QC results."""
        model_provider = (model_provider or "ollama").strip().lower()
        model_name = (model_name or DEFAULT_TEXT_MODEL).strip()
        vision_model = (vision_model or DEFAULT_VISION_MODEL).strip()
        
        # Count strict output statuses.
        status_counts: Dict[str, int] = {}
        
        qc_items = []
        action_items = []
        
        for result in rule_results:
            external_status = self._public_status(result.status)
            status_counts[external_status] = status_counts.get(external_status, 0) + 1
            review_required = result.review_required or external_status in [
                "review",
                "fail",
                "extraction_failed",
                "ocr_low_confidence",
                "system_error",
                "source_missing",
                "cross_doc_mismatch",
            ]
            
            qc_items.append(QCResultItem(
                rule_id=_clean_text(result.rule_id, default="UNKNOWN_RULE"),
                rule_name=_clean_text(result.rule_name, default=result.rule_id or "UNKNOWN_RULE"),
                status=external_status,
                message=_clean_text(result.message, default="No rule message provided."),
                action_item=_clean_text(
                    result.action_item,
                    default=getattr(result, "verify_question", None) or getattr(result, "rejection_text", None) or result.message or "No reviewer action required.",
                ),
                details=result.details or {},
                appraisal_value=_clean_text(result.appraisal_value, default="__NO_APPRAISAL_VALUE__"),
                engagement_value=_clean_text(result.engagement_value, default="__NO_ENGAGEMENT_VALUE__"),
                confidence=getattr(result, "confidence", None) if getattr(result, "confidence", None) is not None else 0.0,
                extracted_value=_clean_text(getattr(result, "extracted_value", None), default="__NO_EXTRACTED_VALUE__"),
                expected_value=_clean_text(getattr(result, "expected_value", None), default="__NO_EXPECTED_VALUE__"),
                verify_question=_clean_text(getattr(result, "verify_question", None), default=""),
                rejection_text=_clean_text(getattr(result, "rejection_text", None), default=""),
                evidence=getattr(result, "evidence", []),
                review_required=review_required,
                source_documents=getattr(result, "source_documents", []) or [],
                compared_fields=getattr(result, "compared_fields", []) or [],
                compared_values=getattr(result, "compared_values", None) or {},
                comparison_method=_clean_text(getattr(result, "comparison_method", None), default="not_comparison_based"),
                decision_path=getattr(result, "decision_path", []) or [],
                exception_type=_clean_text(getattr(result, "exception_type", None), default="none"),
                exception_trace=_clean_text(getattr(result, "exception_trace", None), default=""),
                stage=_clean_text(getattr(result, "stage", None), default="rule_engine"),
                retry_eligible=getattr(result, "retry_eligible", False),
                severity=result.severity.value if hasattr(result.severity, "value") else str(result.severity),
                source_page=_clean_page(result.source_page),
                bbox_x=_clean_float(getattr(result, "bbox_x", None)),
                bbox_y=_clean_float(getattr(result, "bbox_y", None)),
                bbox_w=_clean_float(getattr(result, "bbox_w", None)),
                bbox_h=_clean_float(getattr(result, "bbox_h", None)),
                target_field=getattr(result, "target_field", None) or _rule_target_field(result.rule_id),
                field_confidence=result.field_confidence if result.field_confidence is not None else 0.0,
                auto_correctable=result.auto_correctable,
                rule_version=result.rule_version,
            ))
            
            # Collect action items from rules that need reviewer action.
            if result.action_item and review_required:
                action_items.append(f"[{result.rule_id}] {result.action_item}")
        
        # Get improvement suggestions
        suggestions = engine.get_improvement_suggestions()
        
        # Primary extraction method (most frequent across pages)
        methods = [p.method.value for p in extraction_result.page_details]
        primary_method = max(set(methods), key=methods.count) if methods else "unknown"

        # Per-field confidence: use Phase 2 FieldMetaResult scores when available
        field_confidence: Dict[str, float] = {}
        extracted_field_details: Dict[str, Any] = {}
        for field_name, value in s_extract.model_dump().items():
            meta_entry = (field_meta or {}).get(field_name)
            if meta_entry is not None and hasattr(meta_entry, "effective_confidence"):
                field_confidence[field_name] = round(meta_entry.effective_confidence, 3)
                extracted_field_details[field_name] = meta_entry.to_db_dict() if hasattr(meta_entry, "to_db_dict") else {}
            elif value is None:
                field_confidence[field_name] = 0.0
                extracted_field_details[field_name] = {
                    "field_name": field_name,
                    "field_value": NOT_FOUND_SENTINEL,
                    "extraction_status": "NOT_FOUND",
                    "confidence": 0.0,
                    "failure_reason": "No structured metadata was produced for this field.",
                }
            else:
                field_confidence[field_name] = 0.7
                extracted_field_details[field_name] = {
                    "field_name": field_name,
                    "field_value": value,
                    "extraction_status": "FOUND",
                    "confidence": 0.7,
                    "failure_reason": "no_failure",
                }

        review_count = sum(1 for item in qc_items if item.review_required)

        return QCResults(
            success=True,
            processing_time_ms=int((time.time() - start_time) * 1000),
            total_pages=extraction_result.total_pages,
            extraction_method=primary_method,
            document_id=document_id,
            processing_job_id=processing_job_id,
            cache_hit=cache_hit,
            model_provider=model_provider,
            model_name=model_name,
            vision_model=vision_model,
            extracted_fields=s_extract.model_dump(),
            extracted_field_details=extracted_field_details,
            field_confidence=field_confidence,
            total_rules=len(rule_results),
            passed=status_counts.get("pass", 0),
            failed=status_counts.get("fail", 0),
            verify=review_count,
            review=review_count,
            not_executed=status_counts.get("not_executed", 0),
            not_applicable=status_counts.get("not_applicable", 0),
            extraction_failed=status_counts.get("extraction_failed", 0),
            ocr_low_confidence=status_counts.get("ocr_low_confidence", 0),
            system_error=status_counts.get("system_error", 0),
            source_missing=status_counts.get("source_missing", 0),
            cross_doc_mismatch=status_counts.get("cross_doc_mismatch", 0),
            status_counts=status_counts,
            rule_results=qc_items,
            action_items=action_items,
            suggestions=suggestions,
            processing_notices=extraction_result.notices,
            supporting_document_missing=supporting_document_missing,
            missing_supporting_documents=missing_supporting_documents or [],
        )

    def _public_status(self, status: RuleStatus) -> str:
        if isinstance(status, RuleStatus):
            return status.value
        return str(status)


# Create global processor instance
qc_processor = SmartQCProcessor()
