"""
End-to-end pipeline runner — extract, classify, validate, route, persist.

This is the single orchestration point that takes a PDF from disk all the way
to populated database rows. It ties together components that previously ran in
isolation (the layered extractor produced results but never persisted them; the
classifier, validator, and routing config were only reachable from separate API
endpoints). One call here now produces a complete, auditable record across every
adaptive_* table — satisfying P-5 (keep raw inputs alongside outputs) and P-11
(observability) for the whole document journey.

Flow (each stage degrades independently — P-6):

    PDF
     ├─ classify            → adaptive_document_classifications
     ├─ per-page OCR meta   → adaptive_page_ocr_results
     ├─ run_full_extraction → adaptive_extraction_results  (with routing decision)
     └─ semantic validation → adaptive_validation_results

The strong layered orchestrator (run_full_extraction, ~120-170 fields on real
appraisals) is the extractor — not the bare Tier3 pattern extractor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_VALID_TYPES = {"appraisal_report", "engagement_letter", "sales_contract", "qc_checklist"}


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _route(confidence: float, thresholds: dict) -> str:
    """Map a confidence score to a routing decision using per-field thresholds."""
    if confidence >= thresholds.get("auto_accept", 0.90):
        return "auto_accept"
    if confidence >= thresholds.get("review", 0.65):
        return "review"
    return "mandatory_review"


def process_and_persist(
    pdf_path,
    document_type: Optional[str] = None,
    amc_id: Optional[str] = None,
    run_id: Optional[str] = None,
    store: bool = True,
) -> dict:
    """
    Run the full pipeline on one PDF and persist every stage to the DB.

    document_type: if None, the document classifier decides.
    amc_id: if None, the classifier's AMC match (if any) is used.
    Returns a summary dict (also usable as an API response).
    """
    import fitz

    from app.config import MODEL_VERSION
    from app.core.schema import schema_loader
    from app.extraction.layers.orchestrator import run_full_extraction
    from app.services.document_classifier import document_classifier

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Document not found: {pdf_path}")

    document_id = pdf_path.name
    run_id = run_id or f"run-{int(time.time())}"
    started = time.time()

    # ── Read page text (used by classifier + per-page OCR metadata) ──────────
    text_by_page: Dict[int, str] = {}
    try:
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        for i in range(total_pages):
            text_by_page[i + 1] = doc[i].get_text("text")
        doc.close()
    except Exception as exc:
        raise ValueError(f"Failed to open PDF: {exc}") from exc

    # ── Stage 1: classification ──────────────────────────────────────────────
    classification = None
    try:
        classification = document_classifier.classify(text_by_page, total_pages=total_pages)
        if document_type is None:
            document_type = classification.document_type
        if amc_id is None:
            amc_id = classification.amc_id
    except Exception as exc:
        logger.warning("Classification failed for %s: %s", document_id, exc)

    if document_type not in _VALID_TYPES:
        document_type = "appraisal_report"

    # ── Stage 2: extraction (strong layered orchestrator) ────────────────────
    result_set = run_full_extraction(
        pdf_path, document_type, use_paddle=True, use_llm=False, use_embeddings=True
    )

    # ── Stage 3: semantic validation (self-persists when store=True) ─────────
    validation_results = []
    try:
        from app.services.semantic_validator import validate
        validation_results = validate(result_set, document_id, persist=store)
    except Exception as exc:
        logger.warning("Validation failed for %s: %s", document_id, exc)

    # ── Stage 4: persist classification, page OCR meta, extraction rows ──────
    persisted = {"extraction": 0, "page_ocr": 0, "classification": 0}
    if store:
        try:
            from app.database import get_db
            from app.models.db_models import (
                DocumentClassificationRow,
                ExtractionResultRow,
                PageOcrResultRow,
            )
            from app.services.routing_config import get_thresholds

            file_hash = _file_hash(pdf_path)

            with get_db() as session:
                # Classification
                if classification is not None:
                    session.add(DocumentClassificationRow(
                        document_id=document_id,
                        document_path=str(pdf_path),
                        document_type=classification.document_type,
                        type_confidence=classification.type_confidence,
                        keyword_scores_json=json.dumps(classification.keyword_scores),
                        amc_id=classification.amc_id,
                        amc_template_version=getattr(classification, "amc_version", None),
                        amc_match_score=getattr(classification, "amc_score", None),
                        fingerprint_json=json.dumps(classification.fingerprint),
                        total_pages=total_pages,
                    ))
                    persisted["classification"] = 1

                # Per-page OCR metadata (word counts + path chosen per page)
                for page_num, text in text_by_page.items():
                    wc = len(text.split())
                    ocr_path = "pymupdf_direct" if wc >= 30 else "ocr_scanned"
                    session.add(PageOcrResultRow(
                        document_id=document_id,
                        page_number=page_num,
                        ocr_path=ocr_path,
                        word_count_raw=wc,
                        word_count_ocr=wc,
                        file_hash=file_hash,
                        raw_text_length=len(text),
                        normalized_text_length=len(text),
                    ))
                    persisted["page_ocr"] += 1

                # Extraction results (with routing decision per field)
                for canonical, result in result_set:
                    thresholds = get_thresholds(canonical, amc_id)
                    routing = _route(result.effective_confidence, thresholds) if result.found else "mandatory_review"
                    session.add(ExtractionResultRow(
                        document_id=document_id,
                        amc_id=amc_id,
                        document_type=document_type,
                        document_path=str(pdf_path),
                        total_pages=result_set.total_pages or total_pages,
                        field_name=canonical,
                        field_value=result.value,
                        raw_source_text=result.raw_source_text,
                        extraction_method=result.extraction_method,
                        confidence_score=result.effective_confidence,
                        source_page=result.source_page,
                        char_start=result.char_start,
                        normalization_steps=json.dumps(result.normalization_applied or []),
                        sanity_check_failed=result.sanity_check_failed,
                        hallucination_flag=result.hallucination_flag,
                        routing=routing,
                        model_version=MODEL_VERSION,
                        run_id=run_id,
                    ))
                    persisted["extraction"] += 1
        except Exception as exc:
            logger.error("DB persist failed for %s: %s", document_id, exc)

    found = result_set.found_results()
    elapsed_ms = int((time.time() - started) * 1000)

    summary = {
        "document_id": document_id,
        "document_path": str(pdf_path),
        "document_type": document_type,
        "amc_id": amc_id,
        "classification": {
            "type": classification.document_type if classification else None,
            "confidence": classification.type_confidence if classification else None,
        },
        "total_pages": total_pages,
        "fields_found": len(found),
        "fields_total": len(result_set),
        "validation": {
            "rules": len(validation_results),
            "fail": sum(1 for r in validation_results if r.result == "fail"),
            "warning": sum(1 for r in validation_results if r.result == "warning"),
            "pass": sum(1 for r in validation_results if r.result == "pass"),
        },
        "persisted": persisted,
        "run_id": run_id,
        "elapsed_ms": elapsed_ms,
    }
    logger.info(
        "Pipeline: %s | type=%s | %d/%d fields | persisted=%s | %dms",
        document_id, document_type, len(found), len(result_set), persisted, elapsed_ms,
    )
    return summary
