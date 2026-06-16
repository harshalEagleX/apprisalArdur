"""
Pattern Extractor — baseline synonym-label + data-pattern extraction.

The baseline extraction tier: synonym label matching + data-pattern extraction.
Every function returns ExtractionResult — never a raw string.

Architecture contract (CLAUDE.md P-3, one-sentence rule):
  This module extracts values from text. It does NOT validate, does NOT route,
  does NOT persist, does NOT know about rules.

Key principles enforced here:
  Rule 1: LLM never used for structured field extraction.
  Rule 2: Checkboxes use three-state logic (True / False / None=VERIFY).
  Rule 3: Every result has confidence, source_page, extraction_method, raw_source_text.
  Rule 5: Address parsing anchored on DATA patterns (5-digit zip), not label words.

Critical UAD 1004 insight (discovered Day 2):
  On UAD 1004 appraisal reports, data values are output by PDF software BEFORE
  their corresponding form labels in the text stream. Label-then-value extraction
  therefore captures the NEXT label as the value.

  Fix applied: _KNOWN_LABELS set — if extracted text is itself a known form label,
  reject it and return NOT_FOUND. This turns silent wrong answers into honest
  NOT_FOUND results.

  Week 2 (Day 9) will add a UAD structural parser that extracts the pre-label
  data section in correct positional order.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, FrozenSet, List, Optional, Tuple

from app.core.result import ExtractionMethod, ExtractionResult, ExtractionResultSet
from app.core.schema import FieldDefinition, schema_loader
from app.ocr.document import LoadedDocument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label collision guard — built once from the schema at import time
# ---------------------------------------------------------------------------

def _build_known_labels() -> FrozenSet[str]:
    """
    Build the set of all known field labels (lowercase) from the schema.
    Used to detect when a regex match has captured a form label instead of a value.
    """
    labels: set = set()
    for fd in schema_loader.all_fields():
        for syn in fd.synonyms:
            labels.add(syn.strip().lower())
    return frozenset(labels)


_KNOWN_LABELS: FrozenSet[str] = _build_known_labels()


def _is_known_label(text: str) -> bool:
    """
    True when the captured text IS a known form field label — meaning the extractor
    grabbed the next label rather than a real value. Reject these results.
    """
    t = text.strip().lower().rstrip(":.,;")
    return t in _KNOWN_LABELS or len(t) <= 1


# ---------------------------------------------------------------------------
# Label-based search helpers
# ---------------------------------------------------------------------------

def _label_search(text: str, labels: List[str], value_pattern: str,
                  flags: int = re.IGNORECASE) -> Optional[Tuple[str, str, int, str]]:
    """
    Try each label in order. Return (raw_value, source_snippet, char_pos, method) or None.

    method:
      EXACT_LABEL_MATCH — first label in the list matched (most authoritative)
      SYNONYM_MATCH     — any other label matched
    """
    for idx, label in enumerate(labels):
        escaped = re.escape(label)
        # Require a separator or whitespace after the label to reduce false matches
        pattern = rf"(?:{escaped})\s*[:\-/]?\s*({value_pattern})"
        m = re.search(pattern, text, flags)
        if m:
            raw = m.group(1).strip()
            snippet = text[max(0, m.start() - 20): m.end() + 40].replace("\n", " ")
            method = ExtractionMethod.EXACT_LABEL_MATCH if idx == 0 else ExtractionMethod.SYNONYM_MATCH
            return raw, snippet, m.start(), method
    return None


def _label_search_next_line(text: str, labels: List[str]) -> Optional[Tuple[str, str, int, str]]:
    """
    Find a label then grab the NEXT non-empty line as the value.
    More robust for engagement letters where label and value are on separate lines.
    """
    for idx, label in enumerate(labels):
        escaped = re.escape(label)
        # Label at line start or after newline, value on next line
        pattern = rf"(?:^|\n)[ \t]*(?:{escaped})[ \t]*:?[ \t]*\n([ \t]*\S[^\n]{{0,80}})"
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            raw = m.group(1).strip()
            snippet = text[max(0, m.start() - 5): m.end() + 30].replace("\n", " ")
            method = ExtractionMethod.EXACT_LABEL_MATCH if idx == 0 else ExtractionMethod.SYNONYM_MATCH
            return raw, snippet, m.start(), method
    return None


# ---------------------------------------------------------------------------
# Data-pattern extractors (not label-dependent)
# ---------------------------------------------------------------------------

_RE_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_RE_STATE_BEFORE_ZIP = re.compile(r"\b([A-Z]{2})\s+\d{5}\b")
_RE_CURRENCY_WITH_SIGN = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_RE_DATE_MDY = re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b")
_RE_DATE_WRITTEN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
)
_RE_YEAR_4 = re.compile(r"\b((?:19|20)\d{2})\b")
_RE_UAD_C = re.compile(r"\bC([1-6])\b")
_RE_UAD_Q = re.compile(r"\bQ([1-6])\b")

# Appraised value: SCA indicated value and final opinion appear as identical pair
# then followed by Cost Approach value then Income Approach (often 0)
# Pattern: value\nvalue\ncost_approach\n0\n (or value\nvalue\nnon_zero\n0\n)
_RE_APPRAISED_VALUE = re.compile(r"\n([\d,]{5,})\n\1\n[\d,]+\n0\n")

# Effective date: date just before an appraiser license number (alphanumeric 6-10 chars)
_RE_EFFECTIVE_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})\n([A-Z]{2}\d{4,8})\n")

# Standalone currency on its own line (for signature page appraised value fallback)
_RE_STANDALONE_CURRENCY = re.compile(r"\n([\d,]{5,})\n")

# AppraiserLicense pattern to identify signature page
_RE_LICENSE_LINE = re.compile(r"\n([A-Z]{2}\d{4,8})\n([A-Z]{2})\n(\d{2}/\d{2}/\d{4})\n")


def _extract_zip(text: str) -> Optional[Tuple[str, str, int]]:
    m = _RE_ZIP.search(text)
    if m:
        snippet = text[max(0, m.start() - 30): m.end() + 10].replace("\n", " ")
        return m.group(1), snippet, m.start()
    return None


def _extract_state(text: str) -> Optional[Tuple[str, str, int]]:
    m = _RE_STATE_BEFORE_ZIP.search(text)
    if m:
        snippet = text[max(0, m.start() - 10): m.end() + 10].replace("\n", " ")
        return m.group(1), snippet, m.start()
    return None


def _normalize_currency(raw: str) -> Optional[str]:
    clean = re.sub(r"[$,\s]", "", raw)
    try:
        v = float(clean)
        return str(round(v, 2)) if "." in clean else str(int(v))
    except ValueError:
        return None


def _normalize_date(raw: str) -> Optional[str]:
    import datetime
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = _RE_DATE_WRITTEN.match(raw.strip())
    if m:
        try:
            return datetime.datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Checkbox detection — three-state (True / False / None)
# ---------------------------------------------------------------------------

_CHECKED_MARKERS = {"x", "✓", "☑", "✗", "[x]", "(x)", "yes", "y"}
_UNCHECKED_MARKERS = {"☐", "[ ]", "( )", "no", "n"}


def _checkbox_search(text: str, labels: List[str]) -> Optional[Tuple[Optional[bool], str, int, str]]:
    """
    Return (state, snippet, pos, method) or None if label not found.
    state = True / False / None(VERIFY — label found but state indeterminate)
    Returns None (outer None) when label is not found at all.
    """
    for idx, label in enumerate(labels):
        escaped = re.escape(label)
        m = re.search(rf"(.{{0,30}})(?:{escaped})(.{{0,30}})", text, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        context = (m.group(1) + m.group(2)).lower().strip()
        snippet = text[max(0, m.start() - 5): m.end() + 30].replace("\n", " ")
        pos = m.start()
        method = ExtractionMethod.EXACT_LABEL_MATCH if idx == 0 else ExtractionMethod.SYNONYM_MATCH
        for marker in _CHECKED_MARKERS:
            if marker in context:
                return True, snippet, pos, method
        for marker in _UNCHECKED_MARKERS:
            if marker in context:
                return False, snippet, pos, method
        return None, snippet, pos, method  # label found, state indeterminate
    return None  # label not found


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class PatternExtractor:
    """
    Day 2 baseline extractor.

    Extraction hierarchy:
    1. Data-pattern (zip, state, appraised_value, effective_date) — no label dependency
    2. Label + next-line search — for engagement letter style documents
    3. Label + same-line search — for inline label:value formats
    4. Enum search — find allowed values near label
    5. Checkbox — three-state logic

    Returns ExtractionResult for every field. Never returns raw strings.
    """

    def __init__(self) -> None:
        self._schema = schema_loader

    def extract(self, doc: LoadedDocument, document_type: str) -> ExtractionResultSet:
        result_set = ExtractionResultSet(
            document_path=doc.path,
            document_type=document_type,
            total_pages=doc.total_pages,
            ocr_method="pymupdf",
        )

        full_text = doc.full_text
        page_index = doc.page_index

        for field_def in self._schema.all_fields():
            try:
                result = self._extract_field(field_def, full_text, page_index, document_type)
                result_set.add(result)
            except Exception as exc:
                logger.error("Extraction error for '%s': %s", field_def.canonical_name, exc)
                result_set.add(ExtractionResult(
                    canonical_name=field_def.canonical_name,
                    document_type=document_type,
                    extraction_method=ExtractionMethod.NOT_FOUND,
                    confidence=0.0,
                    sanity_check_reason="extraction_exception",
                ))

        result_set.finalize()
        found = len(result_set.found_results())
        logger.info(
            "Tier3 done: %s | %d/%d fields found | %dms",
            document_type, found, len(result_set), result_set.extraction_time_ms,
        )
        return result_set

    # ------------------------------------------------------------------
    # Per-field dispatch
    # ------------------------------------------------------------------

    def _extract_field(
        self,
        fd: FieldDefinition,
        full_text: str,
        page_index: Dict[int, str],
        document_type: str,
    ) -> ExtractionResult:
        name = fd.canonical_name

        # Structural / data-pattern fields — never depend on label wording
        if name == "zip_code":
            return self._by_zip_pattern(fd, full_text, page_index, document_type)
        if name == "state":
            return self._by_state_pattern(fd, full_text, page_index, document_type)
        if name == "appraised_value":
            return self._by_appraised_value(fd, full_text, page_index, document_type)
        if name == "effective_date":
            return self._by_effective_date(fd, full_text, page_index, document_type)

        # Boolean / checkbox
        if fd.data_type == "boolean":
            return self._by_checkbox(fd, full_text, page_index, document_type)

        # UAD codes
        if fd.data_type in ("uad_condition", "uad_quality"):
            return self._by_uad_code(fd, full_text, page_index, document_type)

        # Currency
        if fd.data_type == "currency":
            return self._by_currency(fd, full_text, page_index, document_type)

        # Date
        if fd.data_type == "date":
            return self._by_date(fd, full_text, page_index, document_type)

        # Year
        if fd.data_type == "year":
            return self._by_year(fd, full_text, page_index, document_type)

        # Numeric
        if fd.data_type in ("integer", "numeric", "percent"):
            return self._by_numeric(fd, full_text, page_index, document_type)

        # Enum
        if fd.data_type == "enum":
            return self._by_enum(fd, full_text, page_index, document_type)

        # Default: string — try next-line first (more reliable), then inline
        return self._by_string(fd, full_text, page_index, document_type)

    # ------------------------------------------------------------------
    # Data-pattern strategies
    # ------------------------------------------------------------------

    def _by_zip_pattern(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _extract_zip(text)
        if hit:
            val, snippet, pos = hit
            return ExtractionResult(
                canonical_name=fd.canonical_name, document_type=dt,
                value=val, raw_source_text=snippet,
                extraction_method=ExtractionMethod.DATA_PATTERN_ONLY,
                confidence=self._schema.method_confidence(ExtractionMethod.DATA_PATTERN_ONLY),
                source_page=self._page_of(pos, text, pi),
                char_start=pos,
                normalization_applied=["digits_only_first5"],
            )
        return self._not_found(fd, dt)

    def _by_state_pattern(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _extract_state(text)
        if hit:
            val, snippet, pos = hit
            return ExtractionResult(
                canonical_name=fd.canonical_name, document_type=dt,
                value=val.upper(), raw_source_text=snippet,
                extraction_method=ExtractionMethod.DATA_PATTERN_ONLY,
                confidence=self._schema.method_confidence(ExtractionMethod.DATA_PATTERN_ONLY),
                source_page=self._page_of(pos, text, pi),
                char_start=pos,
                normalization_applied=["uppercase_strip"],
            )
        return self._not_found(fd, dt)

    def _by_appraised_value(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        """
        Two strategies:
        A) On reconciliation page: look for two identical dollar amounts on consecutive lines.
           This is the pattern where the form has "Indicated Value by SCA" and "Final Opinion"
           both showing the same number.
        B) On signature page: standalone dollar amount after address+zip block near appraiser license.
        """
        # Strategy A: two identical amounts in sequence
        m = _RE_APPRAISED_VALUE.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                val = float(raw)
                if 10000 < val < 100_000_000:
                    pos = m.start()
                    snippet = text[max(0, pos - 30): m.end() + 30].replace("\n", " ")
                    norm = str(int(val)) if val == int(val) else str(val)
                    return ExtractionResult(
                        canonical_name=fd.canonical_name, document_type=dt,
                        value=norm, raw_source_text=snippet,
                        extraction_method=ExtractionMethod.POSITIONAL_ANCHOR,
                        confidence=0.88,
                        source_page=self._page_of(pos, text, pi),
                        char_start=pos,
                        normalization_applied=["strip_commas_then_float"],
                    )
            except ValueError:
                pass

        # Strategy B: label-based (reconciliation label synonyms)
        hit = _label_search(text, fd.synonyms, r"\$?\s*[\d,]{4,}(?:\.\d{1,2})?")
        if hit:
            raw, snippet, pos, method = hit
            norm = _normalize_currency(raw)
            if norm:
                try:
                    v = float(norm)
                    if 10000 < v < 100_000_000:
                        return ExtractionResult(
                            canonical_name=fd.canonical_name, document_type=dt,
                            value=norm, raw_source_text=snippet,
                            extraction_method=method,
                            confidence=self._schema.method_confidence(method),
                            source_page=self._page_of(pos, text, pi),
                            char_start=pos,
                            normalization_applied=["strip_currency_symbols_commas_then_float"],
                        )
                except ValueError:
                    pass

        return self._not_found(fd, dt)

    def _by_effective_date(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        """
        Two strategies:
        A) On signature page: date just BEFORE an appraiser license number.
           Pattern: date\nLicenseNum\nState\nExpiration
        B) Label-based search on any page.
        """
        # Strategy A: date before license number (signature page structural pattern)
        m = _RE_EFFECTIVE_DATE.search(text)
        if m:
            raw_date = m.group(1)
            norm = _normalize_date(raw_date)
            if norm:
                pos = m.start()
                snippet = text[max(0, pos - 20): m.end() + 10].replace("\n", " ")
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=norm, raw_source_text=snippet,
                    extraction_method=ExtractionMethod.POSITIONAL_ANCHOR,
                    confidence=0.85,
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["parse_date_to_iso8601"],
                )

        # Strategy B: label-based
        hit = _label_search(text, fd.synonyms, r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}")
        if hit:
            raw, snippet, pos, method = hit
            norm = _normalize_date(raw)
            if norm:
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=norm, raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["parse_date_to_iso8601"],
                )

        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Checkbox
    # ------------------------------------------------------------------

    def _by_checkbox(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _checkbox_search(text, fd.synonyms)
        if hit is None:
            return self._not_found(fd, dt)
        state, snippet, pos, method = hit
        value = str(state) if state is not None else None
        conf = self._schema.method_confidence(method)
        if state is None:
            conf = max(0.0, conf - 0.15)
        return ExtractionResult(
            canonical_name=fd.canonical_name, document_type=dt,
            value=value, raw_source_text=snippet,
            extraction_method=method,
            confidence=conf,
            source_page=self._page_of(pos, text, pi),
            char_start=pos,
            normalization_applied=["checkbox_to_three_state"],
        )

    # ------------------------------------------------------------------
    # UAD code
    # ------------------------------------------------------------------

    def _by_uad_code(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        prefix = "C" if fd.data_type == "uad_condition" else "Q"
        pattern = _RE_UAD_C if prefix == "C" else _RE_UAD_Q

        # Try label-anchored first
        hit = _label_search(text, fd.synonyms, rf"{prefix}[1-6]")
        if hit:
            raw, snippet, pos, method = hit
            val = raw.upper()
            if _is_known_label(val):
                return self._not_found(fd, dt)
            return ExtractionResult(
                canonical_name=fd.canonical_name, document_type=dt,
                value=val, raw_source_text=snippet,
                extraction_method=method,
                confidence=self._schema.method_confidence(method),
                source_page=self._page_of(pos, text, pi),
                char_start=pos,
                normalization_applied=["extract_uad_code"],
            )

        # Fallback: first UAD code in text (lower confidence, may be wrong)
        m = pattern.search(text)
        if m:
            val = f"{prefix}{m.group(1)}"
            pos = m.start()
            snippet = text[max(0, pos - 20): m.end() + 20].replace("\n", " ")
            return ExtractionResult(
                canonical_name=fd.canonical_name, document_type=dt,
                value=val, raw_source_text=snippet,
                extraction_method=ExtractionMethod.DATA_PATTERN_ONLY,
                confidence=0.55,
                source_page=self._page_of(pos, text, pi),
                char_start=pos,
                normalization_applied=["extract_uad_code"],
            )
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Currency
    # ------------------------------------------------------------------

    def _by_currency(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _label_search(text, fd.synonyms, r"\$?\s*[\d,]+(?:\.\d{1,2})?")
        if hit:
            raw, snippet, pos, method = hit
            if _is_known_label(raw):
                return self._not_found(fd, dt)
            norm = _normalize_currency(raw)
            if norm:
                try:
                    v = float(norm)
                    vr = fd.value_range
                    if vr and not (vr.get("min", 0) <= v <= vr.get("max", 1e9)):
                        return self._not_found(fd, dt)
                except ValueError:
                    return self._not_found(fd, dt)
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=norm, raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["strip_currency_symbols_commas_then_float"],
                )
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Date
    # ------------------------------------------------------------------

    def _by_date(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _label_search(text, fd.synonyms, r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}")
        if hit:
            raw, snippet, pos, method = hit
            if _is_known_label(raw):
                return self._not_found(fd, dt)
            norm = _normalize_date(raw)
            if norm:
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=norm, raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["parse_date_to_iso8601"],
                )
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Year
    # ------------------------------------------------------------------

    def _by_year(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _label_search(text, fd.synonyms, r"(?:19|20)\d{2}")
        if hit:
            raw, snippet, pos, method = hit
            if _is_known_label(raw):
                return self._not_found(fd, dt)
            try:
                year = int(raw)
                vr = fd.value_range
                if vr and not (vr.get("min", 1800) <= year <= vr.get("max", 2030)):
                    return self._not_found(fd, dt)
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=str(year), raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["extract_4digit_year"],
                )
            except ValueError:
                pass
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Numeric
    # ------------------------------------------------------------------

    def _by_numeric(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        hit = _label_search(text, fd.synonyms, r"[\d,]+(?:\.\d+)?%?")
        if hit:
            raw, snippet, pos, method = hit
            if _is_known_label(raw):
                return self._not_found(fd, dt)
            clean = re.sub(r"[,%\s]", "", raw)
            try:
                val = float(clean)
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=str(int(val)) if fd.data_type == "integer" else str(val),
                    raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["strip_non_digits_then_float"],
                )
            except ValueError:
                pass
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Enum
    # ------------------------------------------------------------------

    def _by_enum(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        if not fd.allowed_values:
            return self._by_string(fd, text, pi, dt)

        for label in fd.synonyms:
            escaped_label = re.escape(label)
            region_m = re.search(
                rf"(?:{escaped_label}).{{0,300}}", text, re.IGNORECASE | re.DOTALL
            )
            if not region_m:
                continue
            region = region_m.group(0)
            for av in fd.allowed_values:
                if re.search(re.escape(av), region, re.IGNORECASE):
                    pos = region_m.start()
                    snippet = region[:80].replace("\n", " ")
                    method = ExtractionMethod.EXACT_LABEL_MATCH if label == fd.synonyms[0] else ExtractionMethod.SYNONYM_MATCH
                    return ExtractionResult(
                        canonical_name=fd.canonical_name, document_type=dt,
                        value=av, raw_source_text=snippet,
                        extraction_method=method,
                        confidence=self._schema.method_confidence(method),
                        source_page=self._page_of(pos, text, pi),
                        char_start=pos,
                    )
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # String — with label collision guard
    # ------------------------------------------------------------------

    def _by_string(self, fd: FieldDefinition, text: str, pi: Dict, dt: str) -> ExtractionResult:
        """
        Two-pass string extraction:
        Pass 1 — next-line search (label on one line, value on next). More reliable
                  for engagement letters and cover-letter style formats.
        Pass 2 — inline search (label: value on same line). Fallback.

        Label collision guard: if extracted value is a known form label → reject.
        """
        # Pass 1: next-line
        hit = _label_search_next_line(text, fd.synonyms)
        if hit:
            raw, snippet, pos, method = hit
            val = raw.strip().rstrip(".,;:")
            if val and len(val) > 1 and not _is_known_label(val):
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=val, raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method),
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["strip_whitespace"],
                )

        # Pass 2: inline (label: value)
        hit = _label_search(text, fd.synonyms, r"[^\n]{1,80}")
        if hit:
            raw, snippet, pos, method = hit
            val = raw.strip().rstrip(".,;:")
            if val and len(val) > 1 and not _is_known_label(val):
                return ExtractionResult(
                    canonical_name=fd.canonical_name, document_type=dt,
                    value=val, raw_source_text=snippet,
                    extraction_method=method,
                    confidence=self._schema.method_confidence(method) * 0.85,  # slight penalty for inline
                    source_page=self._page_of(pos, text, pi),
                    char_start=pos,
                    normalization_applied=["strip_whitespace"],
                )

        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _not_found(fd: FieldDefinition, dt: str) -> ExtractionResult:
        return ExtractionResult(
            canonical_name=fd.canonical_name,
            document_type=dt,
            extraction_method=ExtractionMethod.NOT_FOUND,
            confidence=0.0,
        )

    @staticmethod
    def _page_of(char_pos: int, full_text: str, page_index: Dict[int, str]) -> int:
        """Map a character offset in full_text back to the page number it came from."""
        cumulative = 0
        for page_num in sorted(page_index.keys()):
            page_len = len(page_index[page_num]) + 2  # +2 for '\n\n' separator
            if cumulative + page_len > char_pos:
                return page_num
            cumulative += page_len
        return max(page_index.keys()) if page_index else 1
