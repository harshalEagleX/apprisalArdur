"""
extractor.pdf_scanned (ocr-1.0.0) — 300dpi grayscale render → Tesseract OCR.

SHALqc.md §3.2 step 3: pages with <30 words (extraction/pdf_digital.py's
threshold) are treated as scanned. Render at 300dpi grayscale, run
`tesseract --psm 6 --oem 3`, confidence floor 30 (below that a word is
dropped, not just down-weighted). Fixed field confidence is 0.80.

Word boxes from Tesseract are fed into the same SpatialWordMap label-proximity
matcher used for digital pages (extraction/pdf_digital.py), so scanned and
digital pages share one extraction strategy — only the word source differs.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.extraction.pdf_digital import (
    SpatialWord,
    SpatialWordMap,
    _norm_box,
    build_known_label_set,
    extract_field_spatially,
    is_digital_page,
)
from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.extraction.schema import schema_loader as _default_schema_loader

__version__ = "ocr-1.0.0"

logger = logging.getLogger(__name__)

_TESSERACT_DPI = 300
_TESSERACT_CONFIG = "--psm 6 --oem 3"
_TESSERACT_CONF_FLOOR = 30
_FIELD_CONF = 0.80

_SKIP_PREFIXES = ("comp_", "subject_grid_")
_SKIP_SUFFIXES = ("_adjustment", "_blank")


def _render_grayscale(page, dpi: int = _TESSERACT_DPI):
    """Render a fitz page to a grayscale PIL image at the given DPI."""
    import fitz

    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    return pix, scale


def _pixmap_to_pil(pix):
    from PIL import Image

    mode = "L" if pix.n == 1 else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def _run_tesseract_words(pil_image, page_number: int, scale: float) -> list[SpatialWord]:
    """OCR the image and return SpatialWord boxes rescaled back to PDF points
    (72dpi) so scanned pages share the same coordinate space as digital pages."""
    import pytesseract

    # pytesseract's in-memory temp-file roundtrip is unreliable in some
    # environments; write the image and pass a path — the reliable code path.
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pil_image.save(tmp)
        data = pytesseract.image_to_data(tmp, output_type=pytesseract.Output.DICT, config=_TESSERACT_CONFIG)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    words: list[SpatialWord] = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        if not text or int(data["conf"][i]) < _TESSERACT_CONF_FLOOR:
            continue
        x, y = float(data["left"][i]), float(data["top"][i])
        w, h = float(data["width"][i]), float(data["height"][i])
        # Rescale pixel coords back to PDF points (the render was at `scale`x).
        words.append(SpatialWord(
            x0=x / scale, y0=y / scale, x1=(x + w) / scale, y1=(y + h) / scale,
            text=text, page_number=page_number,
        ))
    return words


def extract_pdf_scanned(pdf_path, schema=None, max_pages: Optional[int] = None) -> ExtractedFieldSet:
    """Label-proximity extraction over scanned (<30-word) pages via Tesseract.

    `max_pages` is config-driven (EXTRACT_MAX_PAGES) for the same reason as
    pdf_digital's — a hardcoded 8 made every page past 8 of a 40-page UAD 3.6
    report invisible. `None` = read the settings default.
    """
    import fitz

    if max_pages is None:
        from app.config import settings
        max_pages = settings.extract_max_pages
    schema = schema or _default_schema_loader
    fs = ExtractedFieldSet()
    known_labels = build_known_label_set(schema)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("pdf_scanned: cannot open %s: %s", pdf_path, exc)
        return fs

    try:
        candidate_fields = [
            fd for fd in schema.all_fields()
            if not fd.canonical_name.startswith(_SKIP_PREFIXES)
            and not fd.canonical_name.endswith(_SKIP_SUFFIXES)
        ]
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            if is_digital_page(page):
                continue  # digital pages are extraction/pdf_digital.py's job
            try:
                pix, scale = _render_grayscale(page)
                pil_image = _pixmap_to_pil(pix)
                words = _run_tesseract_words(pil_image, page_num + 1, scale)
            except Exception as exc:
                logger.warning("pdf_scanned: OCR failed on page %d of %s: %s", page_num + 1, pdf_path, exc)
                continue
            if not words:
                continue
            word_map = SpatialWordMap(words, page_width=float(page.rect.width), page_height=float(page.rect.height))
            for fd in candidate_fields:
                if fs.get(fd.canonical_name) is not None:
                    continue
                found = extract_field_spatially(word_map, fd.all_labels, known_labels)
                if not found:
                    continue
                value, _method, bbox = found
                fs.add(ExtractedField(
                    canonical_name=fd.canonical_name,
                    value=value,
                    raw_value=value,
                    source=Source.PDF_SCANNED,
                    confidence=_FIELD_CONF,
                    page=page_num + 1,
                    bbox=_norm_box(*bbox, word_map.page_width, word_map.page_height),
                ))
    finally:
        doc.close()

    logger.info("pdf_scanned: %d fields found in %s", len(fs.found_fields()), Path(pdf_path).name)
    return fs
