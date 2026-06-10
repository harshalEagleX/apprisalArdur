"""
Transaction-level QC entry point.

Given a transaction folder (with appraisal/, engagement/, contract/ subfolders)
this: extracts each document with the layered orchestrator, builds a QCContext,
runs the rule engine, and (optionally) persists the QC report.

This is the product entry point the API/dashboard call to QC a whole case.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Optional

from app.qc.config import qc_config
from app.qc.context import QCContext
from app.qc.engine import persist_report, run_qc
from app.qc.result import QCReport

# ensure rules are registered
import app.qc.rules  # noqa: F401

logger = logging.getLogger(__name__)

_DOC_TYPE = {
    "appraisal": "appraisal_report",
    "engagement": "engagement_letter",
    "contract": "sales_contract",
}


def _first_pdf(folder: Path, sub: str) -> Optional[Path]:
    d = folder / sub
    if not d.is_dir():
        return None
    pdfs = sorted(d.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def extract_documents(folder: Path) -> Dict[str, object]:
    """Extract each present document. Returns {role: ExtractionResultSet}."""
    from app.extraction.layers.orchestrator import run_full_extraction
    sets: Dict[str, object] = {}
    for role, dtype in _DOC_TYPE.items():
        pdf = _first_pdf(folder, role)
        if pdf is None:
            continue
        try:
            # use_paddle=False: scanned pages are OCR'd via Tesseract in the spatial
            # layer (fast); PaddleOCR 3.x on CPU is too slow for this path.
            rs = run_full_extraction(pdf, dtype, use_paddle=False, use_llm=False)
            if role == "engagement":
                rs = _overlay_engagement(rs, pdf, dtype)
            elif role == "appraisal":
                rs = _overlay_comp_grid(rs, pdf, dtype)
                rs = _overlay_sca_llm(rs, pdf, dtype)
                rs = _overlay_photos(rs, pdf, dtype)
                rs = _overlay_comp_photos(rs, pdf, dtype)
            elif role == "contract":
                rs = _overlay_contract(rs, pdf, dtype)
            sets[role] = rs
        except Exception as exc:
            logger.error("Extraction failed for %s/%s: %s", folder.name, role, exc)
    return sets


# First-page title markers that identify a 1004D Appraisal Update / Completion
# report — a form with NO sales-comparison grid. A normal 1004 reads "Uniform
# Residential Appraisal Report" and never matches these, so gating on this signal
# never hides a real 1004's comp-extraction failure (engine._SECTION_GATE).
_UPDATE_FORM_MARKERS = (
    "appraisal update",
    "completion report",
    "1004d",
    "summary appraisal update",
)


def _overlay_form_type(rs, pdf, dtype):
    """Mark `is_update_report` when the report's first pages identify it as a 1004D
    Appraisal Update / Completion form (no sales-comparison grid). No-op otherwise,
    so a normal full appraisal keeps the grid-present default (P-6)."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    try:
        import fitz
        doc = fitz.open(str(pdf))
        text = " ".join(doc[i].get_text() for i in range(min(3, doc.page_count))).lower()
        doc.close()
    except Exception as exc:
        logger.warning("Form-type detection failed for %s: %s", pdf.name, exc)
        return rs
    if not any(m in text for m in _UPDATE_FORM_MARKERS):
        return rs
    logger.info("Form-type: %s detected as 1004D update/completion (no SCA grid)", pdf.name)
    existing = {name: r for name, r in rs}
    existing["is_update_report"] = ExtractionResult(
        canonical_name="is_update_report", document_type=dtype, value="true",
        raw_source_text="true", extraction_method="form_marker",
        confidence=0.9, source_page=0, normalization_applied=["form_marker"],
    )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method=rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_comp_grid(rs, pdf, dtype):
    """Overlay per-comparable DESCRIPTIVE grid fields (address, proximity, date,
    condition, quality, real GLA, location, data source) parsed column-wise from
    the sales grid. Currency comp fields (sale_price/net/adjusted) are left to
    Camelot, which reads those right-aligned columns reliably."""
    import re as _re
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.comp_grid_extractor import extract_comp_grid
    from app.extraction.sca_grid_matrix import extract_sca_grid
    try:
        grid = extract_comp_grid(pdf)
    except Exception as exc:
        logger.warning("Comp-grid extraction failed for %s: %s", pdf.name, exc)
        grid = {}
    # Overlay the dedicated Camelot-lattice cell reads (glue-free) where they pass
    # a per-field validator, so garbled cells (e.g. "1 C 1") are rejected and the
    # pdfplumber band value is kept. Camelot fixes the pdfplumber glue (site/date).
    try:
        cam = extract_sca_grid(pdf)
    except Exception as exc:
        logger.debug("SCA lattice extraction failed for %s: %s", pdf.name, exc)
        cam = {}
    cam_acc = cam.pop("_sca_grid_accuracy", None)
    _VALID = {
        "site_size": lambda v: _re.search(r"\d", v) and _re.search(r"(sf|ac)", v.lower()),
        "sale_date": lambda v: bool(_re.search(r"([sc]\d\d/\d\d|active|unk)", v.lower())),
        "condition_rating": lambda v: bool(_re.fullmatch(r"C[1-6]", v.upper())),
        "quality_rating": lambda v: bool(_re.fullmatch(r"Q[1-6]", v.upper())),
        "location_rating": lambda v: ";" in v,
        "view": lambda v: ";" in v,
        "proximity": lambda v: bool(_re.search(r"\d+\.\d+", v)),
        "net_adj_pct": lambda v: bool(_re.fullmatch(r"\d+(?:\.\d+)?", v)),
        "gross_adj_pct": lambda v: bool(_re.fullmatch(r"\d+(?:\.\d+)?", v)),
        "prior_sale_date": lambda v: bool(_re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", v)),
    }
    cam_fields = set()
    for name, value in cam.items():
        v = str(value).strip()
        if not v:
            continue
        suffix = name.split("_", 2)[2] if name.startswith("comp_") and name[5].isdigit() else \
            (name[len("subject_grid_"):] if name.startswith("subject_grid_") else name)
        validator = _VALID.get(suffix)
        if validator is None or validator(v):
            grid[name] = v
            cam_fields.add(name)
    if not grid:
        return rs
    existing = {name: r for name, r in rs}
    for name, value in grid.items():
        if not value or not str(value).strip():
            continue
        from_cam = name in cam_fields
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value),
            extraction_method="sca_lattice" if from_cam else "comp_grid",
            confidence=0.92 if from_cam else 0.88, source_page=0,
            normalization_applied=["sca_lattice" if from_cam else "comp_grid"],
        )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method="comp_grid+layered")
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_sca_llm(rs, pdf, dtype):
    """Repair the SCA currency grid with the LLM "brain" (extraction layer
    v0.1.12) when the deterministic table readers look insufficient or
    implausible. The LLM reads the grid TEXT only (no OCR, no images) and its
    identity-validated currency/GLA values win for the comps they cover; every
    other field is left untouched. No-op when LLM extraction is disabled (P-6)."""
    from app import config
    if not config.LLM_EXTRACTION_ENABLED:
        return rs
    from app.extraction import llm_groq
    if not llm_groq.groq_extraction_available():
        return rs
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.sca_llm_extractor import SCA_LLM_VERSION, extract_sca_grid_llm

    existing = {name: r for name, r in rs}

    def _num(v):
        try:
            return float(str(v).replace(",", "").replace("$", "").strip())
        except Exception:
            return None

    # The SCA currency grid is the known-weak spot for the deterministic readers
    # (cost-approach / opinion-of-value frequently leaks into the adjusted row),
    # so run the LLM brain whenever it is available — it validates
    # adjusted == sale + net and only overwrites the comps it confidently reads,
    # so a correct deterministic value is simply confirmed. adj_vals/suspect are
    # computed for the log (visibility into why a repair was needed).
    adj_vals, suspect = [], False
    for name, r in existing.items():
        if name.startswith("comp_") and name.endswith("_adjusted_sale_price"):
            a = _num(r.value)
            if a is None:
                continue
            adj_vals.append(a)
            comp = name[: -len("_adjusted_sale_price")]
            sp = existing.get(f"{comp}_sale_price")
            s = _num(sp.value) if sp else None
            if s and s > 0 and abs(a - s) / s > 0.25:
                suspect = True

    try:
        llm = extract_sca_grid_llm(pdf)
    except Exception as exc:
        logger.warning("SCA-LLM overlay failed for %s: %s", pdf.name, exc)
        return rs
    if not llm:
        return rs

    replaced = 0
    for name, value in llm.items():
        prev = existing.get(name)
        if prev is not None and str(prev.value) == str(value):
            continue
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value), extraction_method="sca_llm",
            confidence=0.9, source_page=0,
            normalization_applied=[f"sca_llm:{SCA_LLM_VERSION}"],
        )
        replaced += 1
    logger.info(
        "SCA-LLM overlay (v%s, groq:%s): set/replaced %d currency-grid fields for %s "
        "(deterministic adjusted=%d, suspect=%s)",
        SCA_LLM_VERSION, config.GROQ_MODEL, replaced, pdf.name, len(adj_vals), suspect,
    )
    if replaced == 0:
        return rs
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method=rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_sketch(rs, pdf, dtype):
    """Overlay the Building Sketch's Total Living Area (OCR, vision fallback) as
    `sketch_living_area`, so SCA-17 can cross-check the grid/improvements GLA
    against the sketch. No-op when the sketch GLA can't be read (P-6)."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.sketch_extractor import extract_sketch_gla
    try:
        fields = extract_sketch_gla(pdf)
    except Exception as exc:
        logger.warning("Sketch overlay failed for %s: %s", pdf.name, exc)
        return rs
    val = fields.get("sketch_living_area")
    if not val:
        return rs
    try:
        page = int(fields.get("_sketch_page", 0) or 0)
    except (TypeError, ValueError):
        page = 0
    method = fields.get("_sketch_method", "sketch_ocr")
    existing = {name: r for name, r in rs}
    existing["sketch_living_area"] = ExtractionResult(
        canonical_name="sketch_living_area", document_type=dtype, value=str(val),
        raw_source_text=str(val), extraction_method=method,
        confidence=0.85, source_page=page, normalization_applied=[method],
    )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method=rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_photos(rs, pdf, dtype):
    """Add photo-presence pseudo-fields (photo_front/_rear/_street/_left/_right
    and photo_interior_rooms) from caption detection, so the PH rules can read
    them without the rule engine touching the PDF (P-3)."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.photo_detector import detect_photos
    try:
        p = detect_photos(pdf)
    except Exception as exc:
        logger.warning("Photo detection failed for %s: %s", pdf.name, exc)
        return rs
    fields = {
        "photo_front": str(p.has_front), "photo_rear": str(p.has_rear),
        "photo_street": str(p.has_street), "photo_left": str(p.has_left),
        "photo_right": str(p.has_right),
        "photo_interior_rooms": ",".join(sorted(p.interior_rooms)),
    }
    existing = {name: r for name, r in rs}
    for name, value in fields.items():
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=value,
            raw_source_text=value, extraction_method="photo_caption",
            confidence=0.8, source_page=0, normalization_applied=["photo_caption"],
        )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method=rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_comp_photos(rs, pdf, dtype):
    """Add comparable-photo pseudo-fields (page count + Cloud Vision signals when
    configured) so SCA-27 / SCA-16V read them without touching the PDF (P-3)."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.comp_photo_extractor import extract_comp_photo_signals
    try:
        fields = extract_comp_photo_signals(pdf)
    except Exception as exc:
        logger.warning("Comp-photo signals failed for %s: %s", pdf.name, exc)
        return rs
    if not fields:
        return rs
    existing = {name: r for name, r in rs}
    for name, value in fields.items():
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value), extraction_method="comp_photo_vision",
            confidence=0.8, source_page=0, normalization_applied=["comp_photo_vision"],
        )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method=rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_contract(rs, pdf, dtype):
    """Overlay best-effort contract price/date/concessions (Tesseract OCR for
    scanned contracts). Only sets a field when confidently found, so an
    unreadable contract leaves C-2/C-4 at VERIFY rather than a false mismatch."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.contract_extractor import extract_contract_fields
    try:
        fields = extract_contract_fields(pdf)
    except Exception as exc:
        logger.warning("Contract extraction failed for %s: %s", pdf.name, exc)
        return rs
    if not fields:
        return rs
    existing = {name: r for name, r in rs}
    for name, value in fields.items():
        if not value:
            continue
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value), extraction_method="contract_ocr",
            confidence=0.82, source_page=1, normalization_applied=["contract_ocr"],
        )
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method="contract_ocr+layered")
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def _overlay_engagement(rs, pdf, dtype):
    """Overlay the dedicated label-based engagement fields on top of the layered
    output — the order form is free-form, so the label extractor is far more
    accurate for the cross-document fields the QC rules depend on."""
    from app.core.result import ExtractionResult
    from app.extraction.engagement_extractor import extract_engagement_fields
    try:
        fields = extract_engagement_fields(pdf)
    except Exception as exc:
        logger.warning("Engagement label extraction failed for %s: %s", pdf.name, exc)
        return rs
    # Fields the label extractor OWNS for an engagement letter. For any owned
    # field the label extractor did not find, drop the layered value too — the
    # free-form layered read of these is unreliable (it produced merged/garbage
    # values), and a wrong value is worse than NOT_FOUND for a cross-doc rule.
    owned = {
        "property_address", "city", "state", "zip_code", "county",
        "borrower_name", "co_borrower_name", "lender_name", "lender_address",
        "loan_type", "assignment_type", "form_type",
    }
    existing = {name: r for name, r in rs}
    for name in owned:
        if name not in fields:
            existing.pop(name, None)
    for name, value in fields.items():
        if not value:
            continue
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value), extraction_method="engagement_label",
            confidence=0.92, source_page=1, normalization_applied=["engagement_label"],
        )
    from app.core.result import ExtractionResultSet
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages, ocr_method="engagement_label+layered")
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


def run_transaction_qc_paths(appraisal_path, engagement_path=None, contract_path=None,
                             transaction_id: Optional[str] = None, persist: bool = True,
                             progress=None):
    """Run QC from explicit document paths (what the Java backend supplies via
    the multipart /qc/process call) rather than a folder layout. `progress` is an
    optional callable(stage:str, message:str, pct:float) for live updates.

    Returns (QCReport, QCContext) so the caller can build the Java response shape."""
    from app.extraction.layers.orchestrator import run_full_extraction

    def _emit(stage, msg, pct):
        if progress:
            try:
                progress(stage, msg, pct)
            except Exception:
                pass

    transaction_id = transaction_id or str(Path(appraisal_path).stem)
    sets = {}
    _emit("extract_appraisal", "Reading appraisal report (OCR + fields)", 10.0)
    rs = run_full_extraction(Path(appraisal_path), "appraisal_report", use_paddle=False)
    rs = _overlay_form_type(rs, Path(appraisal_path), "appraisal_report")
    _emit("sca_grid", "Reading the sales comparison grid", 28.0)
    rs = _overlay_comp_grid(rs, Path(appraisal_path), "appraisal_report")
    _emit("sca_llm", "Confirming comparable adjustments (LLM)", 36.0)
    rs = _overlay_sca_llm(rs, Path(appraisal_path), "appraisal_report")
    _emit("sketch", "Reading the building sketch GLA", 40.0)
    rs = _overlay_sketch(rs, Path(appraisal_path), "appraisal_report")
    _emit("photos", "Analyzing report photographs", 42.0)
    rs = _overlay_photos(rs, Path(appraisal_path), "appraisal_report")
    rs = _overlay_comp_photos(rs, Path(appraisal_path), "appraisal_report")
    sets["appraisal"] = rs
    if engagement_path:
        _emit("extract_engagement", "Extracting engagement letter", 45.0)
        eng = run_full_extraction(Path(engagement_path), "engagement_letter", use_paddle=False)
        sets["engagement"] = _overlay_engagement(eng, Path(engagement_path), "engagement_letter")
    if contract_path:
        _emit("extract_contract", "Extracting sales contract", 65.0)
        con = run_full_extraction(Path(contract_path), "sales_contract", use_paddle=False)
        sets["contract"] = _overlay_contract(con, Path(contract_path), "sales_contract")

    _emit("rules", "Evaluating QC rules", 85.0)
    ctx = QCContext(
        transaction_id=transaction_id,
        appraisal=sets.get("appraisal"), engagement=sets.get("engagement"),
        contract=sets.get("contract"),
        structured_conf=qc_config.structured_conf, checkbox_conf=qc_config.checkbox_conf,
    )
    report = run_qc(ctx)
    if persist:
        persist_report(report, document_id=Path(appraisal_path).name)
    _emit("done", "QC complete", 100.0)
    return report, ctx


def run_transaction_qc(folder, transaction_id: Optional[str] = None,
                       persist: bool = True, min_phase: Optional[int] = None) -> QCReport:
    """Full QC for one transaction folder."""
    folder = Path(folder)
    transaction_id = transaction_id or str(folder).split("uploads/")[-1]
    start = time.time()

    sets = extract_documents(folder)
    ctx = QCContext(
        transaction_id=transaction_id,
        appraisal=sets.get("appraisal"),
        engagement=sets.get("engagement"),
        contract=sets.get("contract"),
        structured_conf=qc_config.structured_conf,
        checkbox_conf=qc_config.checkbox_conf,
    )
    report = run_qc(ctx, min_phase=min_phase)

    if persist:
        doc_id = (_first_pdf(folder, "appraisal") or folder).name
        persist_report(report, document_id=doc_id)

    logger.info(
        "QC %s | loan=%s txn=%s | %s | %.1fs",
        transaction_id, ctx.loan_type, ctx.transaction_type,
        report.counts(), time.time() - start,
    )
    return report
