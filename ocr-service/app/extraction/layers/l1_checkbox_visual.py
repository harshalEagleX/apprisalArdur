"""
Layer 1 — OpenCV Visual Checkbox Detector

Fixes the Yes/No context ambiguity problem:
  The existing checkbox_extractor.py detects X marks in vector drawings.
  This layer renders the page as an image and measures PIXEL FILL DENSITY
  inside each checkbox rectangle — a filled box is checked regardless of
  whether the PDF uses X marks, filled squares, or tick marks.

Why this is needed:
  - TOTAL software: X marks (already handled by existing detector)
  - Clickforms: filled rectangles (needs pixel analysis)
  - Other software: various markers (needs pixel analysis)

Additionally, this layer solves Yes/No context by:
  1. Rendering the page
  2. Finding ALL checkbox squares via contour detection
  3. For each checkbox: is it filled? + what text is immediately to its right?
  4. For each Yes/No pair: find the QUESTION TEXT directly ABOVE the pair
     → that question text disambiguates which field the Yes/No belongs to

Output: {field_name: value} with 0.90 confidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Render DPI for checkbox analysis (150 is enough, faster than 300)
_RENDER_DPI = 150
_CHECKBOX_MIN_SIZE = 8     # pixels at 150 DPI
_CHECKBOX_MAX_SIZE = 25
_FILL_THRESHOLD = 0.35     # fraction of pixels dark inside box = checked
_LABEL_SEARCH_PX = 150     # search this far right of checkbox for label
_QUESTION_SEARCH_PX = 60   # search this far ABOVE Yes/No pair for question

# Yes/No question → canonical field + True/False assignment
YES_NO_QUESTIONS = {
    # UAD Subject Section
    "offered for sale": ("offered_for_sale_12mo", "yes_is_true"),
    "12 months prior": ("offered_for_sale_12mo", "yes_is_true"),
    "pud": ("is_pud_checked", "yes_is_true"),
    "planned unit development": ("is_pud_checked", "yes_is_true"),
    "seller the owner": ("is_seller_owner_of_record", "yes_is_true"),
    "seller owner of public record": ("is_seller_owner_of_record", "yes_is_true"),
    "financial assistance": ("has_financial_assistance", "yes_is_true"),
    "loan charges": ("has_financial_assistance", "yes_is_true"),
    "concessions": ("has_financial_assistance", "yes_is_true"),
    "highest and best use": ("highest_and_best_use", "yes_is_true"),
    "existing use its highest": ("highest_and_best_use", "yes_is_true"),
    # Site Section
    "fema special flood": ("fema_flood_hazard", "yes_is_true"),
    "flood hazard area": ("fema_flood_hazard", "yes_is_true"),
    "utilities and off-site": ("utilities_typical_for_market", "yes_is_true"),
    "typical for the market": ("utilities_typical_for_market", "yes_is_true"),
    "adverse site conditions": ("adverse_site_conditions", "yes_is_true"),
    "easements": ("adverse_site_conditions", "yes_is_true"),
    # Improvements
    "adverse conditions": ("adverse_conditions", "yes_is_true"),
    "livability": ("adverse_conditions", "yes_is_true"),
    "conform to the neighborhood": ("conforms_to_neighborhood", "yes_is_true"),
    "functional": ("conforms_to_neighborhood", "yes_is_true"),
    "analyzed the contract": ("did_analyze_contract", "yes_is_true"),
    "did analyze": ("did_analyze_contract", "yes_is_true"),
    # Sales Comparison
    "foreclosure sales": ("foreclosure_sales_factor", "yes_is_true"),
    # USPAP
    "have not performed": ("prior_services_performed", "yes_is_false"),
    "have performed": ("prior_services_performed", "yes_is_true"),
}


@dataclass
class CheckedBox:
    """A checkbox detected visually on the page."""
    x: int           # top-left pixel
    y: int
    w: int
    h: int
    is_filled: bool
    fill_ratio: float
    label_text: str   # text immediately to the right
    page_number: int


def _render_page_to_image(page) -> np.ndarray:
    """Render a fitz page to a grayscale numpy array at _RENDER_DPI."""
    import fitz
    scale = _RENDER_DPI / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _find_checkbox_squares(gray: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Find checkbox squares via contour detection.
    Returns list of (x, y, w, h) for each candidate checkbox.
    """
    # Threshold
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Filter by size (checkbox-sized squares)
        if not (_CHECKBOX_MIN_SIZE <= w <= _CHECKBOX_MAX_SIZE and
                _CHECKBOX_MIN_SIZE <= h <= _CHECKBOX_MAX_SIZE):
            continue
        # Must be roughly square
        if max(w, h) / max(min(w, h), 1) > 2.0:
            continue
        boxes.append((x, y, w, h))

    return boxes


def _measure_fill(gray: np.ndarray, x: int, y: int, w: int, h: int) -> float:
    """Measure what fraction of pixels inside the box are dark (filled)."""
    # Add 2px margin inside to avoid box border itself
    margin = 2
    inner = gray[y + margin: y + h - margin, x + margin: x + w - margin]
    if inner.size == 0:
        return 0.0
    dark_pixels = np.sum(inner < 128)
    return float(dark_pixels) / inner.size


def _find_text_right_of(
    x: int, y: int, w: int, h: int,
    words_on_page: List[Tuple],
    max_distance: int = _LABEL_SEARCH_PX,
) -> str:
    """Find text words immediately to the right of a box, same vertical band."""
    cy = y + h / 2
    candidates = [
        (wx, wy, wtext)
        for wx, wy, wx1, wy1, wtext in words_on_page
        if wx > x + w and wx < x + w + max_distance
        and abs((wy + wy1) / 2 - cy) < h * 1.5
    ]
    candidates.sort(key=lambda c: c[0])
    return " ".join(c[2] for c in candidates[:4])


def _find_question_above(
    x: int, y: int,
    words_on_page: List[Tuple],
    search_height: int = _QUESTION_SEARCH_PX,
) -> str:
    """
    Find the question text that appears ABOVE the Yes/No checkbox pair.
    This is the key disambiguation: each Yes/No pair belongs to exactly
    one question, which is the text immediately above it at the same X range.
    """
    candidates = [
        wtext
        for wx, wy, wx1, wy1, wtext in words_on_page
        if wy < y and wy > y - search_height
        and not wtext.strip().lower() in ("yes", "no", "y", "n")
    ]
    return " ".join(candidates[-8:]).lower()  # last 8 words before Yes/No


def extract_checkboxes_visual(
    pdf_path: Path,
    document_type: str,
    max_pages: int = 10,
) -> Dict[str, str]:
    """
    Render each page as image, detect checkboxes visually via pixel fill density.
    For Yes/No questions, find the question text ABOVE to disambiguate context.

    Returns {canonical_field_name: "True"/"False"} for all detected checkboxes.
    """
    results: Dict[str, str] = {}

    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("Cannot open PDF for visual checkbox: %s", exc)
        return results

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        pn = page_num + 1

        # Skip pages with very few words (likely blank or image-heavy)
        word_count = len(page.get_text("text").split())
        if word_count < 5:
            continue

        # Get word positions for label lookup (scale to image coordinates)
        raw_words = page.get_text("words")  # (x0, y0, x1, y1, text, ...)
        scale = _RENDER_DPI / 72.0
        words_scaled = [
            (int(w[0] * scale), int(w[1] * scale),
             int(w[2] * scale), int(w[3] * scale), w[4])
            for w in raw_words if w[4].strip()
        ]

        # Render and detect
        try:
            gray = _render_page_to_image(page)
            boxes = _find_checkbox_squares(gray)
        except Exception as exc:
            logger.debug("Visual checkbox render failed p%d: %s", pn, exc)
            continue

        # Group boxes into Yes/No pairs (boxes within ~30px of each other horizontally)
        yes_no_pairs = []
        used = set()
        boxes_sorted = sorted(boxes, key=lambda b: (round(b[1] / 5) * 5, b[0]))

        for i, (x1, y1, w1, h1) in enumerate(boxes_sorted):
            if i in used:
                continue
            # Find a nearby box on the same row (potential Yes/No pair)
            for j, (x2, y2, w2, h2) in enumerate(boxes_sorted):
                if j <= i or j in used:
                    continue
                if abs(y1 - y2) < max(h1, h2) * 1.5 and abs(x2 - x1 - w1) < 40:
                    yes_no_pairs.append(((x1, y1, w1, h1), (x2, y2, w2, h2)))
                    used.add(i)
                    used.add(j)
                    break

        for (bx1, by1, bw1, bh1), (bx2, by2, bw2, bh2) in yes_no_pairs:
            fill1 = _measure_fill(gray, bx1, by1, bw1, bh1)
            fill2 = _measure_fill(gray, bx2, by2, bw2, bh2)

            label1 = _find_text_right_of(bx1, by1, bw1, bh1, words_scaled)
            label2 = _find_text_right_of(bx2, by2, bw2, bh2, words_scaled)

            # Identify which is "Yes" and which is "No"
            if "yes" in label1.lower() and "no" in label2.lower():
                yes_filled = fill1 >= _FILL_THRESHOLD
                no_filled = fill2 >= _FILL_THRESHOLD
            elif "no" in label1.lower() and "yes" in label2.lower():
                yes_filled = fill2 >= _FILL_THRESHOLD
                no_filled = fill1 >= _FILL_THRESHOLD
            else:
                continue  # not a clear Yes/No pair

            if not yes_filled and not no_filled:
                continue  # neither clearly checked

            # Find the question above this pair for context disambiguation
            pair_y = min(by1, by2)
            pair_x = min(bx1, bx2)
            question_text = _find_question_above(pair_x, pair_y, words_scaled)

            # Match to known field
            field_name = None
            yes_is_true = True

            for key, (fname, polarity) in YES_NO_QUESTIONS.items():
                if key in question_text:
                    field_name = fname
                    yes_is_true = (polarity == "yes_is_true")
                    break

            if not field_name:
                continue

            # Determine value
            if yes_filled:
                value = "True" if yes_is_true else "False"
            else:
                value = "False" if yes_is_true else "True"

            if field_name not in results:
                results[field_name] = value
                logger.debug(
                    "L1 visual checkbox p%d: %s=%s (question: %s…)",
                    pn, field_name, value, question_text[:40],
                )

    doc.close()
    logger.info("L1 visual checkbox: %s — %d fields found", pdf_path.name, len(results))
    return results
