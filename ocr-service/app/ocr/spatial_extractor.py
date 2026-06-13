"""
Spatial PDF Extractor — image-as-layout extraction

Core insight discovered from real UAD 1073 form (90 NE 32nd St Unit 524, Miami FL):
  "Property Address" label at y=59.0, value "90 NE 32nd St" at y=60.4 — same row (Δy=1.4px)
  "Unit #" label at y=59.0, value "524" at y=60.4 — same row
  "HOA $" label at y=119.0, value "635" at y=120.4 — same row

This means labels and values are SPATIALLY CO-LOCATED on the same horizontal row.
Linear text stream extraction misses this because PyMuPDF reads in rendering order
(labels and values can be in different rendering layers).

Fix: render page → extract ALL words with (x, y) bounding boxes →
     for each field, find its label spatially → collect nearby values.

Works for BOTH digital pages (PyMuPDF word positions) and scanned pages (Tesseract).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

# How close a value word must be to a label word's Y center to be on the "same row"
Y_ROW_TOLERANCE = 6.0      # pixels — covers the 1.4px offset seen in real docs
# How far to look to the right on the same row for the value
X_RIGHT_MAX = 500.0        # pixels — don't cross to next column if it's far away
# How far below to look for values on the next line (label above, value below)
Y_BELOW_MAX = 22.0         # pixels — one text line
# Minimum word length to consider as a value (not noise)
MIN_VALUE_LENGTH = 1

# Strip everything but alphanumerics and lowercase, so value-vs-word comparison is
# insensitive to spaces, commas, currency signs and punctuation ("$1,450" == "1450").
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize_for_match(text: str) -> str:
    return _NON_ALNUM.sub("", (text or "").lower())


@dataclass
class SpatialWord:
    """A single word extracted with its position."""
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

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def width(self) -> float:
        return self.x1 - self.x0


class SpatialWordMap:
    """
    Spatial index of all words on a page with their (x, y) positions.
    Built from PyMuPDF word extraction for digital pages.

    Primary query: given a label bbox, find the value words that are
    spatially adjacent (same row to the right, or one line below).
    """

    def __init__(self, words: List[SpatialWord]) -> None:
        self._words = words
        # Build sorted lookup tables for fast spatial queries
        self._by_y: List[SpatialWord] = sorted(words, key=lambda w: (w.y_center, w.x0))

    @classmethod
    def from_fitz_page(cls, page, page_number: int) -> "SpatialWordMap":
        """
        Build SpatialWordMap from a PyMuPDF page using word-level extraction.
        Returns exact word positions for digital PDFs.
        """
        import fitz
        raw_words = page.get_text("words")
        # fitz format: (x0, y0, x1, y1, word, block_no, line_no, word_no)
        words = [
            SpatialWord(
                x0=float(w[0]), y0=float(w[1]),
                x1=float(w[2]), y1=float(w[3]),
                text=w[4].strip(),
                page_number=page_number,
            )
            for w in raw_words
            if w[4].strip()
        ]
        return cls(words)

    @classmethod
    def from_tesseract(cls, image, page_number: int) -> "SpatialWordMap":
        """
        Build SpatialWordMap from Tesseract OCR on a page image.
        Used for scanned pages where PyMuPDF has no embedded text.
        """
        import os
        import tempfile
        import pytesseract
        # pytesseract's in-memory temp-file roundtrip is broken in this
        # environment (it reads back the input PNG and raises a
        # UnicodeDecodeError on byte 0x89). Write the image ourselves and pass
        # the path — the reliable code path. Same fix as adaptive_ocr._run_tesseract.
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            image.save(tmp)
            data = pytesseract.image_to_data(
                tmp, output_type=pytesseract.Output.DICT,
                config="--psm 6 --oem 3",
            )
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        words = []
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text or int(data["conf"][i]) < 30:
                continue
            x = float(data["left"][i])
            y = float(data["top"][i])
            w = float(data["width"][i])
            h = float(data["height"][i])
            words.append(SpatialWord(
                x0=x, y0=y, x1=x + w, y1=y + h,
                text=text,
                page_number=page_number,
            ))
        return cls(words)

    @classmethod
    def from_paddle_words(
        cls,
        paddle_words: List[Tuple[float, float, float, float, str, float]],
        page_number: int,
    ) -> "SpatialWordMap":
        """
        Build SpatialWordMap from PaddleOCR word boxes.

        PaddleOCR returns (x0, y0, x1, y1, text, confidence) already scaled to
        PDF points (72 DPI), matching from_fitz_page's coordinate space — so
        scanned and digital pages share one spatial frame. Used as the primary
        OCR for scanned pages (better than Tesseract on form layouts).
        """
        words = [
            SpatialWord(
                x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                text=text.strip(), page_number=page_number,
            )
            for (x0, y0, x1, y1, text, conf) in paddle_words
            if text and text.strip()
        ]
        return cls(words)

    # ------------------------------------------------------------------
    # Core spatial queries
    # ------------------------------------------------------------------

    def find_label(
        self, synonyms: List[str], known_labels: FrozenSet[str]
    ) -> Optional[Tuple[float, float, float, float, str]]:
        """
        Find any word/phrase that matches a known label synonym.
        Returns (x0, y0, x1, y1, matched_label_text) of the rightmost word of the label.

        Handles multi-word labels: "Project Name" = two consecutive words on same row.
        """
        for syn in synonyms:
            syn_words = syn.strip().split()
            if not syn_words:
                continue

            if len(syn_words) == 1:
                # Single-word label
                word = syn_words[0].lower()
                for sw in self._words:
                    if sw.text.lower().rstrip(":/.,") == word:
                        return sw.x0, sw.y0, sw.x1, sw.y1, sw.text
            else:
                # Multi-word label — find first word then check consecutive words on same row
                first = syn_words[0].lower()
                candidates = [sw for sw in self._words if sw.text.lower().rstrip(":/.,") == first]
                for candidate in candidates:
                    matched = self._match_phrase_from(candidate, syn_words)
                    if matched:
                        # Return bbox spanning the whole phrase
                        last = matched[-1]
                        return candidate.x0, candidate.y0, last.x1, last.y1, " ".join(sw.text for sw in matched)
        return None

    def _match_phrase_from(
        self, first_word: SpatialWord, phrase_words: List[str]
    ) -> Optional[List[SpatialWord]]:
        """Check if phrase_words follow first_word on the same row."""
        if not phrase_words:
            return None
        if first_word.text.lower().rstrip(":/.,") != phrase_words[0].lower():
            return None

        result = [first_word]
        for next_label_word in phrase_words[1:]:
            # Look for the next word: same Y row, immediately to the right
            candidates = [
                sw for sw in self._words
                if sw.x0 > result[-1].x1
                and abs(sw.y_center - first_word.y_center) < Y_ROW_TOLERANCE
                and sw.x0 - result[-1].x1 < 40  # gap < 40px
            ]
            candidates.sort(key=lambda sw: sw.x0)
            if not candidates or candidates[0].text.lower().rstrip(":/.,") != next_label_word.lower():
                return None
            result.append(candidates[0])
        return result

    def value_words_right_of(
        self, label_x1: float, label_y0: float, label_y1: float,
        known_labels: FrozenSet[str],
    ) -> List[SpatialWord]:
        """
        Collect value words on the SAME ROW to the right of the label.

        Stops when:
        - Gap > 120px (crossed into a separate column)
        - Next word is a known label AND has length >= 3 (short words like "St", "$",
          "NE" are part of address/value content, not standalone labels)
        """
        row_y_center = (label_y0 + label_y1) / 2
        row_tolerance = max(Y_ROW_TOLERANCE, (label_y1 - label_y0) * 0.6)

        candidates = [
            sw for sw in self._words
            if sw.x0 > label_x1
            and sw.x0 < label_x1 + X_RIGHT_MAX
            and abs(sw.y_center - row_y_center) <= row_tolerance
            and len(sw.text) >= MIN_VALUE_LENGTH
        ]
        candidates.sort(key=lambda sw: sw.x0)

        result = []
        prev_x1 = label_x1
        for sw in candidates:
            if sw.x0 - prev_x1 > 120:
                break
            # Only stop on known labels that are at least 3 chars long.
            # Short words ("St", "$", "NE", "E", "W") are part of values.
            text_norm = sw.text.lower().rstrip(":/.,")
            if len(text_norm) >= 3 and text_norm in known_labels:
                break
            result.append(sw)
            prev_x1 = sw.x1
        return result

    def enum_proximity_search(
        self, label_x0: float, label_y0: float, label_y1: float,
        allowed_values: List[str], search_radius_x: float = 400.0,
    ) -> Optional[str]:
        """
        For checkbox / enum fields: scan the row for any of the allowed values.
        This handles UAD form layouts where all options appear on the same row
        as the label: "Fee Simple [ ] Leasehold [ ] Other"

        Checks for a checked marker (X, x, ✓) BEFORE the matching word, OR
        uses the first allowed value that appears in the row.
        """
        row_y_center = (label_y0 + label_y1) / 2
        tolerance = max(Y_ROW_TOLERANCE, (label_y1 - label_y0) * 0.7)

        # Gather all words in this row region
        row_words = sorted([
            sw for sw in self._words
            if abs(sw.y_center - row_y_center) <= tolerance
            and sw.x0 >= label_x0 - 10
            and sw.x0 <= label_x0 + search_radius_x
        ], key=lambda sw: sw.x0)

        row_text = " ".join(sw.text for sw in row_words).lower()

        # Check for markers near each allowed value
        check_markers = {"x", "✓", "☑", "✗", "[x]", "(x)"}
        words_lower = [sw.text.lower() for sw in row_words]

        for av in allowed_values:
            av_words = av.lower().split()
            # Find where this value appears in the row
            for i in range(len(words_lower) - len(av_words) + 1):
                if words_lower[i:i+len(av_words)] == av_words:
                    # Check if there's a marker right before this value (within 3 words)
                    preceding = words_lower[max(0, i-3):i]
                    if any(m in preceding for m in check_markers):
                        return av
                    # For the form, checkboxes are often inline — return if it's the only option
                    # or if it appears at the start of the value section
                    if i == 0 or (i > 0 and words_lower[i-1] in {"simple", "fee"} and av == "Fee Simple"):
                        pass  # Don't auto-select without a marker

        # Fallback: if exactly one value appears in the text (unambiguous), return it
        found_values = [av for av in allowed_values if av.lower() in row_text]
        if len(found_values) == 1:
            return found_values[0]

        return None

    def value_words_below(
        self, label_x0: float, label_x1: float, label_y1: float,
        known_labels: FrozenSet[str],
    ) -> List[SpatialWord]:
        """
        Collect value words BELOW the label (within Y_BELOW_MAX pixels),
        in the same horizontal column range.
        """
        below_words = [
            sw for sw in self._words
            if sw.y0 > label_y1
            and sw.y0 < label_y1 + Y_BELOW_MAX
            and sw.x1 > label_x0 - 10
            and sw.x0 < label_x1 + 10
        ]
        below_words.sort(key=lambda sw: sw.x0)

        result = []
        for sw in below_words:
            if sw.text.lower().rstrip(":/.,") in known_labels:
                break
            result.append(sw)
        return result

    def reconstruct_address_block(self, start_y: float, page_width: float) -> Dict[str, str]:
        """
        Extract a full address block starting at start_y.
        Used for multi-field address extraction: street, city, state, zip.
        """
        # Find words in the address row (±10px of start_y)
        addr_words = [
            sw for sw in self._words
            if abs(sw.y_center - start_y) < 10
        ]
        addr_words.sort(key=lambda sw: sw.x0)
        return {"raw": " ".join(sw.text for sw in addr_words)}

    def all_words_as_text(self) -> str:
        """Return all words sorted by reading order (Y then X)."""
        sorted_words = sorted(self._words, key=lambda w: (round(w.y_center / 5) * 5, w.x0))
        return " ".join(sw.text for sw in sorted_words)

    def words_in_row(self, y_center: float, tolerance: float = Y_ROW_TOLERANCE) -> List[SpatialWord]:
        """Get all words on a given horizontal row."""
        return sorted(
            [sw for sw in self._words if abs(sw.y_center - y_center) <= tolerance],
            key=lambda sw: sw.x0,
        )

    def locate_value(
        self, value: str, *, row_tolerance: float = Y_ROW_TOLERANCE
    ) -> List[Tuple[float, float, float, float]]:
        """Find every place an already-extracted VALUE appears, as the bounding
        box (x0, y0, x1, y1) of the contiguous run of words that spells it on one
        horizontal row.

        This is the inverse of find_label: the value is known (the extractor
        already produced it) and we want *where it sits* so the reviewer can be
        scrolled to it. Matching is done on a punctuation/space-insensitive
        normalized form, so "1,450" matches the word "1,450" and "123 Main St"
        matches the three words "123" "Main" "St".

        Returns one box per distinct row match (callers use the count to decide
        whether a match is unambiguous). Empty when the value is not on the page
        — e.g. a scanned page with no text layer yields no words here.
        """
        target = _normalize_for_match(value)
        if not target:
            return []

        # Group words into rows by quantized y-center, each sorted left→right.
        rows: Dict[int, List[SpatialWord]] = {}
        for sw in self._words:
            rows.setdefault(round(sw.y_center / row_tolerance), []).append(sw)

        matches: List[Tuple[float, float, float, float]] = []
        for row_words in rows.values():
            row_words.sort(key=lambda sw: sw.x0)
            n = len(row_words)
            for i in range(n):
                acc = ""
                for j in range(i, n):
                    acc += _normalize_for_match(row_words[j].text)
                    if len(acc) > len(target):
                        break
                    if acc == target:
                        span = row_words[i : j + 1]
                        matches.append((
                            min(w.x0 for w in span), min(w.y0 for w in span),
                            max(w.x1 for w in span), max(w.y1 for w in span),
                        ))
                        break  # shortest span from this start wins
        return matches

    def __len__(self) -> int:
        return len(self._words)


def extract_field_spatially(
    word_map: SpatialWordMap,
    synonyms: List[str],
    known_labels: FrozenSet[str],
    fallback_patterns: Optional[List[str]] = None,
) -> Optional[Tuple[str, str, Tuple[float, float, float, float]]]:
    """
    Extract a field value using spatial proximity.

    Returns (value_text, method, (x0, y0, x1, y1)) or None.

    method values:
      "spatial_right_of_label"   — value found to the right of label on same row
      "spatial_below_label"      — value found below the label
      "spatial_pattern_fallback" — found via regex pattern when spatial fails
    """
    label_bbox = word_map.find_label(synonyms, known_labels)
    if not label_bbox:
        return None

    lx0, ly0, lx1, ly1, label_matched = label_bbox

    # Strategy 1: value to the right on same row
    right_words = word_map.value_words_right_of(lx1, ly0, ly1, known_labels)
    if right_words:
        value = " ".join(w.text for w in right_words).strip()
        if value:
            bbox = (right_words[0].x0, right_words[0].y0,
                    right_words[-1].x1, right_words[-1].y1)
            return value, "spatial_right_of_label", bbox

    # Strategy 2: value below the label
    below_words = word_map.value_words_below(lx0, lx1, ly1, known_labels)
    if below_words:
        value = " ".join(w.text for w in below_words).strip()
        if value:
            bbox = (below_words[0].x0, below_words[0].y0,
                    below_words[-1].x1, below_words[-1].y1)
            return value, "spatial_below_label", bbox

    return None


def build_known_label_set(schema) -> FrozenSet[str]:
    """
    Build the set of all known label words (lowercase) for collision detection.

    Rules:
    - Only add words with 3+ characters (single letters and 2-char words like
      "St", "NE", "of" are part of address values, not standalone labels)
    - Never add pure-numeric words ("12", "2", "4") — they are values, not labels
    - Never add single characters or punctuation
    """
    labels: set = set()
    for fd in schema.all_fields():
        for syn in fd.synonyms:
            for word in syn.lower().split():
                stripped = word.rstrip(":/.,()#$%")
                # Skip pure numerics, very short words, and single chars
                if stripped.isdigit():
                    continue
                if len(stripped) < 3:
                    continue
                labels.add(stripped)
    return frozenset(labels)
