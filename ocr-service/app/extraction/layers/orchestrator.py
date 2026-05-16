"""
Extraction Orchestrator

Runs all extraction layers concurrently (ThreadPoolExecutor).
Each layer is independent — failure in one never blocks others.
Results are merged by confidence score.

Architecture (all parallel):

  PDF
   ├──[Thread 1]── L0 pdfplumber      → words + bordered tables
   ├──[Thread 2]── L1 OpenCV visual   → Yes/No checkbox fill density
   ├──[Thread 3]── L2 Grid resolver   → price/age/land-use grids
   ├──[Thread 4]── L3 PaddleOCR       → scanned pages (if any)
   └──[Thread 5]── L4 Spatial/Drawing → existing spatial + X-mark checkbox

                        ↓ (after all complete)
                   Merge by confidence
                        ↓
              ExtractionResultSet (253 fields)
                        ↓
              Semantic Validation → PASS/FAIL/VERIFY
                        ↓
              QC Report → Java Backend → Frontend
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional

from app.core.result import ExtractionMethod, ExtractionResult, ExtractionResultSet
from app.core.schema import schema_loader

logger = logging.getLogger(__name__)

# Confidence scores per source (higher = more trusted for that field)
_CONF = {
    "visual_checkbox": 0.92,   # OpenCV pixel fill — direct visual evidence
    "drawing_checkbox": 0.92,  # X-mark in drawing layer — direct visual evidence
    "camelot_table":    0.90,  # Camelot Ghostscript-rendered table — 92-95% verified
    "uad_template":     0.89,  # UAD form known field positions — high confidence
    "grid_table":       0.88,  # pdfplumber table cell — precise coordinate match
    "spatial_label":    0.85,  # label→value spatial proximity
    "paddle_ocr":       0.80,  # PaddleOCR from scanned page
    "fuzzy_label":      0.72,  # fuzzy label match
    "embedding":        0.68,  # semantic embedding match
    "llm":              0.72,  # LLM with hallucination verification
}


def _make_result(field_name: str, value: str, doc_type: str,
                 method: str, confidence: float, page: int = 1) -> ExtractionResult:
    return ExtractionResult(
        canonical_name=field_name,
        document_type=doc_type,
        value=value,
        extraction_method=method,
        confidence=confidence,
        source_page=page,
        normalization_applied=[method],
    )


def _not_found(field_name: str, doc_type: str) -> ExtractionResult:
    return ExtractionResult(
        canonical_name=field_name,
        document_type=doc_type,
        extraction_method=ExtractionMethod.NOT_FOUND,
        confidence=0.0,
    )


def run_full_extraction(
    pdf_path: Path,
    document_type: str = "appraisal_report",
    use_paddle: bool = True,
    use_llm: bool = False,
    use_embeddings: bool = True,
) -> ExtractionResultSet:
    """
    Run all extraction layers concurrently and merge results.

    All 6 layers run in parallel threads:
      L0: pdfplumber words + tables
      L1: OpenCV Yes/No visual checkbox
      L2: pdfplumber grid resolver
      L3: PaddleOCR for scanned pages
      L4: Spatial label matching (existing)
      L4b: Camelot bordered table extraction (comparable grid, MCA)

    Results merged by confidence — highest confidence wins per field.
    Returns a complete ExtractionResultSet with all 253 fields.
    """
    pdf_path = Path(pdf_path)
    start = time.time()

    # ── Run all layers in parallel ──────────────────────────────────────────
    layer_results: Dict[str, Dict[str, str]] = {}

    def run_l0():
        from app.extraction.layers.l0_pdfplumber import extract_with_pdfplumber
        return "l0", extract_with_pdfplumber(pdf_path)

    def run_l1():
        from app.extraction.layers.l1_checkbox_visual import extract_checkboxes_visual
        return "l1", extract_checkboxes_visual(pdf_path, document_type)

    def run_l2():
        from app.extraction.layers.l2_grid_resolver import extract_grid_fields
        return "l2", extract_grid_fields(pdf_path)

    def run_l3():
        if not use_paddle:
            return "l3", {}
        from app.extraction.layers.l3_paddle_ocr import extract_scanned_pdf_with_paddle
        return "l3", extract_scanned_pdf_with_paddle(pdf_path)

    def run_l4():
        from app.extraction.spatial_tier3 import SpatialTier3Extractor
        extractor = SpatialTier3Extractor()
        rs = extractor.extract(pdf_path, document_type)
        return "l4", {r.canonical_name: r for _, r in rs if r.found}

    def run_l4b():
        """Camelot: Ghostscript-powered bordered table extraction.
        Best for: comparable sales adjustment grid, MCA addendum.
        Accuracy on real appraisals: 92-95%.
        Note: comp_N fields use template names (comp_N_sale_price) not indexed
        (comp_1_sale_price) because the schema stores them as templates.
        """
        from app.extraction.layers.l4_camelot import extract_with_camelot
        raw_camelot = extract_with_camelot(pdf_path)
        results = {}
        for fname, val in raw_camelot.items():
            if val and str(val).strip():
                # Accept all Camelot fields — don't filter by schema lookup
                # (comp_1/2/3 fields don't match comp_N schema template names)
                results[fname] = _make_result(
                    fname, str(val), document_type,
                    "camelot_table", _CONF["camelot_table"],
                )
        return "l4b", results

    def run_l5():
        """UAD Form Template Parser — fills Yes/No, grids, GLA, dates by known positions."""
        from app.extraction.layers.l5_uad_template import extract_with_uad_template
        raw = extract_with_uad_template(pdf_path)
        results = {}
        for fname, val in raw.items():
            if val:
                results[fname] = _make_result(
                    fname, str(val), document_type,
                    "uad_template", _CONF.get("uad_template", 0.88),
                )
        return "l5", results

    tasks = [run_l0, run_l1, run_l2, run_l3, run_l4, run_l4b, run_l5]

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(fn): fn.__name__ for fn in tasks}
        raw: Dict[str, object] = {}
        for future in as_completed(futures):
            try:
                layer_id, result = future.result()
                raw[layer_id] = result
            except Exception as exc:
                logger.warning("Layer %s failed: %s", futures[future], exc)

    # ── Merge results ────────────────────────────────────────────────────────
    # Priority (highest → lowest confidence):
    #   L1  visual checkbox    0.92  — pixel fill analysis, most direct
    #   L4b Camelot table      0.90  — Ghostscript-rendered, 92-95% verified accuracy
    #   L2  pdfplumber grid    0.88  — coordinate-based table cell
    #   L4  spatial label      0.85  — label proximity matching
    #   L3  PaddleOCR          0.80  — scanned page OCR
    # Higher confidence always wins. Same confidence → first found wins.

    merged: Dict[str, ExtractionResult] = {}
    schema = schema_loader

    # L4 — spatial extractor (baseline — always complete, fills all fields)
    l4 = raw.get("l4", {})
    for fname, result in l4.items():
        if result.found:
            merged[fname] = result

    # L4b — Camelot table extraction (comp grid, MCA — overrides spatial for table fields)
    l4b = raw.get("l4b", {})
    for fname, result in l4b.items():
        if hasattr(result, 'found') and result.found:
            if fname not in merged or merged[fname].effective_confidence < _CONF["camelot_table"]:
                merged[fname] = result

    # L1 — visual Yes/No checkboxes (override spatial for boolean fields)
    l1 = raw.get("l1", {})
    for fname, value in l1.items():
        fd = schema.get_field(fname)
        if not value:
            continue
        result = _make_result(fname, value, document_type, "visual_checkbox",
                              _CONF["visual_checkbox"])
        if fname not in merged or merged[fname].effective_confidence < _CONF["visual_checkbox"]:
            merged[fname] = result

    # L2 — grid resolver (fills price/land-use grids)
    l2 = raw.get("l2", {})
    for fname, value in l2.items():
        if not value:
            continue
        result = _make_result(fname, value, document_type, "grid_table",
                              _CONF["grid_table"])
        if fname not in merged or merged[fname].effective_confidence < _CONF["grid_table"]:
            merged[fname] = result

    # L0 — pdfplumber (additional word coordinates; tables already handled in L2)
    # This layer's output feeds L2 — no direct field results to merge here

    # L3 — PaddleOCR for scanned pages (only fills pages not covered by digital OCR)
    # PaddleOCR output feeds through spatial matching re-run (TODO: integrate fully)

    # L5 — UAD template parser (fills Yes/No, grids, GLA, effective_date by known positions)
    l5 = raw.get("l5", {})
    for fname, result in l5.items():
        if hasattr(result, "found") and result.found:
            if fname not in merged or merged[fname].effective_confidence < _CONF["uad_template"]:
                merged[fname] = result

    # ── Ensure every schema field has a result ──────────────────────────────
    result_set = ExtractionResultSet(
        document_path=str(pdf_path),
        document_type=document_type,
        total_pages=0,
        ocr_method="layered_parallel",
    )

    for fd in schema.all_fields():
        fname = fd.canonical_name
        if fname in merged:
            result_set.add(merged[fname])
        else:
            result_set.add(_not_found(fname, document_type))

    # Add extra fields from Camelot/L5 that aren't in the schema template
    # (comp_1_sale_price, comp_2_gla, etc. — schema only has comp_N_ templates)
    schema_names = {fd.canonical_name for fd in schema.all_fields()}
    for fname, result in merged.items():
        if fname not in schema_names and result.found:
            result_set.add(result)

    result_set.finalize()

    elapsed = int((time.time() - start) * 1000)
    found = len(result_set.found_results())
    layers_used = [k for k in ("l0", "l1", "l2", "l3", "l4", "l4b", "l5") if raw.get(k)]

    logger.info(
        "Orchestrator: %s | %d/%d fields | layers=%s | %dms",
        pdf_path.name, found, len(result_set), layers_used, elapsed,
    )
    return result_set
