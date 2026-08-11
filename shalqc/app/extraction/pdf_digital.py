"""
extractor.pdf_digital (pdd-1.0.0) — PyMuPDF word maps, label-proximity extraction.

SHALqc.md §3.2 step 2: pages with ≥30 words are "digital" — PyMuPDF word-level
text is reliable, so no OCR is needed. Labels and values are spatially
co-located on the page (same row, or one row below); linear text-stream
reading loses this because rendering order can separate them from their
values. Confidence band 0.85–0.92 depending on which spatial strategy wins.

Ported from ocr-service/app/ocr/spatial_extractor.py, re-pointed at the
ExtractedField contract and schema_loader.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source
from app.extraction.schema import schema_loader as _default_schema_loader

__version__ = "pdd-1.0.0"

logger = logging.getLogger(__name__)

DIGITAL_WORD_THRESHOLD = 30     # SHALqc.md §3.2: ≥30 words/page ⇒ digital

Y_ROW_TOLERANCE = 6.0
X_RIGHT_MAX = 500.0
Y_BELOW_MAX = 22.0
MIN_VALUE_LENGTH = 1

_CONF_RIGHT_OF = 0.90
_CONF_BELOW = 0.88
_CONF_PATTERN_FALLBACK = 0.85


@dataclass
class SpatialWord:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    page_number: int

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


class SpatialWordMap:
    """Spatial index of all words on a page, built from PyMuPDF word extraction."""

    def __init__(self, words: List[SpatialWord], page_width: float = 0.0, page_height: float = 0.0) -> None:
        self._words = words
        self.page_width = page_width
        self.page_height = page_height

    @classmethod
    def from_fitz_page(cls, page, page_number: int) -> "SpatialWordMap":
        raw_words = page.get_text("words")
        words = [
            SpatialWord(x0=float(w[0]), y0=float(w[1]), x1=float(w[2]), y1=float(w[3]),
                        text=w[4].strip(), page_number=page_number)
            for w in raw_words if w[4].strip()
        ]
        return cls(words, page_width=float(page.rect.width), page_height=float(page.rect.height))

    def find_label(self, synonyms: List[str], known_labels: FrozenSet[str]
                   ) -> Optional[Tuple[float, float, float, float, str]]:
        """Return (x0, y0, x1, y1, matched_text) for the first synonym found."""
        for syn in synonyms:
            syn_words = syn.strip().split()
            if not syn_words:
                continue
            if len(syn_words) == 1:
                word = syn_words[0].lower()
                for sw in self._words:
                    if sw.text.lower().rstrip(":/.,") == word:
                        return sw.x0, sw.y0, sw.x1, sw.y1, sw.text
            else:
                first = syn_words[0].lower()
                candidates = [sw for sw in self._words if sw.text.lower().rstrip(":/.,") == first]
                for candidate in candidates:
                    matched = self._match_phrase_from(candidate, syn_words)
                    if matched:
                        last = matched[-1]
                        return candidate.x0, candidate.y0, last.x1, last.y1, " ".join(sw.text for sw in matched)
        return None

    def _match_phrase_from(self, first_word: SpatialWord, phrase_words: List[str]) -> Optional[List[SpatialWord]]:
        if first_word.text.lower().rstrip(":/.,") != phrase_words[0].lower():
            return None
        result = [first_word]
        for next_label_word in phrase_words[1:]:
            candidates = [
                sw for sw in self._words
                if sw.x0 > result[-1].x1
                and abs(sw.y_center - first_word.y_center) < Y_ROW_TOLERANCE
                and sw.x0 - result[-1].x1 < 40
            ]
            candidates.sort(key=lambda sw: sw.x0)
            if not candidates or candidates[0].text.lower().rstrip(":/.,") != next_label_word.lower():
                return None
            result.append(candidates[0])
        return result

    def value_words_right_of(self, label_x1: float, label_y0: float, label_y1: float,
                              known_labels: FrozenSet[str]) -> List[SpatialWord]:
        row_y_center = (label_y0 + label_y1) / 2
        row_tolerance = max(Y_ROW_TOLERANCE, (label_y1 - label_y0) * 0.6)
        candidates = sorted(
            (sw for sw in self._words
             if label_x1 < sw.x0 < label_x1 + X_RIGHT_MAX
             and abs(sw.y_center - row_y_center) <= row_tolerance
             and len(sw.text) >= MIN_VALUE_LENGTH),
            key=lambda sw: sw.x0,
        )
        result: List[SpatialWord] = []
        prev_x1 = label_x1
        for sw in candidates:
            if sw.x0 - prev_x1 > 120:
                break
            text_norm = sw.text.lower().rstrip(":/.,")
            if len(text_norm) >= 3 and text_norm in known_labels:
                break
            result.append(sw)
            prev_x1 = sw.x1
        return result

    def value_words_below(self, label_x0: float, label_x1: float, label_y1: float,
                           known_labels: FrozenSet[str]) -> List[SpatialWord]:
        below_words = sorted(
            (sw for sw in self._words
             if label_y1 < sw.y0 < label_y1 + Y_BELOW_MAX
             and sw.x1 > label_x0 - 10 and sw.x0 < label_x1 + 10),
            key=lambda sw: sw.x0,
        )
        result: List[SpatialWord] = []
        for sw in below_words:
            if sw.text.lower().rstrip(":/.,") in known_labels:
                break
            result.append(sw)
        return result

    def __len__(self) -> int:
        return len(self._words)


def build_known_label_set(schema) -> FrozenSet[str]:
    """Collision set: every 3+ char, non-numeric synonym word across the schema."""
    labels: set = set()
    for fd in schema.all_fields():
        for syn in fd.synonyms:
            for word in syn.lower().split():
                stripped = word.rstrip(":/.,()#$%")
                if stripped.isdigit() or len(stripped) < 3:
                    continue
                labels.add(stripped)
    return frozenset(labels)


def _norm_box(x0: float, y0: float, x1: float, y1: float, page_w: float, page_h: float) -> Optional[Dict[str, float]]:
    if page_w <= 0 or page_h <= 0:
        return None
    x, y = max(0.0, x0 / page_w), max(0.0, y0 / page_h)
    w, h = min(1.0 - x, (x1 - x0) / page_w), min(1.0 - y, (y1 - y0) / page_h)
    if w <= 0 or h <= 0:
        return None
    return {"x": round(x, 5), "y": round(y, 5), "w": round(w, 5), "h": round(h, 5)}


def extract_field_spatially(
    word_map: SpatialWordMap, synonyms: List[str], known_labels: FrozenSet[str],
) -> Optional[Tuple[str, str, Tuple[float, float, float, float]]]:
    """Returns (value_text, method, (x0,y0,x1,y1)) or None.

    method: "spatial_right_of_label" | "spatial_below_label"
    """
    label_bbox = word_map.find_label(synonyms, known_labels)
    if not label_bbox:
        return None
    lx0, ly0, lx1, ly1, _matched = label_bbox

    right_words = word_map.value_words_right_of(lx1, ly0, ly1, known_labels)
    if right_words:
        value = " ".join(w.text for w in right_words).strip()
        if value:
            bbox = (right_words[0].x0, right_words[0].y0, right_words[-1].x1, right_words[-1].y1)
            return value, "spatial_right_of_label", bbox

    below_words = word_map.value_words_below(lx0, lx1, ly1, known_labels)
    if below_words:
        value = " ".join(w.text for w in below_words).strip()
        if value:
            bbox = (below_words[0].x0, below_words[0].y0, below_words[-1].x1, below_words[-1].y1)
            return value, "spatial_below_label", bbox

    return None


def is_digital_page(page) -> bool:
    """SHALqc.md §3.2: ≥30 words on the page ⇒ digital."""
    return len((page.get_text("text") or "").split()) >= DIGITAL_WORD_THRESHOLD


# Fields owned by other extractors — the digital-page label-proximity pass must
# not fight the grid extractor (comp columns) or checkbox extractor (enum
# checkboxes) for the same canonical names.
_SKIP_SUFFIXES = ("_adjustment", "_blank")
_SKIP_PREFIXES = ("comp_", "subject_grid_")


def extract_pdf_digital(pdf_path, schema=None, max_pages: Optional[int] = None) -> ExtractedFieldSet:
    """Label-proximity extraction over the digital pages of an appraisal PDF.

    Only the first `max_pages` are scanned — main URAR form content lives
    there; narrative/exhibit pages are handled by other extractors/LLM gap-fill.

    2026-08-09: `max_pages` was a hardcoded 8 — correct for a 1004, catastrophic
    for the 40-page UAD 3.6 URAR where pages 9-40 hold the ENTIRE valuation
    (market trends, listing history, the 6-comp sales grid, reconciliation,
    certifications). Now config-driven via EXTRACT_MAX_PAGES so a long report is
    a setting, not a code change. `None` = read the settings default.
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
        logger.warning("pdf_digital: cannot open %s: %s", pdf_path, exc)
        return fs

    try:
        candidate_fields = [
            fd for fd in schema.all_fields()
            if not fd.canonical_name.startswith(_SKIP_PREFIXES)
            and not fd.canonical_name.endswith(_SKIP_SUFFIXES)
        ]
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            if not is_digital_page(page):
                continue
            word_map = SpatialWordMap.from_fitz_page(page, page_num + 1)
            for fd in candidate_fields:
                if fs.get(fd.canonical_name) is not None:
                    continue  # first page to find it wins
                found = extract_field_spatially(word_map, fd.all_labels, known_labels)
                if not found:
                    continue
                value, method, bbox = found
                conf = _CONF_RIGHT_OF if method == "spatial_right_of_label" else _CONF_BELOW
                fs.add(ExtractedField(
                    canonical_name=fd.canonical_name,
                    value=value,
                    raw_value=value,
                    source=Source.PDF_DIGITAL,
                    confidence=conf,
                    page=page_num + 1,
                    bbox=_norm_box(*bbox, word_map.page_width, word_map.page_height),
                ))
    finally:
        doc.close()

    logger.info("pdf_digital: %d fields found in %s", len(fs.found_fields()), Path(pdf_path).name)
    return fs
