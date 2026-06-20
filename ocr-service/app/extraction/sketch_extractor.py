"""Building Sketch GLA extractor — extraction layer.

The "Total Living Area" figure lives inside the rasterized sketch image on the
"Building Sketch" page (TOTAL by a la mode software), NOT in the PDF text layer,
so it needs OCR or vision. We locate the sketch page by its "Building Sketch"
header, render it, and read the "Total Living Area (Rounded)" value — the
authoritative GLA the SCA-17 rule cross-checks against the grid / improvements
GLA (the common error: appraiser updates the grid but not the sketch).

Two readers, cheap-first (P-6 / cost):
  1. Tesseract OCR of the page image — fast, free, works on clean printed
     area-calc tables.
  2. Vision fallback (Gemini, then Groq llama-4-scout) when OCR can't find the
     total — handles handwritten / rotated / low-quality sketches by "studying"
     the image.

Returns {} on any failure so SCA-17 degrades to "could not confirm against the
sketch" (P-6).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# "Total Living Area (Rounded): 2301 Sq ft" — the authoritative total. The
# non-parenthesized form is the fallback for software that omits "(Rounded)".
_TOTAL_ROUNDED = re.compile(r"total\s+living\s+area\s*\(rounded\)\s*:?\s*([\d,]+)", re.I)
_TOTAL_ANY = re.compile(r"total\s+living\s+area[^\d]{0,20}([\d,]+)\s*sq", re.I)
# Per-floor above-grade living-area subtotals on the TOTAL sketch "Area
# Calculations Summary". Summing these recovers the grand total when the sketch
# prints no explicit "Total Living Area (Rounded)" line in the text layer (the
# 1,485.6 + 986.75 = 2,472 case the partial-floor bug used to mis-read as 1,496).
# Garage/porch/basement/unfinished areas are deliberately excluded — they are NOT
# floor-labelled and never above-grade GLA.
_FLOOR_AREA = re.compile(
    r"\b(?:first|second|third|fourth|upper|lower|main|ground|1st|2nd|3rd|4th)\s+"
    r"floor\s*:?\s*([\d,]+\.?\d*)\s*sq", re.I)

_VISION_PROMPT = (
    "This image is the Building Sketch page of a residential appraisal (TOTAL "
    "software). Read the 'Area Calculations Summary' / 'Living Area' table and "
    'return ONLY JSON: {"total_living_area_sqft": <number>} — the Total Living '
    "Area (Rounded) above-grade gross living area in square feet. Exclude garage "
    "and other non-living area. Digits only, no commas."
)


def _plausible(n: Optional[int]) -> Optional[int]:
    return n if (n is not None and 200 <= n <= 20000) else None


def _find_sketch_page(doc) -> Optional[int]:
    for i in range(doc.page_count):
        if "building sketch" in (doc[i].get_text() or "").lower():
            return i
    return None


def _sketch_pages_text(doc) -> str:
    """Concatenated text of every 'Building Sketch' page (TOTAL splits multi-floor
    sketches across 'Building Sketch (Page - N)' pages, so a single page misses
    floors)."""
    parts = []
    for i in range(doc.page_count):
        t = doc[i].get_text() or ""
        if "building sketch" in t.lower():
            parts.append(t)
    return "\n".join(parts)


def _text_total(doc) -> Optional[int]:
    """Read the sketch total from the text layer (cheap-first, P-6): prefer an
    explicit 'Total Living Area (Rounded)', else sum the per-floor subtotals.
    Returns None when neither is present (image-only sketch → OCR/vision)."""
    text = _sketch_pages_text(doc)
    if not text:
        return None
    m = _TOTAL_ROUNDED.search(text) or _TOTAL_ANY.search(text)
    if m:
        try:
            return _plausible(int(m.group(1).replace(",", "")))
        except (TypeError, ValueError):
            pass
    floors = _FLOOR_AREA.findall(text)
    if floors:
        try:
            total = sum(float(f.replace(",", "")) for f in floors)
            return _plausible(int(round(total)))
        except (TypeError, ValueError):
            pass
    return None


def _ocr_total(png: bytes) -> Optional[int]:
    try:
        import pytesseract
        from PIL import Image
        txt = pytesseract.image_to_string(Image.open(io.BytesIO(png)))
    except Exception as exc:
        logger.warning("Sketch OCR unavailable: %s", exc)
        return None
    m = _TOTAL_ROUNDED.search(txt) or _TOTAL_ANY.search(txt)
    if not m:
        return None
    try:
        return _plausible(int(m.group(1).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _gemini_vision_json(png: bytes, prompt: str) -> Optional[dict]:
    from app import config
    if not config.GEMINI_API_KEY:
        return None
    import requests
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{config.GEMINI_MODEL}:generateContent")
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    try:
        resp = requests.post(
            url, headers={"Content-Type": "application/json", "X-goog-api-key": config.GEMINI_API_KEY},
            json=body, timeout=config.GEMINI_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Gemini sketch vision HTTP %s", resp.status_code)
            return None
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = next((p["text"] for p in reversed(parts) if "text" in p), "")
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0) if m else text)
    except Exception as exc:
        logger.warning("Gemini sketch vision failed: %s", exc)
        return None


def _vision_total(png: bytes) -> Optional[int]:
    """Read the Total Living Area by 'studying' the sketch image. Gemini first
    (preferred), then Groq llama-4-scout — both behind the vision config."""
    from app import config
    data = _gemini_vision_json(png, _VISION_PROMPT) if config.VISION_ENABLED else None
    if not data:
        from app.extraction import llm_groq
        data = llm_groq.vision_chat_json(png, _VISION_PROMPT)
    if not data:
        return None
    v = data.get("total_living_area_sqft", data.get("total_living_area"))
    try:
        return _plausible(int(float(str(v).replace(",", ""))))
    except (TypeError, ValueError):
        return None


def extract_sketch_gla(pdf_path) -> Dict[str, str]:
    """Return {sketch_living_area, _sketch_page, _sketch_method} or {}."""
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        logger.warning("Sketch extractor needs PyMuPDF: %s", exc)
        return {}

    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        doc = fitz.open(str(Path(pdf_path)))
    except Exception as exc:
        logger.warning("Sketch extractor could not open %s: %s", name, exc)
        return {}
    try:
        idx = _find_sketch_page(doc)
        if idx is None:
            return {}
        # Text-layer first (cheap, exact): explicit total or summed floor subtotals.
        val = _text_total(doc)
        method = "sketch_text"
        png = None if val is not None else \
            doc[idx].get_pixmap(matrix=fitz.Matrix(3, 3)).tobytes("png")  # ~216 DPI
    except Exception as exc:
        logger.warning("Sketch render failed for %s: %s", name, exc)
        return {}
    finally:
        doc.close()

    if val is None:
        val = _ocr_total(png)
        method = "sketch_ocr"
    if val is None:
        val = _vision_total(png)
        method = "sketch_vision"
    if val is None:
        logger.info("Sketch GLA not readable (OCR+vision) for %s", name)
        return {}
    logger.info("Sketch GLA for %s: %s sf (page %d, %s)", name, val, idx + 1, method)
    return {"sketch_living_area": str(val), "_sketch_page": str(idx + 1), "_sketch_method": method}
