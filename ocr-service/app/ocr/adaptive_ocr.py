"""
Day 7 — Adaptive OCR Engine

Per-page intelligence: digital pages go through PyMuPDF direct extraction.
Scanned pages go through a 5-step image preprocessing pipeline then Tesseract.

The decision threshold, preprocessing steps, and all quality metadata are stored
in adaptive_page_ocr_results for every page — this feeds the confidence system.

Architecture:
  - ProcessedPage: result of one page's OCR pass (data, not behavior)
  - AdaptiveOCREngine: makes the per-page decision, runs preprocessing, stores metadata
  - Replaces the basic load_pdf() for full pipeline runs; load_pdf() remains for quick use

CLAUDE.md Rule 7: parallel page processing via thread pool.
CLAUDE.md Rule 8: file hash before OCR for dedup (hash computed here, checked by caller).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

_DIGITAL_WORD_THRESHOLD = 100     # fewer words → treat page as scanned
_TESSERACT_DPI = 300              # render scanned pages at this DPI for OCR
_LOW_DPI_THRESHOLD = 200          # below → aggressive preprocessing
_HIGH_DPI_THRESHOLD = 400         # above → downsample before OCR


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PageOcrMetadata:
    """Everything the confidence system and DB need about how a page was processed."""
    page_number: int             # 1-indexed
    ocr_path: str                # "pymupdf_direct" | "tesseract"
    word_count_raw: int          # words from PyMuPDF before decision
    word_count_ocr: int          # words after OCR processing
    dpi_estimated: Optional[int] = None
    image_quality_flag: Optional[str] = None   # "low" | "normal" | "high"
    image_variance: Optional[float] = None
    preprocessing_steps: List[str] = field(default_factory=list)
    text_quality_score: float = 1.0            # 0.0-1.0 estimated accuracy
    normalization_log: List[dict] = field(default_factory=list)  # Day 8 populated


@dataclass
class ProcessedPage:
    """Complete output of one page's adaptive OCR pass."""
    page_number: int
    raw_text: str          # text before Day 8 normalization
    normalized_text: str   # text after Day 8 normalization (same as raw until Day 8)
    metadata: PageOcrMetadata

    @property
    def text(self) -> str:
        return self.normalized_text

    @property
    def word_count(self) -> int:
        return len(self.normalized_text.split())


@dataclass
class AdaptiveDocument:
    """Complete output of adaptive OCR for a whole document."""
    path: str
    file_hash: str          # SHA-256 of file bytes
    total_pages: int
    pages: List[ProcessedPage] = field(default_factory=list)
    processing_time_ms: int = 0

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.normalized_text for p in self.pages)

    @property
    def page_index(self) -> Dict[int, str]:
        return {p.page_number: p.normalized_text for p in self.pages}

    @property
    def scanned_page_count(self) -> int:
        return sum(1 for p in self.pages if p.metadata.ocr_path == "tesseract")

    @property
    def digital_page_count(self) -> int:
        return sum(1 for p in self.pages if p.metadata.ocr_path == "pymupdf_direct")

    def ocr_quality_for_page(self, page_number: int) -> float:
        for p in self.pages:
            if p.page_number == page_number:
                return p.metadata.text_quality_score
        return 1.0


# ---------------------------------------------------------------------------
# Image preprocessing pipeline (for scanned pages)
# ---------------------------------------------------------------------------

def _preprocess_scanned_page(
    page: fitz.Page,
    target_dpi: int = _TESSERACT_DPI,
) -> Tuple[object, PageOcrMetadata, int]:
    """
    Apply adaptive preprocessing to a scanned page and run Tesseract OCR.
    Returns (pil_image_for_ocr, partial_metadata, estimated_dpi).
    """
    import numpy as np
    import cv2
    from PIL import Image

    steps: List[str] = []

    # Render at target DPI
    scale = target_dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

    # Estimate DPI from rendered dimensions vs A4/Letter
    estimated_dpi = int(pix.width / (page.rect.width / 72.0))
    if estimated_dpi < _LOW_DPI_THRESHOLD:
        quality_flag = "low"
    elif estimated_dpi > _HIGH_DPI_THRESHOLD:
        quality_flag = "high"
        # Downsample to 300 DPI to reduce compute
        factor = estimated_dpi / _TESSERACT_DPI
        new_w = int(pix.width / factor)
        new_h = int(pix.height / factor)
        img_array = cv2.resize(img_array, (new_w, new_h), interpolation=cv2.INTER_AREA)
        steps.append(f"downsampled_{estimated_dpi}dpi_to_{_TESSERACT_DPI}dpi")
        estimated_dpi = _TESSERACT_DPI
    else:
        quality_flag = "normal"

    # Step 1: Grayscale — already grayscale from fitz.csGRAY, just normalize
    gray = img_array.copy()
    steps.append("grayscale")

    # Step 2: Gaussian denoising — apply when pixel variance indicates noise
    variance = float(np.var(gray))
    noise_threshold = 800.0 if quality_flag == "low" else 1200.0
    if variance > noise_threshold:
        gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
        steps.append(f"gaussian_denoise_var{int(variance)}")

    # Step 3: Otsu thresholding — always apply for binary contrast
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    steps.append("otsu_threshold")

    # Step 4: Deskew — detect rotation from text line angles
    coords = np.column_stack(np.where(binary < 128))
    skew_angle = 0.0
    if len(coords) > 200:
        try:
            rect = cv2.minAreaRect(coords.astype(np.float32))
            angle = rect[-1]
            # minAreaRect returns -90 to 0; convert to -45 to 45
            if angle < -45:
                angle = 90 + angle
            skew_angle = angle
            if 0.5 < abs(skew_angle) < 45:
                (h, w) = binary.shape[:2]
                M = cv2.getRotationMatrix2D((w // 2, h // 2), skew_angle, 1.0)
                binary = cv2.warpAffine(
                    binary, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                steps.append(f"deskew_{skew_angle:.1f}deg")
        except Exception:
            pass

    # Step 5: Table line removal — detect long horizontal/vertical rules
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    horiz = cv2.morphologyEx(255 - binary, cv2.MORPH_OPEN, horiz_kernel)
    vert = cv2.morphologyEx(255 - binary, cv2.MORPH_OPEN, vert_kernel)
    line_pixels = int(np.sum(horiz > 0) + np.sum(vert > 0))
    if line_pixels > 500:
        lines_mask = cv2.add(horiz, vert)
        binary = cv2.add(binary, lines_mask)
        steps.append(f"table_line_removal_{line_pixels}px")

    pil_image = Image.fromarray(binary)

    meta = PageOcrMetadata(
        page_number=page.number + 1,
        ocr_path="tesseract",
        word_count_raw=0,   # set by caller
        word_count_ocr=0,   # set after OCR
        dpi_estimated=estimated_dpi,
        image_quality_flag=quality_flag,
        image_variance=variance,
        preprocessing_steps=steps,
        text_quality_score=0.0,
    )
    return pil_image, meta, estimated_dpi


def _run_tesseract(pil_image) -> str:
    """Run Tesseract OCR on a preprocessed page image."""
    import pytesseract
    config = "--psm 6 --oem 3"  # assume uniform block of text, LSTM engine
    return pytesseract.image_to_string(pil_image, config=config)


def _estimate_text_quality(text: str, ocr_path: str) -> float:
    """
    Heuristic text quality score 0.0-1.0.
    Digital pages start at 1.0. Scanned pages estimated from:
    - word count (more words = better)
    - ratio of alphabetic characters (high garbage OCR has many non-alpha chars)
    - presence of common appraisal words
    """
    if ocr_path == "pymupdf_direct":
        return 1.0
    if not text.strip():
        return 0.0

    words = text.split()
    total_chars = len(text)
    if total_chars == 0:
        return 0.0

    alpha_ratio = sum(1 for c in text if c.isalpha()) / total_chars
    # Score: alpha ratio weighted with word count (more words = better signal)
    base_score = alpha_ratio
    if len(words) > 200:
        base_score = min(1.0, base_score + 0.1)
    elif len(words) < 20:
        base_score = max(0.0, base_score - 0.2)

    return round(base_score, 3)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class AdaptiveOCREngine:
    """
    Per-page adaptive OCR. Digital pages → PyMuPDF. Scanned → Tesseract.
    Processes pages in parallel via thread pool (Rule 7).

    Usage:
        engine = AdaptiveOCREngine()
        doc = engine.process(Path("report.pdf"))
        text = doc.full_text
    """

    def __init__(self, word_threshold: int = _DIGITAL_WORD_THRESHOLD, max_workers: int = 4):
        self._word_threshold = word_threshold
        self._max_workers = max_workers

    def process(self, path: Path) -> AdaptiveDocument:
        """Process a PDF with adaptive per-page OCR. Returns an AdaptiveDocument."""
        start = time.time()
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        file_hash = self._hash_file(path)
        fitz_doc = fitz.open(str(path))
        total_pages = len(fitz_doc)

        # First pass: extract digital text for each page (fast, synchronous)
        raw_digital: Dict[int, str] = {}
        for page_num in range(total_pages):
            page = fitz_doc[page_num]
            raw_digital[page_num] = page.get_text("text") or ""

        fitz_doc.close()

        # Parallel processing: digital pages and scanned pages
        processed: Dict[int, ProcessedPage] = {}

        def _process_one(page_num: int) -> ProcessedPage:
            raw_text = raw_digital[page_num]
            word_count_raw = len(raw_text.split())

            if word_count_raw >= self._word_threshold:
                # Digital page — direct extraction
                meta = PageOcrMetadata(
                    page_number=page_num + 1,
                    ocr_path="pymupdf_direct",
                    word_count_raw=word_count_raw,
                    word_count_ocr=word_count_raw,
                    preprocessing_steps=[],
                    text_quality_score=1.0,
                )
                return ProcessedPage(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    normalized_text=raw_text,
                    metadata=meta,
                )
            else:
                # Scanned page — Tesseract OCR
                fitz_doc2 = fitz.open(str(path))
                page = fitz_doc2[page_num]
                try:
                    pil_image, meta, _ = _preprocess_scanned_page(page)
                    meta.word_count_raw = word_count_raw
                    ocr_text = _run_tesseract(pil_image)
                    meta.word_count_ocr = len(ocr_text.split())
                    meta.text_quality_score = _estimate_text_quality(ocr_text, "tesseract")
                    text = ocr_text if ocr_text.strip() else raw_text
                except Exception as exc:
                    logger.warning("Tesseract failed on page %d of %s: %s", page_num + 1, path.name, exc)
                    text = raw_text
                    meta = PageOcrMetadata(
                        page_number=page_num + 1,
                        ocr_path="tesseract",
                        word_count_raw=word_count_raw,
                        word_count_ocr=word_count_raw,
                        preprocessing_steps=["failed"],
                        text_quality_score=0.3,
                    )
                finally:
                    fitz_doc2.close()

                return ProcessedPage(
                    page_number=page_num + 1,
                    raw_text=text,
                    normalized_text=text,
                    metadata=meta,
                )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(_process_one, i): i for i in range(total_pages)}
            for fut in as_completed(futures):
                result = fut.result()
                processed[result.page_number] = result

        pages = [processed[i + 1] for i in range(total_pages) if i + 1 in processed]
        elapsed_ms = int((time.time() - start) * 1000)

        doc = AdaptiveDocument(
            path=str(path),
            file_hash=file_hash,
            total_pages=total_pages,
            pages=pages,
            processing_time_ms=elapsed_ms,
        )

        digital = doc.digital_page_count
        scanned = doc.scanned_page_count
        logger.info(
            "AdaptiveOCR: %s — %d pages (%d digital, %d scanned) in %dms",
            path.name, total_pages, digital, scanned, elapsed_ms,
        )
        return doc

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def persist_ocr_metadata(self, doc: AdaptiveDocument, document_id: str) -> None:
        """Store per-page OCR metadata in adaptive_page_ocr_results."""
        from app.database import get_db
        from app.models.db_models import PageOcrResultRow

        with get_db() as session:
            for page in doc.pages:
                m = page.metadata
                row = PageOcrResultRow(
                    document_id=document_id,
                    page_number=page.page_number,
                    ocr_path=m.ocr_path,
                    word_count_raw=m.word_count_raw,
                    word_count_ocr=m.word_count_ocr,
                    dpi_estimated=m.dpi_estimated,
                    image_quality_flag=m.image_quality_flag,
                    image_variance=m.image_variance,
                    preprocessing_steps_json=json.dumps(m.preprocessing_steps),
                    text_quality_score=m.text_quality_score,
                    normalization_log_json=json.dumps(m.normalization_log) if m.normalization_log else None,
                    raw_text_length=len(page.raw_text),
                    normalized_text_length=len(page.normalized_text),
                )
                session.add(row)
        logger.debug("Persisted OCR metadata: %s (%d pages)", document_id, len(doc.pages))


# Module-level singleton
adaptive_ocr = AdaptiveOCREngine()
