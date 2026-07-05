"""
Day 8 — Text Normalization Pipeline

Seven independent, composable transformations applied in sequence.
Each transform: text in → text out. Each records what it changed.

Independence is the key architectural property: transforms can be added,
removed, or reordered without affecting the others. No transform knows
about another.

Transformations (in order):
  1. whitespace_normalize     — collapse whitespace, normalize line endings
  2. ocr_char_confusion       — fix appraisal-specific OCR misreads
  3. special_char_normalize   — typographic → plain ASCII equivalents
  4. currency_normalize       — consistent currency format $X,XXX.XX
  5. date_normalize           — consistent date format (stored internally as-is; extraction parses)
  6. numeric_normalize        — percentages, measurements, area units
  7. appraisal_term_normalize — domain-specific abbreviation expansion

OCR character confusion table built from errors observed in our Day 4 test set:
  - Equity Solutions docs: "$0" sometimes appears as "S0"
  - Henderson docs: "l" / "1" confusion in parcel numbers
  - Currency: "263.000" vs "263,000" (period vs comma in amounts)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Transform result
# ---------------------------------------------------------------------------

@dataclass
class TransformEvent:
    """Records what a single transform changed."""
    transform: str
    before: str        # original substring
    after: str         # replacement
    position: int      # character offset in the text before this transform ran


@dataclass
class NormalizationResult:
    """Output of running the full normalization pipeline."""
    original: str
    normalized: str
    events: List[TransformEvent] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original != self.normalized

    def to_log_entry(self) -> dict:
        return {
            "changed": self.changed,
            "events": [
                {"t": e.transform, "b": e.before[:80], "a": e.after[:80], "pos": e.position}
                for e in self.events
            ],
        }


# ---------------------------------------------------------------------------
# Transform 1 — Whitespace normalization
# ---------------------------------------------------------------------------

def whitespace_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """
    Collapse multi-space sequences, normalize tabs, normalize line endings.
    Preserve line break structure — field values often span lines.
    """
    events: List[TransformEvent] = []
    result = text

    # Normalize Windows line endings to Unix
    if "\r\n" in result:
        events.append(TransformEvent("whitespace_normalize", "\\r\\n", "\\n", 0))
        result = result.replace("\r\n", "\n")

    # Collapse tabs to spaces
    if "\t" in result:
        events.append(TransformEvent("whitespace_normalize", "\\t", " ", 0))
        result = result.replace("\t", " ")

    # Collapse multiple spaces within lines (preserve newlines)
    multi_space = re.compile(r" {2,}")
    found = multi_space.search(result)
    if found:
        events.append(TransformEvent("whitespace_normalize", "  ", " ", found.start()))
        result = multi_space.sub(" ", result)

    # Strip trailing spaces from each line
    stripped = "\n".join(line.rstrip() for line in result.split("\n"))
    if stripped != result:
        events.append(TransformEvent("whitespace_normalize", "<trailing space>", "", 0))
        result = stripped

    # Collapse 3+ blank lines to 2
    result2 = re.sub(r"\n{3,}", "\n\n", result)
    if result2 != result:
        events.append(TransformEvent("whitespace_normalize", "\\n\\n\\n+", "\\n\\n", 0))
        result = result2

    return result, events


# ---------------------------------------------------------------------------
# Transform 2 — OCR character confusion
# Errors observed in Day 4 test set documents (MSL, Equity Solutions batches)
# ---------------------------------------------------------------------------

# Each entry: (pattern, replacement, description)
# Ordered from most specific to least to avoid over-matching
_OCR_CONFUSION_RULES: List[Tuple[str, str, str]] = [
    # Currency: "$0" OCR'd as "S0" — seen in Equity Solutions docs
    (r"\bS(\d{3,})\b", r"$\1", "S→$ before digits"),

    # "l" confused with "1" in parcel numbers (Henderson docs show "l052 245")
    # Only apply when surrounded by digits
    (r"(\d)l(\d)", r"\g<1>1\g<2>", "l→1 between digits"),

    # "O" confused with "0" in numeric contexts (APN, census tract)
    (r"(?<=\d)O(?=\d)", "0", "O→0 between digits"),

    # Period as thousands separator (European format) → comma
    # e.g. "263.000" in a currency context
    (r"\b(\d{1,3})\.(\d{3})\b(?!\d)", r"\1,\2", "period→comma in thousands"),

    # Merged dollar sign and digit: "$263000" without comma → leave as is (handled by currency_normalize)

    # "l" confused with "I" at start of a word followed by lowercase
    (r"\bI([a-z]{2,})\b", r"l\1", "I→l at word start before lowercase"),

    # Space erroneously inserted inside parcel numbers: "m052 245" is fine, but
    # "m0 52 245" would be wrong. Keep the rule conservative.
]

_COMPILED_OCR_RULES = [
    (re.compile(pattern), replacement, desc)
    for pattern, replacement, desc in _OCR_CONFUSION_RULES
]


def ocr_char_confusion(text: str) -> Tuple[str, List[TransformEvent]]:
    """Apply observed OCR character confusion corrections for appraisal documents."""
    events: List[TransformEvent] = []
    result = text

    for pattern, replacement, desc in _COMPILED_OCR_RULES:
        new = pattern.sub(replacement, result)
        if new != result:
            m = pattern.search(result)
            if m:
                events.append(TransformEvent("ocr_char_confusion", m.group(0), desc, m.start()))
            result = new

    return result, events


# ---------------------------------------------------------------------------
# Transform 3 — Special character normalization
# ---------------------------------------------------------------------------

_SPECIAL_CHAR_MAP = {
    "‘": "'",   # left single quotation mark
    "’": "'",   # right single quotation mark
    "“": '"',   # left double quotation mark
    "”": '"',   # right double quotation mark
    "–": "-",   # en dash
    "—": "-",   # em dash
    "…": "...", # ellipsis
    " ": " ",   # non-breaking space
    "½": "1/2", # fraction one half
    "¼": "1/4", # fraction one quarter
    "¾": "3/4", # fraction three quarters
    "®": "(R)", # registered sign
    "™": "(TM)",# trade mark sign
}


def special_char_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """Convert typographic characters to plain ASCII equivalents."""
    events: List[TransformEvent] = []
    result = list(text)
    for i, ch in enumerate(result):
        if ch in _SPECIAL_CHAR_MAP:
            replacement = _SPECIAL_CHAR_MAP[ch]
            events.append(TransformEvent("special_char_normalize", ch, replacement, i))
            result[i] = replacement
    return "".join(result), events


# ---------------------------------------------------------------------------
# Transform 4 — Currency normalization
# ---------------------------------------------------------------------------

_RE_CURRENCY_LOOSE = re.compile(
    r"\$?\s*([\d,\.]+)",
    re.IGNORECASE,
)

# We only normalize obvious currency amounts (≥ 4 digits after stripping punctuation)
_RE_LARGE_NUMBER = re.compile(r"\b(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{4,}(?:\.\d{1,2})?)\b")


def currency_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """
    Normalize currency amounts to consistent format.
    Adds $ prefix, ensures commas as thousands separators.
    Only acts on standalone numeric values that look like dollar amounts.
    """
    events: List[TransformEvent] = []
    result = text

    def _normalize_amount(m: re.Match) -> str:
        raw = m.group(0)
        clean = re.sub(r"[,\s]", "", raw.lstrip("$").strip())
        if not clean.replace(".", "").isdigit():
            return raw
        try:
            val = float(clean)
        except ValueError:
            return raw
        if val < 100:  # don't normalize small numbers
            return raw
        # Format with commas
        formatted = f"{val:,.2f}".rstrip("0").rstrip(".")
        if "." not in formatted:
            formatted = f"{int(val):,}"
        normalized = f"${formatted}"
        if normalized != raw:
            events.append(TransformEvent("currency_normalize", raw, normalized, m.start()))
        return normalized

    # Only act on $ prefixed amounts to avoid false positives
    dollar_pattern = re.compile(r"\$\s*[\d,]+(?:\.\d{1,2})?")
    new_text = dollar_pattern.sub(_normalize_amount, result)
    if new_text != result:
        result = new_text

    return result, events


# ---------------------------------------------------------------------------
# Transform 5 — Date normalization
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # MM/DD/YYYY or MM-DD-YYYY
    (re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b"), "MDY_slash"),
    # Month DD, YYYY
    (re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
    ), "written"),
    # DD Mon YYYY
    (re.compile(
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b",
        re.IGNORECASE
    ), "DMY_abbr"),
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def date_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """
    Normalize date representations to MM/DD/YYYY (US standard used in appraisal forms).
    Does not parse — just ensures consistent separators and zero-padding.
    """
    events: List[TransformEvent] = []
    result = text

    # Normalize MM-DD-YYYY to MM/DD/YYYY
    def _slash_normalize(m: re.Match) -> str:
        original = m.group(0)
        if "-" in original:
            normalized = original.replace("-", "/")
            events.append(TransformEvent("date_normalize", original, normalized, m.start()))
            return normalized
        return original

    new = _DATE_PATTERNS[0][0].sub(_slash_normalize, result)
    if new != result:
        result = new

    return result, events


# ---------------------------------------------------------------------------
# Transform 6 — Numeric normalization
# ---------------------------------------------------------------------------

def numeric_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """
    Normalize percentages and area measurements.
    Percentages: ensure % sign is immediately after digits (no space).
    Area: normalize "sq ft" → "sf", "square feet" → "sf", "acres" → "ac".
    """
    events: List[TransformEvent] = []
    result = text

    # Percent: "75 %" → "75%"
    pct = re.compile(r"(\d)\s+%")
    new = pct.sub(r"\1%", result)
    if new != result:
        m = pct.search(result)
        if m:
            events.append(TransformEvent("numeric_normalize", m.group(0), m.group(0).replace(" ", ""), m.start()))
        result = new

    # Area units
    area_rules = [
        (re.compile(r"\bsquare\s+feet\b", re.IGNORECASE), "sf"),
        (re.compile(r"\bsq\.?\s*ft\.?\b", re.IGNORECASE), "sf"),
        (re.compile(r"\bacres\b", re.IGNORECASE), "ac"),
    ]
    for pattern, replacement in area_rules:
        m = pattern.search(result)
        if m:
            events.append(TransformEvent("numeric_normalize", m.group(0), replacement, m.start()))
            result = pattern.sub(replacement, result)

    return result, events


# ---------------------------------------------------------------------------
# Transform 7 — Appraisal term normalization
# Domain-specific abbreviation expansion observed in real documents
# ---------------------------------------------------------------------------

_TERM_RULES = [
    (re.compile(r"\bArms?-?Lth\b", re.IGNORECASE), "Arms-Length"),
    (re.compile(r"\bConv\b(?!\w)"), "Conventional"),
    (re.compile(r"\bArmLth\b", re.IGNORECASE), "Arms-Length"),
    (re.compile(r"\bFWA\b"), "Forced Warm Air"),
    (re.compile(r"\bCAC\b"), "Central Air Conditioning"),
    (re.compile(r"\bDT1\b"), "Detached"),
    (re.compile(r"\bN;Res;\b"), "Neutral;Residential"),
    (re.compile(r"\bRH;\b"), "Rural Housing;"),
]


def appraisal_term_normalize(text: str) -> Tuple[str, List[TransformEvent]]:
    """Expand appraisal-domain abbreviations seen in real UAD documents."""
    events: List[TransformEvent] = []
    result = text

    for pattern, replacement in _TERM_RULES:
        m = pattern.search(result)
        if m:
            events.append(TransformEvent("appraisal_term_normalize", m.group(0), replacement, m.start()))
            result = pattern.sub(replacement, result)

    return result, events


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

_PIPELINE: List[Callable] = [
    whitespace_normalize,
    ocr_char_confusion,
    special_char_normalize,
    currency_normalize,
    date_normalize,
    numeric_normalize,
    appraisal_term_normalize,
]


def normalize(text: str) -> NormalizationResult:
    """
    Run the full 7-transform pipeline on input text.
    Returns NormalizationResult with normalized text and full event log.
    """
    result = NormalizationResult(original=text, normalized=text)

    for transform_fn in _PIPELINE:
        try:
            new_text, events = transform_fn(result.normalized)
            result.normalized = new_text
            result.events.extend(events)
        except Exception as exc:
            logger.warning("Normalization transform %s failed: %s", transform_fn.__name__, exc)

    return result


import logging
logger = logging.getLogger(__name__)
