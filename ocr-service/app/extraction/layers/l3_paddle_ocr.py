"""
Layer 3 — PaddleOCR for Scanned Pages

PaddleOCR is significantly better than Tesseract for:
  - Form-style documents with mixed layouts
  - Documents with tables and structured content
  - Text that appears at angles or with noise

This layer only activates for pages where PyMuPDF finds < 30 words
(i.e., scanned pages). Digital pages use PyMuPDF directly.

Output format matches the SpatialWordMap interface so it's a drop-in
replacement for the Tesseract-based scanned page OCR.

Lazy loading: PaddleOCR model loads on first use (~3s), then stays cached.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_paddle_ocr_instance = None


def _get_paddle_ocr():
    """Lazy-load PaddleOCR. PaddleOCR 3.x changed the constructor — the old
    use_gpu/show_log/use_angle_cls/enable_mkldnn args raise 'Unknown argument'
    and made this silently unavailable (falling back to Tesseract). Use the 3.x
    signature; disable the orientation/unwarp sub-models for CPU speed."""
    global _paddle_ocr_instance
    if _paddle_ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_ocr_instance = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            logger.info("PaddleOCR (3.x) loaded successfully")
        except Exception as exc:
            logger.warning("PaddleOCR load failed: %s", exc)
            _paddle_ocr_instance = "unavailable"
    return None if _paddle_ocr_instance == "unavailable" else _paddle_ocr_instance


def _page_to_image_array(page) -> np.ndarray:
    """Render a fitz page to RGB numpy array at 300 DPI."""
    import fitz
    mat = fitz.Matrix(300 / 72, 300 / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def ocr_scanned_page_with_paddle(
    page,
    page_number: int,
) -> Optional[List[Tuple[float, float, float, float, str, float]]]:
    """
    Run PaddleOCR on a single scanned page.
    Returns list of (x0, y0, x1, y1, text, confidence) tuples.
    Scale is in PDF points (72 DPI coordinates).
    Returns None if PaddleOCR is unavailable.
    """
    ocr = _get_paddle_ocr()
    if ocr is None:
        return None

    try:
        img = _page_to_image_array(page)
        scale = 72.0 / 300.0   # 300 DPI pixels back to 72 DPI points

        # PaddleOCR 3.x: predict() returns a list of dict-like OCRResult objects
        # with rec_texts / rec_scores / rec_polys. Fall back to the legacy
        # ocr(cls=True) [[box,(text,conf)],...] shape for older installs.
        if hasattr(ocr, "predict"):
            results = ocr.predict(img)
            words = []
            for res in results or []:
                texts = res.get("rec_texts", [])
                scores = res.get("rec_scores", [1.0] * len(texts))
                polys = res.get("rec_polys", res.get("dt_polys", []))
                for text, conf, poly in zip(texts, scores, polys):
                    if not text or not str(text).strip():
                        continue
                    xs = [float(p[0]) for p in poly]
                    ys = [float(p[1]) for p in poly]
                    words.append((min(xs) * scale, min(ys) * scale,
                                  max(xs) * scale, max(ys) * scale,
                                  str(text).strip(), float(conf)))
            return words

        result = ocr.ocr(img)
        if not result or not result[0]:
            return []
        words = []
        for line in result[0]:
            box, (text, conf) = line
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            if text.strip():
                words.append((min(xs) * scale, min(ys) * scale,
                              max(xs) * scale, max(ys) * scale, text.strip(), float(conf)))
        return words

    except Exception as exc:
        logger.warning("PaddleOCR failed on page %d: %s", page_number, exc)
        return None


def extract_scanned_pdf_with_paddle(
    pdf_path: Path,
    max_pages: int = 30,
) -> Dict[int, List[Tuple[float, float, float, float, str]]]:
    """
    Extract text with positions from all scanned pages using PaddleOCR.
    Returns {page_number: [(x0, y0, x1, y1, text), ...]}
    Only processes pages where PyMuPDF finds < 30 words (scanned pages).
    """
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("Cannot open PDF for PaddleOCR: %s", exc)
        return {}

    results: Dict[int, List] = {}
    scanned_count = 0

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        pn = page_num + 1

        # Only use PaddleOCR for scanned pages
        digital_words = len(page.get_text("text").split())
        if digital_words >= 30:
            continue

        paddle_words = ocr_scanned_page_with_paddle(page, pn)
        if paddle_words is not None and len(paddle_words) > 0:
            results[pn] = [(x0, y0, x1, y1, text) for x0, y0, x1, y1, text, conf in paddle_words]
            scanned_count += 1

    doc.close()

    if scanned_count > 0:
        logger.info(
            "L3 PaddleOCR: %s — processed %d scanned pages",
            pdf_path.name, scanned_count,
        )
    return results
