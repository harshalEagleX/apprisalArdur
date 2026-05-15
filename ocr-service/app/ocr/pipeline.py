"""
Week 2 Integration — Full Layer One Pipeline

Connects: Adaptive OCR (Day 7) → Normalization (Day 8) → Classification (Day 9)
          → Table Detection (Day 10) → Extraction (Tier 3 + fuzzy, Day 11)

This is the production entry point for processing a document end-to-end.
Individual components remain independently testable — this just orchestrates.

Usage:
    from app.ocr.pipeline import process_document
    result = process_document(Path("report.pdf"))
    # result.classification tells you what document type was found
    # result.extraction_results contains all field results
    # result.tables contains detected table structures
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete Layer One output for one document."""
    path: str
    document_id: str
    classification_type: str       # "appraisal_report" | "engagement_letter" | ...
    classification_confidence: float
    amc_id: Optional[str]
    total_pages: int
    digital_pages: int
    scanned_pages: int
    file_hash: str
    processing_time_ms: int

    # Available after pipeline runs
    full_text: str = ""
    page_texts: Dict[int, str] = field(default_factory=dict)
    table_count: int = 0
    avg_text_quality: float = 1.0

    # ExtractionResultSet — populated by caller if needed
    extraction_result_set: Optional[object] = None


def process_document(
    path: Path,
    document_id: Optional[str] = None,
    document_type_override: Optional[str] = None,
    persist_metadata: bool = True,
    run_extraction: bool = True,
) -> PipelineResult:
    """
    Run the full Layer One pipeline on a PDF.

    Args:
        path: Path to the PDF file
        document_id: Identifier for DB storage (defaults to file name)
        document_type_override: Skip classification and use this type
        persist_metadata: Write OCR metadata and classification to DB
        run_extraction: Run Tier 3 extraction (Day 2 + fuzzy, Day 11)
    """
    from app.ocr.adaptive_ocr import adaptive_ocr
    from app.ocr.normalizers import normalize
    from app.services.document_classifier import document_classifier
    from app.ocr.table_detector import table_detector
    from app.extraction.tier3_pattern import Tier3PatternExtractor

    path = Path(path)
    doc_id = document_id or path.name
    start = time.time()

    # ---- Step 1: Adaptive OCR (Day 7) ----
    adaptive_doc = adaptive_ocr.process(path)

    # ---- Step 2: Normalize each page (Day 8) ----
    normalized_pages: Dict[int, str] = {}
    for page in adaptive_doc.pages:
        norm_result = normalize(page.raw_text)
        normalized_pages[page.page_number] = norm_result.normalized
        # Attach normalization log to metadata for DB persistence
        page.metadata.normalization_log = norm_result.events and [
            e.__dict__ for e in norm_result.events[:20]  # cap for storage
        ] or []
        page.normalized_text = norm_result.normalized

    # ---- Step 3: Document classification (Day 9) ----
    if document_type_override:
        doc_type = document_type_override
        cls_confidence = 1.0
        amc_id = None
    else:
        cls = document_classifier.classify(normalized_pages, adaptive_doc.total_pages)
        doc_type = cls.document_type
        cls_confidence = cls.type_confidence
        amc_id = cls.amc_id

        if persist_metadata:
            try:
                document_classifier.persist(cls, doc_id, str(path))
            except Exception as exc:
                logger.warning("Classification persist failed: %s", exc)

    # ---- Step 4: Table detection (Day 10) ----
    tables_by_page = table_detector.detect_document(normalized_pages)
    table_count = sum(len(v) for v in tables_by_page.values())

    # ---- Step 5: Persist OCR metadata (Day 7) ----
    if persist_metadata:
        try:
            adaptive_ocr.persist_ocr_metadata(adaptive_doc, doc_id)
        except Exception as exc:
            logger.warning("OCR metadata persist failed: %s", exc)

    # ---- Step 6: Extraction (Tier 3 + fuzzy, Days 2 + 11) ----
    extraction_result_set = None
    if run_extraction:
        from app.ocr.document import LoadedDocument, PageText
        # Build LoadedDocument from AdaptiveDocument for compatibility with Tier 3
        pages_compat = [
            PageText(
                page_number=p.page_number,
                text=normalized_pages.get(p.page_number, p.raw_text),
                word_count=p.word_count,
                is_scanned=(p.metadata.ocr_path == "tesseract"),
            )
            for p in adaptive_doc.pages
        ]
        loaded = LoadedDocument(
            path=str(path),
            total_pages=adaptive_doc.total_pages,
            pages=pages_compat,
            file_hash=adaptive_doc.file_hash,
        )
        extractor = Tier3PatternExtractor()
        extraction_result_set = extractor.extract(loaded, doc_type)

    # ---- Assemble result ----
    avg_quality = (
        sum(p.metadata.text_quality_score for p in adaptive_doc.pages) / adaptive_doc.total_pages
        if adaptive_doc.total_pages > 0 else 1.0
    )

    elapsed_ms = int((time.time() - start) * 1000)

    result = PipelineResult(
        path=str(path),
        document_id=doc_id,
        classification_type=doc_type,
        classification_confidence=cls_confidence,
        amc_id=amc_id,
        total_pages=adaptive_doc.total_pages,
        digital_pages=adaptive_doc.digital_page_count,
        scanned_pages=adaptive_doc.scanned_page_count,
        file_hash=adaptive_doc.file_hash,
        processing_time_ms=elapsed_ms,
        full_text=adaptive_doc.full_text,
        page_texts=normalized_pages,
        table_count=table_count,
        avg_text_quality=round(avg_quality, 3),
        extraction_result_set=extraction_result_set,
    )

    logger.info(
        "Pipeline complete: %s | type=%s (%.0f%%) | AMC=%s | %d pages (%d digital, %d scanned) | %d tables | %dms",
        path.name, doc_type, cls_confidence * 100, amc_id or "unknown",
        result.total_pages, result.digital_pages, result.scanned_pages,
        table_count, elapsed_ms,
    )
    return result
