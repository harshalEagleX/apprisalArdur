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
from time import perf_counter
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



def _rebuild(rs, dtype, existing, ocr_method=None):
    """Re-assemble an ExtractionResultSet after an overlay merged new results
    into `existing` — the tail every _overlay_* was duplicating (DRY)."""
    from app.core.result import ExtractionResultSet
    merged = ExtractionResultSet(document_path=rs.document_path, document_type=dtype,
                                 total_pages=rs.total_pages,
                                 ocr_method=ocr_method or rs.ocr_method)
    for r in existing.values():
        merged.add(r)
    merged.finalize()
    return merged


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
                rs = _overlay_subject_llm(rs, pdf, dtype)
                rs = _overlay_photos(rs, pdf, dtype)
                rs = _overlay_comp_photos(rs, pdf, dtype)
            elif role == "contract":
                rs = _overlay_contract(rs, pdf, dtype)
            rs = _overlay_locate(rs, pdf)
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
    return _rebuild(rs, dtype, existing)


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
        grid, grid_pos = extract_comp_grid(pdf)
    except Exception as exc:
        logger.warning("Comp-grid extraction failed for %s: %s", pdf.name, exc)
        grid, grid_pos = {}, {}
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
    # The grid page every comparable field lives on — so even a lattice (Camelot)
    # cell or a value the locator can't disambiguate still scrolls to the right
    # page. Taken from the positions the pdfplumber pass recorded.
    grid_page = next((p["page"] for p in grid_pos.values() if p.get("page")), 0)
    existing = {name: r for name, r in rs}
    for name, value in grid.items():
        if not value or not str(value).strip():
            continue
        from_cam = name in cam_fields
        pos = grid_pos.get(name)
        # Prefer the pdfplumber cell box/page; fall back to the grid page so a
        # lattice-only field is at least page-located (never source_page=0 here).
        page = (pos or {}).get("page") or grid_page
        bbox = (pos or {}).get("bbox")
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value),
            extraction_method="sca_lattice" if from_cam else "comp_grid",
            confidence=0.92 if from_cam else 0.88, source_page=page,
            bbox=bbox,
            normalization_applied=["sca_lattice" if from_cam else "comp_grid"],
        )
    return _rebuild(rs, dtype, existing, ocr_method="comp_grid+layered")


def _sca_num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def _sca_values_agree(a, b) -> bool:
    """True if two readers' values match within $1 or 0.5% (numbers), else exact text."""
    na, nb = _sca_num(a), _sca_num(b)
    if na is None or nb is None:
        return str(a).strip() == str(b).strip()
    return abs(na - nb) <= max(1.0, 0.005 * max(abs(na), abs(nb)))


def _sca_double_verify(existing, llm, dtype) -> int:
    """PROTOTYPE (config.SCA_DOUBLE_VERIFY, UNVERIFIED — default OFF).

    Compare the deterministic (Camelot/comp_grid) value against the LLM value per
    currency cell instead of letting the LLM silently overwrite:
      • agree    → keep value, confidence 0.95 (both readers concur)
      • disagree → keep the DETERMINISTIC value but confidence 0.40 and record BOTH
                   values, so the SCA review rule flags VERIFY rather than trusting
                   one reader blind (closes the "LLM silently wins" gap)
      • LLM-only → use it at 0.90 (unchanged from the repair path)

    NEXT REFINEMENT (after measurement): on disagreement, use the adjusted = sale +
    net invariant to pick the self-consistent source before falling back to VERIFY.
    Returns the number of cells touched (so the caller rebuilds the result set).
    """
    from app.core.result import ExtractionResult
    from app.extraction.sca_llm_extractor import SCA_LLM_VERSION
    touched = 0
    for name, value in llm.items():
        prev = existing.get(name)
        if prev is None:
            existing[name] = ExtractionResult(
                canonical_name=name, document_type=dtype, value=str(value),
                raw_source_text=str(value), extraction_method="sca_llm",
                confidence=0.9, source_page=0, bbox=None,
                normalization_applied=[f"sca_llm:{SCA_LLM_VERSION}"])
            touched += 1
        elif _sca_values_agree(prev.value, value):
            existing[name] = ExtractionResult(
                canonical_name=name, document_type=dtype, value=str(prev.value),
                raw_source_text=f"camelot={prev.value}|llm={value}",
                extraction_method="sca_camelot+llm_agree", confidence=0.95,
                source_page=prev.source_page, bbox=prev.bbox,
                normalization_applied=[f"sca_doubleverify:{SCA_LLM_VERSION}"])
            touched += 1
        else:
            existing[name] = ExtractionResult(
                canonical_name=name, document_type=dtype, value=str(prev.value),
                raw_source_text=f"CONFLICT camelot={prev.value}|llm={value}",
                extraction_method="sca_conflict", confidence=0.40,
                source_page=prev.source_page, bbox=prev.bbox,
                normalization_applied=[f"sca_doubleverify_conflict:{SCA_LLM_VERSION}"])
            touched += 1
    return touched


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
    if config.SCA_DOUBLE_VERIFY:
        # PROTOTYPE path (default OFF): compare-and-flag instead of blind overwrite.
        replaced = _sca_double_verify(existing, llm, dtype)
    else:
        for name, value in llm.items():
            prev = existing.get(name)
            if prev is not None and str(prev.value) == str(value):
                continue
            # The LLM refines the value but reads no geometry — inherit the grid
            # page/box a deterministic pass (comp_grid / lattice) already recorded so
            # the SCA review rule can still scroll to the cell (never drop to page 0).
            existing[name] = ExtractionResult(
                canonical_name=name, document_type=dtype, value=str(value),
                raw_source_text=str(value), extraction_method="sca_llm",
                confidence=0.9,
                source_page=prev.source_page if prev else 0,
                bbox=prev.bbox if prev else None,
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
    return _rebuild(rs, dtype, existing)


def _overlay_subject_llm(rs, pdf, dtype):
    """Gap-fill page-1 subject/contract-section fields with the LLM "brain"
    (extraction layer v0.1.17). Strictly additive: only fields the deterministic
    layers did NOT find are requested, every answer is verbatim-validated against
    the page text, and enum/checkbox answers come back below the structured
    confidence cutoff so rules treat them as VERIFY-grade. No-op when LLM
    extraction is disabled or nothing is missing (P-6)."""
    from app import config
    if not config.LLM_EXTRACTION_ENABLED:
        return rs
    from app.extraction import llm_groq
    if not llm_groq.groq_extraction_available():
        return rs
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.form_llm_extractor import (
        GAP_FIELDS, ALWAYS_REFILL, SUBJECT_LLM_VERSION, extract_gap_fields_llm)

    existing = {name: r for name, r in rs}

    # "See attached addenda" cross-reference detection: when the deterministic
    # layer captured a deferred cross-reference string instead of the actual field
    # value, treat the field as missing so the LLM re-extracts from the full doc.
    # This fixes the Sebring false-positives where N-6/R-1b/S-4a each read the
    # literal "See attached addenda." text instead of following the pointer.
    import re as _re
    _SEE_ADDENDA = _re.compile(
        r"^\s*see\s+(attached\s+)?(addend|supplement|exhibit|attach)", _re.I)

    def _is_see_addenda(r) -> bool:
        return r is not None and r.found and _SEE_ADDENDA.match(str(r.value or ""))

    # A field is re-extracted when:
    #   • it is missing/blank, OR
    #   • it is an ALWAYS_REFILL narrative (deterministic reads label text, not fill-in), OR
    #   • its current value is a "See attached addenda" cross-reference (deferred pointer)
    missing = [f for f in GAP_FIELDS
               if f not in existing or not existing[f].found
               or not str(existing[f].value or "").strip()
               or f in ALWAYS_REFILL
               or _is_see_addenda(existing.get(f))]
    if not missing:
        return rs
    try:
        filled = extract_gap_fields_llm(pdf, missing)
    except Exception as exc:
        logger.warning("Gap-fill LLM overlay failed for %s: %s", pdf.name, exc)
        return rs
    if not filled:
        return rs
    for name, (value, conf) in filled.items():
        # For always-refill narratives the deterministic value may be a real (but
        # garbled) read; keep whichever text is longer/more complete so we never
        # replace a good full narrative with a shorter LLM snippet.
        prev = existing.get(name)
        if (name in ALWAYS_REFILL and prev is not None and prev.found
                and len(str(prev.value or "")) >= len(str(value))):
            continue
        existing[name] = ExtractionResult(
            canonical_name=name, document_type=dtype, value=str(value),
            raw_source_text=str(value), extraction_method="subject_llm",
            confidence=conf, source_page=1,
            normalization_applied=[f"subject_llm:{SUBJECT_LLM_VERSION}"],
        )

    # Extraction sometimes reads the one-unit Low/High range cells in the wrong
    # order; High < Low is never a valid entry, so swap the two values. This is an
    # extraction correction (not a rule change) — N-3 still judges whether the
    # predominant sits within the range and whether comps fall inside it.
    import re as _re
    from dataclasses import replace as _replace

    def _num(v):
        m = _re.sub(r"[^\d.]", "", str(v or ""))
        try:
            return float(m) if m else None
        except ValueError:
            return None

    for lo_f, hi_f in (("price_low", "price_high"), ("age_low", "age_high")):
        lo, hi = existing.get(lo_f), existing.get(hi_f)
        if not (lo and hi and lo.found and hi.found):
            continue
        ln, hn = _num(lo.value), _num(hi.value)
        if ln is not None and hn is not None and ln > hn:
            existing[lo_f] = _replace(
                lo, value=hi.value, raw_source_text=hi.raw_source_text,
                normalization_applied=list(lo.normalization_applied) + ["range_order_fix"])
            existing[hi_f] = _replace(
                hi, value=lo.value, raw_source_text=lo.raw_source_text,
                normalization_applied=list(hi.normalization_applied) + ["range_order_fix"])
            logger.info("Range order fix: swapped %s/%s (was %s > %s) for %s",
                        lo_f, hi_f, lo.value, hi.value, pdf.name)
    return _rebuild(rs, dtype, existing)


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
    return _rebuild(rs, dtype, existing)


def _overlay_narrative(rs, pdf, dtype):
    """Overlay the appraiser's sales-comparison narrative as `sales_comparison_summary`,
    read positionally from the sales-comparison page's prose blocks (the form text
    layer otherwise yields only a one-line header stub). Powers the SCA-14
    quality-commentary safeguard. No-op when no prose is found (P-6)."""
    from app.core.result import ExtractionResult, ExtractionResultSet
    from app.extraction.narrative_extractor import extract_sca_narrative
    try:
        fields = extract_sca_narrative(pdf)
    except Exception as exc:
        logger.warning("Narrative overlay failed for %s: %s", pdf.name, exc)
        return rs
    text = fields.get("sales_comparison_summary")
    if not text:
        return rs
    try:
        page = int(fields.get("_narrative_page", 0) or 0)
    except (TypeError, ValueError):
        page = 0
    existing = {name: r for name, r in rs}
    existing["sales_comparison_summary"] = ExtractionResult(
        canonical_name="sales_comparison_summary", document_type=dtype, value=text,
        raw_source_text=text, extraction_method="positional_narrative",
        confidence=0.85, source_page=page, normalization_applied=["positional_narrative"],
    )
    return _rebuild(rs, dtype, existing)


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
    return _rebuild(rs, dtype, existing)


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
    return _rebuild(rs, dtype, existing)


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
    return _rebuild(rs, dtype, existing, ocr_method="contract_ocr+layered")


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
    return _rebuild(rs, dtype, existing, ocr_method="engagement_label+layered")


def _overlay_locate(rs, pdf):
    """Stamp each found value with its on-page bounding box (normalized [0,1],
    top-left origin) so the reviewer UI can scroll to and highlight the exact
    field. Mutates `rs` in place and returns it. No-op / safe when the locator is
    disabled or the value can't be located (P-6)."""
    from app.extraction.field_locator import locate_fields
    try:
        locate_fields(Path(pdf), rs)
    except Exception as exc:
        logger.warning("Field locator overlay failed for %s: %s", Path(pdf).name, exc)
    return rs


def _overlay_xml(rs, xml_path, dtype):
    """Overlay MISMO 2.6 GSE XML fields on top of the PDF extraction result.

    XML is the primary structured source — every field it produces carries
    confidence 0.97 (vs the PDF extractors' 0.82–0.92), so in DocView the XML
    value wins whenever both sources disagree.  Fields the XML does not cover
    (e.g. narrative text from addendum body) are left untouched.
    No-op when xml_path is None or XML parsing fails (P-6)."""
    if xml_path is None:
        return rs
    try:
        from app.extraction.xml_extractor import extract_xml
        xml_rs = extract_xml(xml_path)
    except Exception as exc:
        logger.warning("XML overlay failed for %s: %s", Path(xml_path).name, exc)
        return rs
    if not xml_rs.found_results():
        return rs
    existing = {name: r for name, r in rs}
    # Merge: XML result wins on confidence, PDF result kept when XML has no value
    from dataclasses import replace as _replace
    for name, xml_r in xml_rs:
        prev = existing.get(name)
        if prev is None or xml_r.effective_confidence > prev.effective_confidence:
            existing[name] = _replace(xml_r, document_type=dtype)
    return _rebuild(rs, dtype, existing, ocr_method="xml_parser+layered")


def _infer_txn_type(sets: dict) -> str:
    """Infer transaction type from ExtractionResultSet objects in `sets`."""
    for role in ("appraisal", "engagement"):
        rs = sets.get(role)
        if rs is None:
            continue
        # ExtractionResultSet supports .get(canonical)
        try:
            r = rs.get("assignment_type")
            t = (r.value if r and r.found else "").lower()
        except Exception:
            continue
        if "purchase" in t:
            return "purchase"
        if "refinance" in t or "refi" in t:
            return "refinance"
    return "unknown"


def _infer_txn_type_from_fields(eng_fields: dict) -> str:
    """Infer transaction type from the raw engagement field dict (pre-ResultSet)."""
    t = (eng_fields.get("assignment_type") or "").lower()
    if "purchase" in t:
        return "purchase"
    if "refinance" in t or "refi" in t:
        return "refinance"
    return "unknown"


def run_transaction_qc_paths(appraisal_path, engagement_path=None, contract_path=None,
                             xml_path=None,
                             transaction_id: Optional[str] = None, persist: bool = True,
                             progress=None, engagement_status: Optional[str] = None):
    """Run QC from explicit document paths (what the Java backend supplies via
    the multipart /qc/process call) rather than a folder layout. `progress` is an
    optional callable(stage:str, message:str, pct:float) for live updates.

    Returns (QCReport, QCContext) so the caller can build the Java response shape."""
    from app.extraction.layers.orchestrator import run_full_extraction

    # Stage timer: each _emit closes the previously-open stage (recording its
    # real perf_counter duration) and opens the new one. _finish_stage() closes
    # the last. These are genuine wall-clock measurements of the pipeline phases.
    # _emit also sets the LLM-telemetry span to the stage name so any Groq call
    # an overlay stage makes is attributed to that stage.
    from app.extraction import llm_telemetry
    llm_calls = llm_telemetry.start_capture()
    stage_ms: Dict[str, float] = {}
    _open = {"stage": None, "t": 0.0}

    def _emit(stage, msg, pct):
        now = perf_counter()
        if _open["stage"] is not None:
            stage_ms[_open["stage"]] = stage_ms.get(_open["stage"], 0.0) + (now - _open["t"]) * 1000.0
        _open["stage"], _open["t"] = stage, now
        llm_telemetry.set_span(stage)
        if progress:
            try:
                progress(stage, msg, pct)
            except Exception:
                pass

    def _finish_stage():
        if _open["stage"] is not None:
            stage_ms[_open["stage"]] = stage_ms.get(_open["stage"], 0.0) + \
                (perf_counter() - _open["t"]) * 1000.0
            _open["stage"] = None

    transaction_id = transaction_id or str(Path(appraisal_path).stem)
    sets = {}

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1 — Document classification (implicit: each file's type is known
    #           from the caller — appraisal/engagement/contract paths are
    #           typed at the API boundary). Document classifier runs inside
    #           pipeline_runner.py for standalone use; here paths are typed.
    # ═══════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2 — Engagement letter: Job 1 (order field extraction) +
    #           Job 2 (policy overlay extraction).
    #
    # The engagement letter IS the order in this system — extracted FIRST so
    # OrderMetadata and PolicyProfile are ready before any other extractor.
    # ═══════════════════════════════════════════════════════════════════════
    eng_status = engagement_status
    eng_raw_text = ""
    eng_raw_fields: dict = {}
    eng_overlay = None

    if engagement_path:
        _emit("extract_engagement", "Reading the engagement letter", 8.0)
        try:
            from app.extraction.engagement_extractor import (
                extract_engagement_fields, extract_engagement,
            )
            eng_raw_fields = extract_engagement_fields(Path(engagement_path))
            eng = extract_engagement(Path(engagement_path), "engagement_letter")
            eng = _overlay_locate(eng, Path(engagement_path))
            sets["engagement"] = eng
            # Full text for overlay + hash
            try:
                import fitz as _fitz
                _doc = _fitz.open(str(engagement_path))
                eng_raw_text = "\n".join(
                    _doc[i].get_text("text") for i in range(len(_doc))
                )
                _doc.close()
            except Exception:
                pass
        except Exception as exc:
            logger.error("Engagement extraction failed: %s", exc)

        # Job 2 — policy overlay (deterministic regex over full letter text)
        try:
            from app.qc.engagement_overlay import EngagementOverlay
            eng_overlay = EngagementOverlay.from_text(eng_raw_text) if eng_raw_text \
                else EngagementOverlay.from_pdf(engagement_path)
        except Exception as exc:
            logger.warning("EngagementOverlay extraction failed: %s", exc)
            from app.qc.engagement_overlay import EngagementOverlay
            eng_overlay = EngagementOverlay.empty()

        if eng_status is None and sets.get("engagement") is None:
            eng_status = "EXTRACTION_FAILED"

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3 — Artifact inventory (what arrived vs what was expected).
    # Runs before any extraction so missing-document warnings are logged
    # before rules run. Rules can also read ctx.artifact_inventory.
    # ═══════════════════════════════════════════════════════════════════════
    from app.qc.artifact_inventory import ArtifactInventory
    inventory = ArtifactInventory.build(
        has_appraisal_pdf=bool(appraisal_path),
        has_appraisal_xml=bool(xml_path),
        has_engagement=bool(engagement_path) and sets.get("engagement") is not None,
        has_contract=bool(contract_path),
        transaction_type=_infer_txn_type_from_fields(eng_raw_fields),
        engagement_status=eng_status,
    )
    for warn in inventory.warnings:
        logger.warning("Artifact inventory: %s", warn)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 4 — OrderMetadata (built from engagement letter + XML pre-read).
    # At this point XML may not yet be extracted — build with what we have.
    # XML fallback fields are merged in Step 5 below.
    # ═══════════════════════════════════════════════════════════════════════
    from app.qc.order_metadata import OrderMetadata
    order = OrderMetadata.from_extraction(
        engagement_fields=eng_raw_fields,
        xml_result_set=None,            # XML not yet extracted; updated in Step 5
        engagement_raw_text=eng_raw_text,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 5 — Appraisal PDF + XML extraction.
    # After XML is extracted, update OrderMetadata with fallback fields.
    # ═══════════════════════════════════════════════════════════════════════
    _emit("extract_appraisal", "Reading the appraisal report", 10.0)
    rs = run_full_extraction(Path(appraisal_path), "appraisal_report", use_paddle=False)
    rs = _overlay_form_type(rs, Path(appraisal_path), "appraisal_report")

    xml_rs = None
    if xml_path:
        _emit("xml_overlay", "Fusing appraisal XML structured data", 22.0)
        try:
            from app.extraction.xml_extractor import extract_xml
            xml_rs = extract_xml(xml_path)
        except Exception as exc:
            logger.warning("XML extraction failed for OrderMetadata: %s", exc)
        rs = _overlay_xml(rs, Path(xml_path), "appraisal_report")

    # Now update OrderMetadata with XML fallbacks
    if xml_rs is not None:
        order = OrderMetadata.from_extraction(
            engagement_fields=eng_raw_fields,
            xml_result_set=xml_rs,
            engagement_raw_text=eng_raw_text,
        )

    _emit("sca_grid", "Reading the comparable sales grid", 28.0)
    rs = _overlay_comp_grid(rs, Path(appraisal_path), "appraisal_report")
    _emit("sca_llm", "Analyzing comparable sales", 36.0)
    rs = _overlay_sca_llm(rs, Path(appraisal_path), "appraisal_report")
    _emit("subject_llm", "Completing subject & contract details", 38.0)
    rs = _overlay_subject_llm(rs, Path(appraisal_path), "appraisal_report")
    _emit("sketch", "Measuring floor plan & living area", 40.0)
    rs = _overlay_sketch(rs, Path(appraisal_path), "appraisal_report")
    rs = _overlay_narrative(rs, Path(appraisal_path), "appraisal_report")
    _emit("photos", "Reviewing property photographs", 42.0)
    rs = _overlay_photos(rs, Path(appraisal_path), "appraisal_report")
    rs = _overlay_comp_photos(rs, Path(appraisal_path), "appraisal_report")
    _emit("locate", "Preparing review highlights", 44.0)
    rs = _overlay_locate(rs, Path(appraisal_path))
    sets["appraisal"] = rs

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 6 — PolicyProfile: AMC defaults → engagement overlay merged.
    # No real AMC DB profiles yet — from_amc_id returns defaults for all.
    # ═══════════════════════════════════════════════════════════════════════
    from app.qc.policy_profile import PolicyProfile
    policy = PolicyProfile.build(
        amc_id=order.amc_id,
        loan_type=order.loan_type,          # loads FHA/USDA/VA sub-profile from amc_policies.yaml
        overlay=eng_overlay,
        engagement_hash=order.engagement_hash,
    )
    logger.info(
        "PolicyProfile built: amc=%s loan=%s stop_unsigned=%s "
        "age_trigger=%s adj_gross_trigger=%s stop_c5c6=%s",
        order.amc_id, order.loan_type,
        policy.stop_on_unsigned_contract,
        policy.comp_age_commentary_trigger_months,
        policy.adjustment_commentary_gross_pct,
        policy.stop_on_c5_c6,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 7 — Contract: NOT extracted (policy).
    # Contract documents are NEVER OCR'd / read / extracted. We only record that
    # one was provided so the reviewer can open it; every contract cross-document
    # rule is flagged for manual verification against the contract. This avoids
    # the slow, error-prone scanned-contract OCR entirely.
    # ═══════════════════════════════════════════════════════════════════════
    contract_pkg = None
    contract_provided = bool(contract_path)
    if contract_provided:
        _emit("contract_skip", "Contract provided — flagged for manual review", 70.0)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 8 — Rule engine.
    # ═══════════════════════════════════════════════════════════════════════
    _emit("rules", "Running quality checks", 85.0)

    ctx = QCContext(
        transaction_id=transaction_id,
        appraisal=sets.get("appraisal"),
        engagement=sets.get("engagement"),
        contract=None,                       # contract is never extracted (policy)
        contract_provided=contract_provided,
        structured_conf=qc_config.structured_conf,
        checkbox_conf=qc_config.checkbox_conf,
        engagement_status=eng_status,
        policy=policy,
        artifact_inventory=inventory,
        contract_package=contract_pkg,
        order_metadata=order,
    )
    report = run_qc(ctx)
    _finish_stage()
    report.stage_ms = stage_ms
    report.llm_calls = list(llm_calls)
    llm_telemetry.stop_capture()
    if persist:
        persist_report(report, document_id=Path(appraisal_path).name)
    _emit("done", "Quality review complete", 100.0)
    return report, ctx


def run_transaction_qc(folder, transaction_id: Optional[str] = None,
                       persist: bool = True, min_phase: Optional[int] = None) -> QCReport:
    """Full QC for one transaction folder."""
    folder = Path(folder)
    transaction_id = transaction_id or str(folder).split("uploads/")[-1]
    start = time.time()

    from app.extraction import llm_telemetry
    llm_calls = llm_telemetry.start_capture()
    _t = perf_counter()
    llm_telemetry.set_span("extraction")
    sets = extract_documents(folder)
    stage_ms = {"extraction": (perf_counter() - _t) * 1000.0}

    # ---- Artifact inventory (folder-based path) -----------------------------
    from app.qc.artifact_inventory import ArtifactInventory
    _appraisal_pdf = _first_pdf(folder, "appraisal")
    inventory = ArtifactInventory.build(
        has_appraisal_pdf=_appraisal_pdf is not None,
        has_appraisal_xml=False,    # folder-based path doesn't carry XML
        has_engagement=sets.get("engagement") is not None,
        has_contract=sets.get("contract") is not None,
        transaction_type=_infer_txn_type(sets),
    )
    for warn in inventory.warnings:
        logger.warning("Artifact inventory: %s", warn)

    # ---- Policy profile (folder-based path) ---------------------------------
    from app.qc.policy_profile import PolicyProfile
    amc_id = None
    try:
        eng_set = sets.get("engagement")
        if eng_set is not None:
            amc_id = eng_set.get("amc_id") if hasattr(eng_set, "get") else None
    except Exception:
        pass
    policy = PolicyProfile.from_amc_id(amc_id)

    ctx = QCContext(
        transaction_id=transaction_id,
        appraisal=sets.get("appraisal"),
        engagement=sets.get("engagement"),
        contract=sets.get("contract"),
        structured_conf=qc_config.structured_conf,
        checkbox_conf=qc_config.checkbox_conf,
        policy=policy,
        artifact_inventory=inventory,
    )
    _t = perf_counter()
    llm_telemetry.set_span("rules")
    report = run_qc(ctx, min_phase=min_phase)
    stage_ms["rules"] = (perf_counter() - _t) * 1000.0
    report.stage_ms = stage_ms
    report.llm_calls = list(llm_calls)
    llm_telemetry.stop_capture()

    if persist:
        doc_id = (_first_pdf(folder, "appraisal") or folder).name
        persist_report(report, document_id=doc_id)

    logger.info(
        "QC %s | loan=%s txn=%s | %s | %.1fs",
        transaction_id, ctx.loan_type, ctx.transaction_type,
        report.counts(), time.time() - start,
    )
    return report
