"""
Week 3 Integration — Full Three-Tier Pipeline (Days 13-18)

Connects all five layers:
  Layer 1: Adaptive OCR (Day 7) → SpatialWordMaps per page
  Layer 1: Text Normalization (Day 8) → normalized page texts
  Layer 1: Document Classification (Day 9) → document type + AMC ID
  Layer 1: Table Detection (Day 10) → structured tables
  Layer 2: Tier 3 Spatial Extraction (Weeks 1-2) → first-pass field results
  Layer 2: Tier 1 LLM Extraction (Day 13-14) → fills gaps in narrative/checkbox fields
  Layer 2: Tier 2 Embedding Extraction (Day 15-16) → fills remaining gaps by semantic similarity
  Layer 2: Tier Merger (Day 17) → single confident result per field
  Layer 2: Document Reconciler (Day 18) → cross-field and cross-page validation

The three-tier ensemble pattern:
  1. Tier 3 (spatial) runs first — fastest, most reliable for structural fields
  2. Tier 1 (LLM) fills gaps for narrative/checkbox/ambiguous fields
  3. Tier 2 (embeddings) fills remaining gaps via semantic similarity
  4. Merger combines with confidence scoring
  5. Reconciler validates cross-field consistency

Usage:
    from app.ocr.pipeline import process_document
    result = process_document(Path("report.pdf"))
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
    """Complete extraction output for one document — all three tiers merged."""
    path: str
    document_id: str
    classification_type: str
    classification_confidence: float
    amc_id: Optional[str]
    total_pages: int
    digital_pages: int
    scanned_pages: int
    file_hash: str
    processing_time_ms: int

    # Tier counts for observability
    tier3_found: int = 0
    tier1_found: int = 0
    tier2_found: int = 0
    merged_found: int = 0
    agreement_all: int = 0
    agreement_partial: int = 0

    # Final merged ExtractionResultSet
    extraction_result_set: Optional[object] = None

    full_text: str = ""
    page_texts: Dict[int, str] = field(default_factory=dict)
    table_count: int = 0
    avg_text_quality: float = 1.0


def process_document(
    path: Path,
    document_id: Optional[str] = None,
    document_type_override: Optional[str] = None,
    persist_metadata: bool = True,
    use_llm: bool = True,
    use_embeddings: bool = True,
    run_extraction: bool = True,
) -> PipelineResult:
    """
    Run the complete three-tier extraction pipeline on a PDF.

    Args:
        path: Path to the PDF file
        document_id: Identifier for DB storage (defaults to file name)
        document_type_override: Skip classification and use this type
        persist_metadata: Write OCR metadata and classification to DB
        use_llm: deprecated no-op (the local model tier was removed); kept for
            call-site compatibility. Extraction here uses spatial + embeddings.
        use_embeddings: Enable Tier 2 embedding extraction
        run_extraction: Run the full extraction pipeline
    """
    from app.ocr.adaptive_ocr import adaptive_ocr
    from app.ocr.normalizers import normalize
    from app.services.document_classifier import document_classifier
    from app.ocr.table_detector import table_detector
    from app.extraction.spatial_tier3 import SpatialTier3Extractor
    from app.extraction.tier2_embeddings import EmbeddingTier2Extractor
    from app.extraction.tier_merger import TierMerger
    from app.extraction.document_reconciler import reconcile
    from app.core.result import ExtractionResult, ExtractionResultSet, ExtractionMethod

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
        page.normalized_text = norm_result.normalized
        page.metadata.normalization_log = [
            {"t": e.transform, "b": e.before[:40], "a": e.after[:40]}
            for e in norm_result.events[:10]
        ] if norm_result.events else []

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

    # ---- Step 5: Persist OCR metadata ----
    if persist_metadata:
        try:
            adaptive_ocr.persist_ocr_metadata(adaptive_doc, doc_id)
        except Exception as exc:
            logger.warning("OCR metadata persist failed: %s", exc)

    if not run_extraction:
        elapsed = int((time.time() - start) * 1000)
        return PipelineResult(
            path=str(path), document_id=doc_id,
            classification_type=doc_type, classification_confidence=cls_confidence,
            amc_id=amc_id, total_pages=adaptive_doc.total_pages,
            digital_pages=adaptive_doc.digital_page_count,
            scanned_pages=adaptive_doc.scanned_page_count,
            file_hash=adaptive_doc.file_hash, processing_time_ms=elapsed,
            full_text=adaptive_doc.full_text, page_texts=normalized_pages,
            table_count=table_count,
        )

    # ---- Step 6: Tier 3 — Spatial extraction ----
    spatial_extractor = SpatialTier3Extractor()
    tier3_result_set = spatial_extractor.extract(path, doc_type)
    tier3_results = {r.canonical_name: r for _, r in tier3_result_set}
    tier3_found = len([r for r in tier3_results.values() if r.found])

    # ---- Step 7: (removed) the local LLM tier — extraction now relies on
    # spatial + embeddings here; the live QC path uses the Groq overlays in
    # app/qc/transaction.py. tier1_results stays empty so the merger is unchanged.
    tier1_results: Dict[str, ExtractionResult] = {}
    tier1_found = 0

    # ---- Step 8: Tier 2 — Embedding extraction for remaining gaps ----
    tier2_results: Dict[str, ExtractionResult] = {}
    if use_embeddings:
        try:
            # What's still missing after spatial + LLM?
            combined_found = {
                **{k: v for k, v in tier3_results.items() if v.found},
                **{k: v for k, v in tier1_results.items() if v.found},
            }
            embedding_extractor = EmbeddingTier2Extractor()
            tier2_results = embedding_extractor.extract_missing_fields(
                normalized_pages, doc_type, combined_found
            )
        except Exception as exc:
            logger.warning("Tier 2 embedding extraction failed: %s", exc)
    tier2_found = len([r for r in tier2_results.values() if r.found])

    # ---- Step 9: Tier Merger (Day 17) ----
    merger = TierMerger()
    merged = merger.merge(tier3_results, tier1_results, tier2_results, doc_type)

    # ---- Step 10: Document Reconciler (Day 18) ----
    flat_results = {
        fname: mfr.to_extraction_result()
        for fname, mfr in merged.items()
    }
    flat_results = reconcile(flat_results)

    # ---- Step 11: Build final ExtractionResultSet ----
    final_rs = ExtractionResultSet(
        document_path=str(path),
        document_type=doc_type,
        amc_id=amc_id,
        total_pages=adaptive_doc.total_pages,
        ocr_method="three_tier_spatial_llm_embedding",
    )
    for canonical, result in flat_results.items():
        final_rs.add(result)
    final_rs.finalize()

    # ---- Step 12: Persist extraction results ----
    if persist_metadata:
        try:
            _persist_extraction_results(doc_id, amc_id, doc_type, final_rs)
        except Exception as exc:
            logger.warning("Extraction results persist failed: %s", exc)

    # ---- Assemble result ----
    avg_quality = (
        sum(p.metadata.text_quality_score for p in adaptive_doc.pages)
        / adaptive_doc.total_pages
    ) if adaptive_doc.total_pages > 0 else 1.0

    elapsed_ms = int((time.time() - start) * 1000)

    agreement_all = sum(1 for mfr in merged.values() if mfr.agreement_pattern == "all")
    agreement_partial = sum(
        1 for mfr in merged.values()
        if mfr.agreement_pattern in ("t1_t3", "t1_t2", "t2_t3")
    )

    result = PipelineResult(
        path=str(path), document_id=doc_id,
        classification_type=doc_type, classification_confidence=cls_confidence,
        amc_id=amc_id, total_pages=adaptive_doc.total_pages,
        digital_pages=adaptive_doc.digital_page_count,
        scanned_pages=adaptive_doc.scanned_page_count,
        file_hash=adaptive_doc.file_hash, processing_time_ms=elapsed_ms,
        tier3_found=tier3_found, tier1_found=tier1_found, tier2_found=tier2_found,
        merged_found=len(final_rs.found_results()),
        agreement_all=agreement_all, agreement_partial=agreement_partial,
        extraction_result_set=final_rs,
        full_text=adaptive_doc.full_text, page_texts=normalized_pages,
        table_count=table_count, avg_text_quality=round(avg_quality, 3),
    )

    logger.info(
        "Pipeline complete: %s | type=%s | pages=%d | "
        "T3=%d T1=%d T2=%d merged=%d | agree_all=%d | %dms",
        path.name, doc_type, adaptive_doc.total_pages,
        tier3_found, tier1_found, tier2_found,
        result.merged_found, agreement_all, elapsed_ms,
    )
    return result


def _persist_extraction_results(doc_id, amc_id, doc_type, result_set) -> None:
    """Persist all merged extraction results to adaptive_extraction_results."""
    from app.database import get_db
    from app.models.db_models import ExtractionResultRow
    from app.config import MODEL_VERSION

    with get_db() as session:
        for canonical, result in result_set:
            row = ExtractionResultRow(
                document_id=doc_id,
                amc_id=amc_id,
                document_type=doc_type,
                field_name=canonical,
                field_value=result.value,
                raw_source_text=result.raw_source_text,
                extraction_method=result.extraction_method,
                confidence_score=result.effective_confidence,
                source_page=result.source_page,
                normalization_steps=json.dumps(result.normalization_applied or []),
                sanity_check_failed=result.sanity_check_failed,
                sanity_check_reason=result.sanity_check_reason,
                hallucination_flag=result.hallucination_flag,
                cross_validated=result.cross_validated,
                cross_validated_source=result.cross_validated_source,
                model_version=MODEL_VERSION,
            )
            session.add(row)
