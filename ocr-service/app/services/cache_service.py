"""
OCR Cache Service — stores and retrieves per-page OCR results by PDF file hash.

When a PDF is submitted:
  1. Compute SHA-256 hash of the file
  2. Check cache: SELECT * FROM page_ocr_results WHERE file_hash = ?
  3. If ALL pages found → return cached PageText objects instantly (0 OCR cost)
  4. If NOT found → run OCR → save results → next request is instant

Also saves per-field extracted values with confidence scores.
"""

import logging
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Graceful degradation if DB is not available
try:
    from app.database import get_db, is_db_available
    from app.models.db_models import (
        Document, PageOCRResult, ExtractedFieldRecord, RuleResultRecord
    )
    DB_AVAILABLE = is_db_available()
    if DB_AVAILABLE:
        logger.info("Database available — OCR caching enabled")
    else:
        logger.info("Database not available — caching disabled, results not persisted")
except Exception as e:
    DB_AVAILABLE = False
    logger.info("Cache service init failed (%s) — running without persistence", e)


def _db_ok() -> bool:
    """Runtime DB check — handles cases where DB came up after startup."""
    global DB_AVAILABLE
    if not DB_AVAILABLE:
        try:
            from app.database import is_db_available
            DB_AVAILABLE = is_db_available()
        except Exception:
            pass
    return DB_AVAILABLE


NULL_TEXT_SENTINEL = "__NOT_PROVIDED__"
NOT_FOUND_SENTINEL = "__NOT_FOUND__"
NO_PAGE_SENTINEL = 0
NO_BBOX_SENTINEL = 0.0


def _clean_text(value: Any, *, default: str = NULL_TEXT_SENTINEL) -> str:
    """Persist explicit sentinel text instead of SQL NULL."""
    if value is None:
        return default
    text = str(value)
    return text if text != "" else default


def _clean_optional_text(value: Any) -> str:
    return _clean_text(value, default="")


def _clean_json(value: Any, *, empty: Any) -> str:
    if value is None:
        value = empty
    return json.dumps(value)


def _clean_page(value: Any) -> int:
    try:
        page = int(value)
        return page if page > 0 else NO_PAGE_SENTINEL
    except Exception:
        return NO_PAGE_SENTINEL


def _clean_float(value: Any) -> float:
    try:
        return float(value) if value is not None else NO_BBOX_SENTINEL
    except Exception:
        return NO_BBOX_SENTINEL


def _rule_target_field(rule_id: str) -> str:
    """Best checklist field anchor for rules that do not set target_field."""
    mapping = {
        "S-1": "property_address", "S-2": "borrower_name", "S-3": "owner_of_public_record",
        "S-4": "legal_description", "S-5": "neighborhood_name", "S-6": "census_tract",
        "S-7": "occupant_status", "S-8": "special_assessments", "S-9": "hoa_dues",
        "S-10": "lender_name", "S-11": "property_rights", "S-12": "offered_for_sale_12mo",
        "C-1": "contract_analyzed", "C-2": "contract_price", "C-3": "owner_of_public_record",
        "C-4": "financial_assistance", "C-5": "personal_property",
        "N-1": "neighborhood_characteristics", "N-2": "housing_trends",
        "N-3": "one_unit_housing_price_age", "N-4": "present_land_use_total",
        "N-5": "neighborhood_boundaries", "N-6": "neighborhood_description",
        "N-7": "market_conditions_commentary",
        "ST-1": "site_dimensions", "ST-2": "site_area", "ST-3": "site_shape",
        "ST-4": "view", "ST-5": "zoning_classification", "ST-6": "highest_best_use",
        "ST-7": "utilities", "ST-8": "flood_hazard", "ST-9": "utilities_typical",
        "ST-10": "adverse_site_conditions",
        "I-1": "improvement_general_description", "I-2": "foundation",
        "I-3": "exterior_description", "I-4": "interior_description",
        "I-5": "utilities", "I-6": "appliances", "I-7": "gla",
        "I-8": "additional_features", "I-9": "condition_rating",
        "I-10": "adverse_livability", "I-11": "neighborhood_conformity",
        "I-12": "additions", "I-13": "security_bars",
        "SCA-1": "comparable_market_summary", "SCA-2": "comparable_count",
        "SCA-3": "comparable_addresses", "SCA-4": "comparable_proximity",
        "SCA-5": "comparable_data_sources", "SCA-6": "verification_sources",
        "SCA-7": "financing_concessions", "SCA-8": "date_of_sale",
        "SCA-9": "location_rating", "SCA-10": "property_rights",
        "SCA-11": "site", "SCA-12": "view", "SCA-13": "design_style",
        "SCA-14": "quality_rating", "SCA-15": "actual_age",
        "SCA-16": "condition_rating", "SCA-17": "room_count_gla",
        "SCA-18": "basement", "SCA-19": "functional_utility",
        "SCA-20": "heating_cooling", "SCA-21": "garage_carport",
        "SCA-22": "porch_patio_deck", "SCA-23": "listing_comparables",
        "SCA-24": "unique_design", "SCA-25": "new_construction",
        "SCA-26": "square_footage", "SCA-27": "comparable_photos",
        "R-1": "value_reconciliation", "R-2": "final_opinion_value",
        "CA-1": "cost_approach", "CA-2": "cost_approach_completion",
        "IA-1": "rent_schedule", "IA-2": "operating_income_statement",
        "ADD-1": "commentary_standards", "ADD-2": "comparable_selection_commentary",
        "ADD-3": "dated_sales_commentary", "ADD-4": "market_conditions_addendum",
        "ADD-5": "inventory_analysis", "ADD-6": "comparables_matching",
        "ADD-7": "overall_trend", "ADD-8": "condo_coop_1004mc",
        "ADD-9": "uspap_prior_service",
        "PH-1": "subject_photos", "PH-2": "interior_photos",
        "PH-3": "additional_subject_photos", "PH-4": "fha_photo_requirements",
        "PH-5": "comparable_photos", "PH-6": "obsolescence_photos",
        "SK-1": "sketch_floor_plan", "SK-2": "floor_coverage",
        "SK-3": "sketch_dimensions", "SK-4": "outbuildings",
        "SK-5": "area_calculations",
        "M-1": "location_map", "M-2": "aerial_map", "M-3": "plat_map",
        "M-4": "flood_map",
        "DOC-1": "appraiser_license", "DOC-2": "eo_insurance",
        "DOC-3": "uad_dataset", "DOC-4": "trainee_signatures",
        "FHA-1": "fha_minimum_property_requirements", "FHA-2": "fha_case_number",
        "FHA-3": "fha_intended_use", "FHA-4": "fha_mpr_statement",
        "FHA-5": "fha_comp_recency", "FHA-6": "fha_repairs",
        "FHA-7": "space_heater", "FHA-8": "security_bars",
        "FHA-9": "fha_photos", "FHA-10": "remaining_economic_life",
        "FHA-11": "attic_crawl_inspection", "FHA-12": "well_septic",
        "FHA-13": "fha_appliances", "FHA-14": "fha_sketch",
        "USDA-1": "cost_approach", "MF-1": "rent_schedule",
        "MF-2": "operating_income_statement",
        "SIG-1": "signature_date", "SIG-2": "appraiser_information",
        "SIG-3": "supervisory_appraiser", "SIG-4": "email_address",
    }
    return mapping.get(rule_id or "", "checklist_rule")


# ── OCR Page Cache ─────────────────────────────────────────────────────────────

def get_document_id(file_hash: str) -> Optional[str]:
    """Return the document_id (UUID str) for a known file_hash, or None."""
    if not _db_ok():
        raise RuntimeError("database unavailable while persisting OCR cache")
    try:
        with get_db() as db:
            doc = db.query(Document).filter(Document.file_hash == file_hash).first()
            return str(doc.id) if doc else None
    except Exception as e:
        logger.info("get_document_id failed: %s", e)
        return None


def get_cached_ocr(file_hash: str, expected_pages: int):
    """
    Return a list of PageText objects if all pages are cached, else None.

    Args:
        file_hash:      SHA-256 hex digest of the PDF
        expected_pages: Total page count (to verify cache is complete)

    Returns:
        List[PageText] if cache hit, None if cache miss or DB unavailable
    """
    if not _db_ok():
        raise RuntimeError("database unavailable while persisting OCR cache")

    try:
        from app.ocr.ocr_pipeline import PageText, ExtractionMethod, OcrWord

        # Read ALL column values INSIDE the session — once the session closes,
        # SQLAlchemy ORM objects become detached and attribute access raises an error.
        with get_db() as db:
            rows = (
                db.query(PageOCRResult)
                .filter(PageOCRResult.file_hash == file_hash)
                .order_by(PageOCRResult.page_number)
                .all()
            )

            if len(rows) != expected_pages:
                return None  # Cache incomplete

            # Materialise all values while session is still open
            pages = [
                PageText(
                    page_number=r.page_number,
                    text=r.raw_text or "",
                    method=ExtractionMethod(r.extraction_method or "embedded"),
                    confidence=r.confidence_score or 0.5,
                    word_count=r.word_count or 0,
                    has_tables=r.has_tables or False,
                    words=[
                        OcrWord(**word)
                        for word in json.loads(r.word_json or "[]")
                    ],
                    hocr_text=r.hocr_text,
                )
                for r in rows
            ]

        logger.info("Cache HIT: %s (%d pages)", file_hash[:12], len(pages))
        return pages

    except Exception as e:
        logger.info("Cache lookup failed: %s", e)
        return None


def save_ocr_pages(file_hash: str, filename: str, pages) -> Optional[str]:
    """
    Persist OCR page results to the database.

    Returns:
        document_id (UUID string) if saved, None if DB unavailable
    """
    if not _db_ok():
        return None

    try:
        doc_id = uuid.uuid4()

        with get_db() as db:
            # Upsert document record (read inside session)
            existing = db.query(Document).filter(Document.file_hash == file_hash).first()
            if existing:
                doc_id = existing.id
            else:
                doc = Document(
                    id=doc_id,
                    file_hash=file_hash,
                    original_filename=filename,
                    page_count=len(pages),
                    upload_timestamp=datetime.utcnow(),
                )
                db.add(doc)
                db.flush()  # get DB-assigned id before child rows

            # Get existing page numbers in one query (avoid N+1)
            existing_page_nums = {
                row[0]
                for row in db.query(PageOCRResult.page_number)
                .filter(PageOCRResult.file_hash == file_hash)
                .all()
            }

            for pt in pages:
                if pt.page_number in existing_page_nums:
                    # Update via direct SQL to avoid session binding issues
                    db.query(PageOCRResult).filter(
                        PageOCRResult.file_hash == file_hash,
                        PageOCRResult.page_number == pt.page_number,
                    ).update({
                        "raw_text": pt.text,
                        "word_count": pt.word_count,
                        "confidence_score": pt.confidence,
                        "extraction_method": pt.method.value,
                        "has_tables": pt.has_tables,
                        "hocr_text": _clean_optional_text(getattr(pt, "hocr_text", None)),
                        "word_json": json.dumps([w.__dict__ for w in getattr(pt, "words", [])]),
                    })
                else:
                    page_row = PageOCRResult(
                        document_id=doc_id,
                        file_hash=file_hash,
                        page_number=pt.page_number,
                        extraction_method=pt.method.value,
                        word_count=pt.word_count,
                        confidence_score=pt.confidence,
                        raw_text=pt.text,
                        hocr_text=_clean_optional_text(getattr(pt, "hocr_text", None)),
                        word_json=json.dumps([w.__dict__ for w in getattr(pt, "words", [])]),
                        has_tables=pt.has_tables,
                    )
                    db.add(page_row)

        logger.info("Saved OCR cache: %s (%d pages)", file_hash[:12], len(pages))
        return str(doc_id)

    except Exception as e:
        logger.error("CRITICAL — OCR cache save failed for %s: %s", file_hash[:12], e)
        raise RuntimeError(f"OCR cache persistence failed: {e}") from e


# ── Field confidence save ──────────────────────────────────────────────────────

def _insert_extracted_fields_in_session(db, document_id: str, fields: Dict[str, Any],
                                        page_confidences: List[float], processing_job_id: str = None):
    """
    Core INSERT logic for extracted fields — runs inside a caller-managed session.
    Separated so save_extracted_fields and save_fields_and_rules_atomically can
    share the same implementation without duplicating code.
    """
    from app.models.field_meta import FieldMetaResult as FMR
    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(processing_job_id) if processing_job_id else None
    avg_conf = sum(page_confidences) / len(page_confidences) if page_confidences else 0.7
    HIGH_CONF = {"zip_code", "census_tract", "assessors_parcel_number", "tax_year"}
    LOW_CONF  = {"neighborhood_name", "legal_description", "owner_of_public_record"}

    existing_query = db.query(ExtractedFieldRecord).filter(ExtractedFieldRecord.document_id == doc_uuid)
    if job_uuid:
        existing_query = existing_query.filter(ExtractedFieldRecord.processing_job_id == job_uuid)
    else:
        existing_query = existing_query.filter(ExtractedFieldRecord.processing_job_id == None)
    existing_query.delete(synchronize_session=False)

    for field_name, value in fields.items():
        if isinstance(value, FMR):
            db_dict = value.to_db_dict()
            try:
                from app.services.confidence_calibration import calibrated_confidence
                db_dict["confidence_score"] = calibrated_confidence(
                    db_dict["field_name"], db_dict["extraction_method"], db_dict["confidence_score"])
            except Exception:
                pass
            record = ExtractedFieldRecord(
                document_id=doc_uuid,
                processing_job_id=job_uuid,
                field_name=db_dict["field_name"],
                field_value=_clean_text(
                    db_dict.get("field_value"),
                    default=NOT_FOUND_SENTINEL if (db_dict.get("extraction_status") or "").upper() != "FOUND" else NULL_TEXT_SENTINEL,
                ),
                extraction_status=db_dict.get("extraction_status") or ("FOUND" if db_dict.get("field_value") is not None else "NOT_FOUND"),
                confidence_score=db_dict["confidence_score"],
                source_document=db_dict.get("source_document") or "appraisal",
                source_page=_clean_page(db_dict.get("source_page")),
                bbox_x=_clean_float(db_dict.get("bbox_x")),
                bbox_y=_clean_float(db_dict.get("bbox_y")),
                bbox_w=_clean_float(db_dict.get("bbox_w")),
                bbox_h=_clean_float(db_dict.get("bbox_h")),
                parser=_clean_text(db_dict.get("parser"), default="unknown_parser"),
                extraction_method=_clean_text(db_dict.get("extraction_method"), default="not_found"),
                raw_ocr_text=_clean_text(db_dict.get("raw_ocr_text"), default=NOT_FOUND_SENTINEL),
                normalization_steps=db_dict.get("normalization_steps") or "[]",
                failure_reason=_clean_text(
                    db_dict.get("failure_reason"),
                    default="no_failure" if (db_dict.get("extraction_status") or "").upper() == "FOUND" else "not_found",
                ),
                correction_applied=db_dict["correction_applied"],
            )
        else:
            if value is None:
                conf, extraction_status, failure_reason = 0.0, "NOT_FOUND", "Legacy extractor returned None."
            elif field_name in HIGH_CONF:
                conf, extraction_status, failure_reason = round(min(1.0, avg_conf + 0.10), 3), "FOUND", None
            elif field_name in LOW_CONF:
                conf, extraction_status, failure_reason = round(max(0.0, avg_conf - 0.10), 3), "FOUND", None
            else:
                conf, extraction_status, failure_reason = round(avg_conf, 3), "FOUND", None
            record = ExtractedFieldRecord(
                document_id=doc_uuid, processing_job_id=job_uuid,
                field_name=field_name,
                field_value=str(value) if value is not None else NOT_FOUND_SENTINEL,
                extraction_status=extraction_status, confidence_score=conf,
                source_document="appraisal", source_page=NO_PAGE_SENTINEL,
                bbox_x=NO_BBOX_SENTINEL, bbox_y=NO_BBOX_SENTINEL,
                bbox_w=NO_BBOX_SENTINEL, bbox_h=NO_BBOX_SENTINEL,
                parser="legacy", extraction_method="regex",
                raw_ocr_text=str(value) if value is not None else NOT_FOUND_SENTINEL,
                normalization_steps="[]", failure_reason=failure_reason or "no_failure",
            )
        db.add(record)


def save_extracted_fields(document_id: str, fields: Dict[str, Any], page_confidences: List[float],
                          processing_job_id: str = None):
    """
    Persist extracted field values with confidence scores (own transaction).

    For atomic persistence with rule results in the same transaction use
    save_fields_and_rules_atomically() instead.
    """
    if not document_id:
        raise RuntimeError("document_id is required to persist extracted fields")
    if not _db_ok():
        raise RuntimeError("database unavailable while persisting extracted fields")
    try:
        with get_db() as db:
            _insert_extracted_fields_in_session(db, document_id, fields, page_confidences, processing_job_id)
    except Exception as e:
        logger.error("CRITICAL — extracted field save failed for document %s: %s", document_id, e)
        raise RuntimeError(f"Extracted field persistence failed: {e}") from e


# ── Rule results save ──────────────────────────────────────────────────────────

def _insert_rule_results_in_session(db, document_id: str, rule_results: list, processing_job_id: str = None):
    """
    Core INSERT logic for rule results — runs inside a caller-managed session.
    See save_rule_results for the standalone version.
    """
    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(processing_job_id) if processing_job_id else None

    existing_query = db.query(RuleResultRecord).filter(RuleResultRecord.document_id == doc_uuid)
    if job_uuid:
        existing_query = existing_query.filter(RuleResultRecord.processing_job_id == job_uuid)
    else:
        existing_query = existing_query.filter(RuleResultRecord.processing_job_id == None)

    existing_count = existing_query.count()
    expected_count = len(rule_results or [])
    if existing_count == expected_count and expected_count > 0:
        logger.info("Rule results already exist for document %s job %s; skipping duplicate save",
                    document_id, processing_job_id or "legacy")
        return
    if existing_count:
        logger.warning("Replacing incomplete/duplicate rule results for document %s job %s: existing=%s expected=%s",
                       document_id, processing_job_id or "legacy", existing_count, expected_count)
        existing_query.delete(synchronize_session=False)

    for r in rule_results or []:
        confidence = getattr(r, "confidence", None) or getattr(r, "field_confidence", None) or 0.0
        rule_id = _clean_text(getattr(r, "rule_id", None), default="UNKNOWN_RULE")
        status = getattr(r, "status", None)
        status_value = status.value if hasattr(status, "value") else str(status or "system_error")
        severity = getattr(r, "severity", None)
        severity_value = severity.value if hasattr(severity, "value") else str(severity or "STANDARD")
        target_field = getattr(r, "target_field", None) or _rule_target_field(rule_id)
        record = RuleResultRecord(
            document_id=doc_uuid,
            processing_job_id=job_uuid,
            rule_id=rule_id,
            rule_name=_clean_text(getattr(r, "rule_name", None), default=rule_id),
            status=status_value,
            message=_clean_text(getattr(r, "message", None), default="No rule message provided."),
            action_item=_clean_text(
                getattr(r, "action_item", None),
                default=getattr(r, "verify_question", None) or getattr(r, "rejection_text", None) or getattr(r, "message", None) or "No reviewer action required.",
            ),
            appraisal_value=_clean_text(getattr(r, "appraisal_value", None), default="__NO_APPRAISAL_VALUE__"),
            engagement_value=_clean_text(getattr(r, "engagement_value", None), default="__NO_ENGAGEMENT_VALUE__"),
            extracted_value=_clean_text(getattr(r, "extracted_value", None), default="__NO_EXTRACTED_VALUE__"),
            expected_value=_clean_text(getattr(r, "expected_value", None), default="__NO_EXPECTED_VALUE__"),
            confidence_score=confidence,
            target_field=target_field,
            rule_version=_clean_text(getattr(r, "rule_version", None), default="1.0"),
            severity=severity_value,
            review_required=bool(getattr(r, "review_required", False)),
            source_documents=_clean_json(getattr(r, "source_documents", None), empty=[]),
            compared_fields=_clean_json(getattr(r, "compared_fields", None), empty=[]),
            compared_values=_clean_json(getattr(r, "compared_values", None), empty={}),
            comparison_method=_clean_text(getattr(r, "comparison_method", None), default="not_comparison_based"),
            decision_path=_clean_json(getattr(r, "decision_path", None), empty=[]),
            exception_type=_clean_text(getattr(r, "exception_type", None), default="none"),
            exception_trace=_clean_text(getattr(r, "exception_trace", None), default=""),
            stage=_clean_text(getattr(r, "stage", None), default="rule_engine"),
            retry_eligible=getattr(r, "retry_eligible", False),
            source_page=_clean_page(getattr(r, "source_page", None)),
            bbox_x=_clean_float(getattr(r, "bbox_x", None)),
            bbox_y=_clean_float(getattr(r, "bbox_y", None)),
            bbox_w=_clean_float(getattr(r, "bbox_w", None)),
            bbox_h=_clean_float(getattr(r, "bbox_h", None)),
        )
        db.add(record)


def save_rule_results(document_id: str, rule_results: list, processing_job_id: str = None):
    """Persist rule results for a document (own transaction).

    For atomic persistence with extracted fields in the same transaction use
    save_fields_and_rules_atomically() instead.
    """
    if not document_id:
        raise RuntimeError("document_id is required to persist rule results")
    if not _db_ok():
        raise RuntimeError("database unavailable while persisting rule results")

    try:
        doc_uuid = uuid.UUID(document_id)
        job_uuid = uuid.UUID(processing_job_id) if processing_job_id else None
        with get_db() as db:
            _insert_rule_results_in_session(db, document_id, rule_results, processing_job_id)
    except Exception as e:
        logger.error("CRITICAL — rule_results save failed for document %s: %s", document_id, e)
        raise RuntimeError(f"Rule result persistence failed: {e}") from e


def save_fields_and_rules_atomically(
    document_id: str,
    fields: Dict[str, Any],
    page_confidences: List[float],
    rule_results: list,
    processing_job_id: str = None,
) -> None:
    """
    Persist both extracted fields AND rule results inside a single DB transaction.

    If field saving succeeds but rule saving fails (or vice versa) the entire
    operation is rolled back — neither partial write reaches the database.
    Call this instead of calling save_extracted_fields + save_rule_results
    sequentially whenever both must succeed together.
    """
    if not document_id:
        raise RuntimeError("document_id is required for atomic field+rule persistence")
    if not _db_ok():
        raise RuntimeError("database unavailable for atomic field+rule persistence")
    try:
        with get_db() as db:
            _insert_extracted_fields_in_session(db, document_id, fields, page_confidences, processing_job_id)
            _insert_rule_results_in_session(db, document_id, rule_results, processing_job_id)
        logger.info("Atomic field+rule save committed for document %s", document_id)
    except Exception as e:
        logger.error("CRITICAL — atomic field+rule save failed for document %s: %s", document_id, e)
        raise RuntimeError(f"Atomic persistence failed: {e}") from e
