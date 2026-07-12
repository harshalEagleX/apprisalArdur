"""
extraction/merge.py — SHALqc.md §3.2 "Extraction order & merge": the orchestrator
that runs every extractor in order and produces one merged ExtractedFieldSet.

| Step | Extractor         | Conf        |
|------|-------------------|-------------|
| 1    | XML (MISMO 2.6)   | 0.97        |
| 2    | PDF digital pages | 0.85-0.92   |
| 3    | PDF scanned pages | 0.80        |
| 4    | Grid extractor    | 0.88-0.90   |
| 5    | Checkboxes        | 0.92        |
| 6    | Engagement letter | 0.92        |
| 7    | LLM gap-fill      | grounded    |
| 8    | Plausibility      | -           |
| 9    | XML overlay       | -           |

Merge rule: for every field, the highest-confidence witness wins; a
materially-disagreeing lower-confidence witness is retained as a `conflict`
on the winner, never discarded (P3). Because XML is parsed first at the
highest fixed confidence (0.97), it naturally wins every tie against every
later step — which is exactly SHALqc.md step 9 ("XML overlay... XML wins
ties"). No separate overlay pass is needed; §9 falls out of the same rule
applied uniformly across all nine steps.

Concurrency rule (SHALqc.md §3.2, "a hard lesson, not a preference"): max 3
workers; PDF-object-parsing extractors (Camelot, pdfplumber deep parse) never
run concurrently with OCR on the same document. XML/engagement/checkbox/
pdf_digital are independent/lightweight and run in a small thread pool; grid
(pdfplumber+Camelot) and pdf_scanned (Tesseract OCR) run sequentially after
that pool drains — never against each other.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from app.extraction import checkbox, engagement, grid_extractor, pdf_digital, pdf_scanned, plausibility, xml_extractor
from app.extraction.llm_gapfill import GapfillClient, gapfill
from app.extraction.result import ExtractedField, ExtractedFieldSet
from app.extraction.schema import schema_loader as _default_schema_loader

__version__ = "mrg-1.0.0"

logger = logging.getLogger(__name__)

_MAX_WORKERS = 3


def _light_normalize(value: str) -> str:
    """Ad hoc equality check for merge-time conflict detection only — NOT a
    substitute for normalize/normalizer.py (Part 4, SHALqc.md §4). Rules must
    never do their own string cleanup (P6); this exists solely so merge.py can
    decide "same value, don't bother with a conflict record" vs "genuinely
    disagreeing witnesses" before the real normalizer exists."""
    v = value.strip().lower()
    v = re.sub(r"[\$,]", "", v)
    v = re.sub(r"\s+", " ", v)
    return v


def _merge_field(merged: Dict[str, ExtractedField], candidate: ExtractedField) -> None:
    """Highest-confidence witness wins; a materially different loser is kept
    as a conflict on the winner (P3) rather than discarded."""
    existing = merged.get(candidate.canonical_name)
    if existing is None:
        merged[candidate.canonical_name] = candidate
        return

    same_value = _light_normalize(str(existing.value or "")) == _light_normalize(str(candidate.value or ""))
    if same_value:
        return  # sources agree — nothing to record

    if candidate.confidence > existing.confidence:
        candidate.add_conflict(
            source=existing.source, value=str(existing.value), confidence=existing.confidence,
            page=existing.page, bbox=existing.bbox,
        )
        merged[candidate.canonical_name] = candidate
    else:
        existing.add_conflict(
            source=candidate.source, value=str(candidate.value), confidence=candidate.confidence,
            page=candidate.page, bbox=candidate.bbox,
        )


def _merge_set(merged: Dict[str, ExtractedField], fs: ExtractedFieldSet) -> None:
    for _name, ef in fs:
        if ef.found:
            _merge_field(merged, ef)


def run_extraction(
    appraisal_pdf,
    xml_path: Optional[str] = None,
    engagement_letter: Optional[str] = None,
    schema=None,
    llm_client: Optional[GapfillClient] = None,
) -> ExtractedFieldSet:
    """Run every extractor per SHALqc.md §3.2 and return one merged
    ExtractedFieldSet. Never raises — a failing extractor is caught and
    logged so the run completes with whatever the other extractors found
    (SHALqc.md §16 partial-failure contract, honored here even though
    report.degradations[] itself is a Part-8/report-builder concern)."""
    schema = schema or _default_schema_loader
    merged: Dict[str, ExtractedField] = {}

    def _safe(label: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            logger.warning("merge: extractor %s failed: %s", label, exc)
            return ExtractedFieldSet()

    # Step 0: AcroForm (SHALqc-CORE §10) — embedded PDF widgets, if any. conf
    # 0.95, bbox = widget rect → location_quality exact for free. Runs before the
    # template/PDF pass; a flat PDF yields an empty set (near-zero cost).
    from app.extraction.acroform import extract_acroform
    _merge_set(merged, _safe("acroform", extract_acroform, appraisal_pdf))

    # Step 1: XML — the spine, parsed first, highest fixed confidence (0.97).
    xml_fs = _safe("xml", xml_extractor.extract_xml, xml_path) if xml_path else ExtractedFieldSet()
    _merge_set(merged, xml_fs)

    # Steps 2, 5, 6 (+ checkbox from step 5) — independent/lightweight, share
    # a small pool. Step 3/4 (OCR, grid) are intentionally excluded from this
    # pool — see the concurrency rule in the module docstring.
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        f_digital = ex.submit(_safe, "pdf_digital", pdf_digital.extract_pdf_digital, appraisal_pdf, schema)
        f_checkbox = ex.submit(_safe, "checkbox", checkbox.extract_checkboxes, appraisal_pdf)
        f_engagement = (
            ex.submit(_safe, "engagement", engagement.extract_engagement, engagement_letter)
            if engagement_letter else None
        )
        _merge_set(merged, f_digital.result())
        _merge_set(merged, f_checkbox.result())
        if f_engagement is not None:
            _merge_set(merged, f_engagement.result())

    # Steps 3 & 4 — pdfplumber deep-parse / Camelot / Tesseract OCR. Run
    # sequentially, never against each other (the "hard lesson" rule).
    grid_fs = _safe("grid", grid_extractor.extract_grid, appraisal_pdf, schema)
    _merge_set(merged, grid_fs)
    scanned_fs = _safe("pdf_scanned", pdf_scanned.extract_pdf_scanned, appraisal_pdf, schema)
    _merge_set(merged, scanned_fs)

    # Step 7: LLM gap-fill — only fields still blank after 1-6, batched per
    # section (SHALqc.md §3.2). No client wired ⇒ fields simply stay MISSING
    # (llm_gapfill.gapfill's documented graceful-degradation behavior).
    missing_by_section: Dict[str, list] = {}
    for fd in schema.all_fields():
        if fd.canonical_name in merged:
            continue
        for section in fd.sections or ["_unsectioned"]:
            missing_by_section.setdefault(section, []).append(fd.canonical_name)
    gapfill_fs = gapfill(missing_by_section, page_text_by_section={}, client=llm_client)
    _merge_set(merged, gapfill_fs)

    # Step 8: plausibility — suppress categorically-impossible winners in place.
    suppressed = plausibility.validate_fields(merged)
    if suppressed:
        logger.info("merge: plausibility suppressed %d field(s)", suppressed)

    # Step 9: XML overlay — already enforced by _merge_field's confidence-
    # priority rule (XML entered the bag first at 0.97 and wins every tie).

    result = ExtractedFieldSet()
    for ef in merged.values():
        result.add(ef)

    # SHALqc-CORE §3 Back-Locator: recover page/bbox for XML-sourced values so
    # every finding is click-to-scroll. Best-effort — a failure never sinks the
    # run (P6).
    try:
        from app.locate.back_locator import locate_fields
        hist = locate_fields(result, appraisal_pdf)
        logger.info("merge: back-locator %s", hist)
    except Exception as exc:
        logger.warning("merge: back-locator failed: %s", exc)

    logger.info("merge: %d fields merged (%d suppressed)", len(result), suppressed)
    return result
