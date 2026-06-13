"""
Spatial Tier 3 Extractor

Replaces text-stream label matching with spatial proximity matching.

Key improvement: finds the label's POSITION (x, y) then collects the value
that is spatially adjacent — same row to the right, or one line below.
This correctly handles UAD forms where data values and labels share the same
Y coordinate but at different X positions.

Verified against real Form 1073 (90 NE 32nd St Unit 524, Miami FL):
  "Property Address" at y=59.0 → value "90 NE 32nd St" at y=60.4, x > label_end
  "Unit #" at y=59.0 → value "524" at y=60.4
  "HOA $" at y=119.0 → value "635" at y=120.4
  Δy ≈ 1.4 pixels — well within 6px tolerance

Architecture: this extractor runs FIRST per page on its spatial word map.
The text-stream Tier3PatternExtractor runs second as a fallback for any
fields not found spatially.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

import fitz

from app.core.result import ExtractionMethod, ExtractionResult, ExtractionResultSet
from app.core.schema import FieldDefinition, schema_loader
from app.extraction.fuzzy_match import find_best_label_match
from app.ocr.spatial_extractor import (
    SpatialWord,
    SpatialWordMap,
    build_known_label_set,
    extract_field_spatially,
)

logger = logging.getLogger(__name__)

# Extraction method identifiers
_SPATIAL_RIGHT = "spatial_right_of_label"
_SPATIAL_BELOW = "spatial_below_label"
_SPATIAL_DATA = "spatial_data_pattern"

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}

# Confidence scores for spatial methods
_CONF_SPATIAL_RIGHT = 0.88
_CONF_SPATIAL_BELOW = 0.82
_CONF_SPATIAL_DATA = 0.78

_BOX_PAD = 0.004  # fraction of page padded around a located value's box


def _normalize_spatial_box(box, word_map) -> Optional[Dict[str, float]]:
    """Normalize a spatially-found value box (x0,y0,x1,y1 PDF points) to {x,y,w,h}
    fractions (top-left origin) using the page's own size — the convention the
    reviewer PDF viewer expects. None when the box or page size is unknown (the
    field then stays page-level). This is what gives subject/site/neighborhood
    label-found values a precise highlight, not just a page scroll."""
    pw = getattr(word_map, "page_width", 0.0)
    ph = getattr(word_map, "page_height", 0.0)
    if not box or pw <= 0 or ph <= 0:
        return None
    x0, y0, x1, y1 = box
    x = min(max(x0 / pw - _BOX_PAD, 0.0), 1.0)
    y = min(max(y0 / ph - _BOX_PAD, 0.0), 1.0)
    w = min(max((x1 - x0) / pw + 2 * _BOX_PAD, 0.0), 1.0 - x)
    h = min(max((y1 - y0) / ph + 2 * _BOX_PAD, 0.0), 1.0 - y)
    if w <= 0 or h <= 0:
        return None
    return {"x": round(x, 5), "y": round(y, 5), "w": round(w, 5), "h": round(h, 5)}


class SpatialTier3Extractor:
    """
    PDF → image → spatial word map → field extraction by proximity.

    For digital pages: PyMuPDF word extraction (exact positions).
    For scanned pages: Tesseract with bounding boxes.
    Both produce the same SpatialWordMap interface.

    Use:
        extractor = SpatialTier3Extractor()
        result_set = extractor.extract(pdf_path, document_type)
    """

    def __init__(self) -> None:
        self._schema = schema_loader
        self._known_labels: FrozenSet[str] = build_known_label_set(schema_loader)

    def extract(self, pdf_path: Path, document_type: str) -> ExtractionResultSet:
        """
        Full spatial extraction pipeline:
        1. Open PDF, process each page to SpatialWordMap
        2. Run spatial field extraction across all pages
        3. Fall back to text-stream patterns for any unfound fields
        4. Return complete ExtractionResultSet
        """
        pdf_path = Path(pdf_path)
        start = time.time()

        result_set = ExtractionResultSet(
            document_path=str(pdf_path),
            document_type=document_type,
            ocr_method="spatial_pymupdf",
        )

        # Build per-page spatial word maps
        page_maps: Dict[int, SpatialWordMap] = {}
        fitz_doc = fitz.open(str(pdf_path))
        total_pages = len(fitz_doc)
        result_set.total_pages = total_pages

        for page_num in range(total_pages):
            page = fitz_doc[page_num]
            word_count = len(page.get_text("text").split())

            if word_count >= 30:
                # Digital page — use PyMuPDF exact word positions
                page_maps[page_num + 1] = SpatialWordMap.from_fitz_page(page, page_num + 1)
            else:
                # Scanned page — render to image then Tesseract
                try:
                    page_maps[page_num + 1] = self._ocr_scanned_page(page, page_num + 1)
                except Exception as exc:
                    logger.warning("Scanned page OCR failed p%d: %s", page_num + 1, exc)

        # Step 1b: Checkbox extraction from PDF drawings layer (BEFORE text-spatial)
        # This correctly detects checked checkboxes on UAD forms (TOTAL software)
        # where the check mark is a vector X in the drawings layer, not text.
        checkbox_results: Dict[str, ExtractionResult] = {}
        try:
            from app.ocr.checkbox_extractor import checkbox_extractor
            checkbox_results = checkbox_extractor.extract_document(
                pdf_path, document_type, max_pages=min(10, total_pages)
            )
        except Exception as exc:
            logger.warning("Checkbox extraction failed (non-fatal): %s", exc)

        fitz_doc.close()

        # Build full-document word map (all pages merged)
        full_map = self._merge_page_maps(page_maps)

        # Run spatial extraction for every schema field
        # Checkbox results take priority for enum/boolean fields
        spatial_results: Dict[str, ExtractionResult] = {}

        for fd in self._schema.all_fields():
            # Checkbox extraction has highest confidence for enum/boolean fields
            if fd.canonical_name in checkbox_results and checkbox_results[fd.canonical_name].found:
                result = checkbox_results[fd.canonical_name]
            else:
                result = self._extract_field(fd, page_maps, full_map, document_type, total_pages)
            spatial_results[fd.canonical_name] = result
            result_set.add(result)

        result_set.finalize()

        found = len(result_set.found_results())
        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "SpatialTier3: %s | %d/%d fields | %dms",
            pdf_path.name, found, len(result_set), elapsed,
        )
        return result_set

    def extract_page_map(self, pdf_path: Path) -> Dict[int, SpatialWordMap]:
        """Return per-page SpatialWordMaps (useful for inspection/debugging)."""
        fitz_doc = fitz.open(str(pdf_path))
        maps: Dict[int, SpatialWordMap] = {}
        for i in range(len(fitz_doc)):
            page = fitz_doc[i]
            wc = len(page.get_text("text").split())
            if wc >= 30:
                maps[i + 1] = SpatialWordMap.from_fitz_page(page, i + 1)
            else:
                try:
                    maps[i + 1] = self._ocr_scanned_page(page, i + 1)
                except Exception:
                    pass
        fitz_doc.close()
        return maps

    # ------------------------------------------------------------------
    # Per-field extraction
    # ------------------------------------------------------------------

    def _extract_field(
        self,
        fd: FieldDefinition,
        page_maps: Dict[int, SpatialWordMap],
        full_map: SpatialWordMap,
        document_type: str,
        total_pages: int = 30,
    ) -> ExtractionResult:
        """
        Try spatial extraction on each page, return first good result.
        Data-pattern fields (zip, state) use regex on full text instead.
        """
        name = fd.canonical_name

        # Data-pattern fields — try spatial label match first (the value sits
        # next to the "Zip Code"/"State" label on the URAR form), then fall back
        # to a text pattern. Spatial-first avoids grabbing the street number as
        # the zip or a stray 2-letter token as the state.
        if name == "zip_code":
            row = self._subject_address_row(page_maps)
            if row.get("zip_code"):
                return self._found(fd, document_type, row["zip_code"], row["zip_code"],
                                   _SPATIAL_RIGHT, 0.9, row.get("page", 1))
            hit = self._spatial_validated(fd, page_maps, document_type, r"^(\d{5})(?:-\d{4})?$", 1)
            return hit or self._data_pattern_zip(fd, full_map, document_type)
        if name == "state":
            row = self._subject_address_row(page_maps)
            if row.get("state"):
                return self._found(fd, document_type, row["state"], row["state"],
                                   _SPATIAL_RIGHT, 0.9, row.get("page", 1))
            hit = self._spatial_validated(fd, page_maps, document_type, r"^([A-Z]{2})$", 1,
                                          valid=_US_STATES)
            return hit or self._data_pattern_state(fd, full_map, document_type)
        if name == "appraised_value":
            return self._structural_appraised_value(fd, page_maps, document_type)
        if name in ("effective_date", "date_of_signature"):
            return self._structural_date_from_sig_page(fd, page_maps, full_map, document_type)

        # UAD codes (uad_condition, uad_quality) — look for C[1-6] / Q[1-6] pattern near label
        if fd.data_type in ("uad_condition", "uad_quality"):
            return self._extract_uad_code(fd, page_maps, document_type)

        # Enum fields: use proximity checkbox search (UAD forms put all options on same row)
        if fd.data_type == "enum" and fd.allowed_values:
            return self._extract_enum_spatial(fd, page_maps, document_type)

        # Boolean fields: look for marker near label
        if fd.data_type == "boolean":
            return self._extract_boolean_spatial(fd, page_maps, document_type)

        # Determine which pages to search for this field based on its form section.
        # Searching all pages creates false positives from boilerplate certification text.
        page_range = self._page_range_for_field(fd, total_pages)

        # Spatial extraction — take the FIRST valid hit in page order.
        # "Longest value = best" is wrong: narrative text is long but usually wrong.
        # Simple values (a number, a name) are right. Take the first clean match.
        for page_num, word_map in sorted(page_maps.items()):
            if page_num not in page_range:
                continue

            hit = extract_field_spatially(word_map, fd.synonyms, self._known_labels)
            if not hit:
                continue

            raw_value, method, value_box = hit
            normalized = self._normalize(raw_value, fd)
            if not normalized or len(normalized.strip()) < 1:
                continue
            if self._is_known_label_text(normalized):
                continue

            # Type-specific normalization and range validation
            if fd.data_type == "currency":
                norm = self._try_currency(raw_value)
                if norm is None:
                    continue
                # Range check
                vr = fd.value_range
                if vr:
                    try:
                        v = float(norm)
                        if not (vr.get("min", 0) <= v <= vr.get("max", 1e12)):
                            continue
                    except ValueError:
                        continue
                normalized = norm

            elif fd.data_type in ("integer", "numeric"):
                norm = self._try_numeric(raw_value)
                if norm is None:
                    continue
                vr = fd.value_range
                if vr:
                    try:
                        v = float(norm)
                        if not (vr.get("min", -1e9) <= v <= vr.get("max", 1e9)):
                            continue
                    except ValueError:
                        continue
                normalized = norm

            elif fd.data_type == "year":
                norm = self._try_year(raw_value)
                if norm is None:
                    continue
                normalized = norm

            elif fd.data_type == "date":
                norm = self._try_date(raw_value)
                if norm is None:
                    continue
                normalized = norm

            # Accept first valid hit
            conf = _CONF_SPATIAL_RIGHT if method == _SPATIAL_RIGHT else _CONF_SPATIAL_BELOW
            return ExtractionResult(
                canonical_name=name,
                document_type=document_type,
                value=normalized,
                raw_source_text=raw_value,
                extraction_method=method,
                confidence=conf,
                source_page=page_num,
                bbox=_normalize_spatial_box(value_box, word_map),
                normalization_applied=[f"spatial_{fd.data_type}"],
            )

        # Pass 3 — Fuzzy label matching (Day 11 integration).
        # Handles OCR-garbled labels that exact spatial matching can't find.
        # Only runs for string fields — numeric types are found by data patterns.
        if fd.data_type == "string":
            full_page_text = "\n".join(
                page_maps.get(pn, SpatialWordMap([])).all_words_as_text()
                for pn in sorted(page_maps)
                if pn in page_range
            )
            hit = find_best_label_match(full_page_text, fd.synonyms, r"[^\n]{1,80}")
            if hit:
                raw, snippet, pos, method = hit
                val = raw.strip().rstrip(".,;:")
                if val and len(val) > 1 and not self._is_known_label_text(val):
                    # Map fuzzy match to approximate page number
                    page_num = min(page_range) if page_range else 1
                    return ExtractionResult(
                        canonical_name=name,
                        document_type=document_type,
                        value=val,
                        raw_source_text=snippet,
                        extraction_method=ExtractionMethod.FUZZY_LABEL_MATCH,
                        confidence=self._schema.method_confidence(ExtractionMethod.FUZZY_LABEL_MATCH),
                        source_page=page_num,
                        normalization_applied=["fuzzy_label_strip_whitespace"],
                    )

        return ExtractionResult(
            canonical_name=name,
            document_type=document_type,
            extraction_method=ExtractionMethod.NOT_FOUND,
            confidence=0.0,
        )

    @staticmethod
    def _page_range_for_field(fd: FieldDefinition, total_pages: int) -> set:
        """
        Infer which pages to search for a given field based on its form section.
        UAD 1004/1073 forms have consistent page structures:
          Pages 1-7: Subject, Contract, Neighborhood, Site, Improvements, Sales Comparison
          Pages 8-12: Certification, USPAP Addendum, Supplemental
          Pages 13+: Market Conditions Addendum, Rent Schedule, Charts
          Last 3 pages: Appraiser signature
        """
        all_pages = set(range(1, total_pages + 1))
        sections = set(fd.sections)

        if "appraiser" in sections or "uspap_addendum" in sections:
            # Signature page is typically in the last third of the document
            mid = max(1, total_pages // 2)
            return set(range(mid, total_pages + 1))

        if "market_conditions_addendum" in sections:
            # 1004MC form is typically in pages 10-20
            return set(range(8, min(total_pages + 1, 25)))

        if "rent_schedule" in sections:
            return set(range(10, total_pages + 1))

        if "reconciliation" in sections:
            # Reconciliation page is typically in first half
            return set(range(1, total_pages // 2 + 3))

        if any(s in sections for s in [
            "subject", "contract", "neighborhood", "site",
            "improvements", "condo_project", "condo_unit",
            "sales_comparison", "income_approach", "cost_approach",
            "prior_sale_history", "engagement_letter", "sales_contract",
        ]):
            # Main form content — first 60% of pages
            max_page = max(7, int(total_pages * 0.6))
            return set(range(1, max_page + 1))

        # Unknown section — search all pages
        return all_pages

    def _extract_enum_spatial(self, fd: FieldDefinition, page_maps: Dict, dt: str) -> ExtractionResult:
        """
        For checkbox/enum fields (property_rights, assignment_type, location, etc.):
        Find the label, then scan the row for which allowed value is checked/present.
        """
        for page_num, word_map in sorted(page_maps.items()):
            label_bbox = word_map.find_label(fd.synonyms, self._known_labels)
            if not label_bbox:
                continue
            lx0, ly0, lx1, ly1, _ = label_bbox
            matched = word_map.enum_proximity_search(lx0, ly0, ly1, fd.allowed_values)
            if matched:
                return self._found(fd, dt, matched, matched, _SPATIAL_RIGHT, 0.80, page_num)
        return self._not_found(fd, dt)

    def _extract_boolean_spatial(self, fd: FieldDefinition, page_maps: Dict, dt: str) -> ExtractionResult:
        """
        For boolean (checkbox) fields: look for checked/unchecked marker near label.
        """
        check_markers = {"x", "✓", "☑", "✗", "[x]", "yes"}
        uncheck_markers = {"☐", "[ ]", "no"}

        for page_num, word_map in sorted(page_maps.items()):
            hit = extract_field_spatially(word_map, fd.synonyms, self._known_labels)
            if not hit:
                continue
            raw, method, _ = hit
            raw_lower = raw.lower()
            if any(m in raw_lower for m in check_markers):
                return self._found(fd, dt, "True", raw, method, 0.80, page_num)
            if any(m in raw_lower for m in uncheck_markers):
                return self._found(fd, dt, "False", raw, method, 0.78, page_num)
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Data-pattern extractors (don't depend on labels)
    # ------------------------------------------------------------------

    def _subject_address_row(self, page_maps) -> dict:
        """Parse the URAR subject row 'Property Address | City | State | Zip Code'
        where each value sits to the RIGHT of its label on the SAME row. Segment
        the row by label x-positions so the subject's own state/zip are read
        (not the lender block's adjacent 'ST ZIP' or the street number).
        Memoized per page_maps object."""
        cache = getattr(self, "_subj_cache", None)
        if cache and cache[0] is page_maps:
            return cache[1]
        result: dict = {}
        for pn in sorted(page_maps)[:3]:
            wm = page_maps[pn]

            def first_label(t):
                cands = [w for w in wm._words
                         if w.text.lower().rstrip(":") == t and w.y0 < 300]
                return min(cands, key=lambda w: w.y0) if cands else None

            city_l, state_l, zip_l = first_label("city"), first_label("state"), first_label("zip")
            if not (state_l and zip_l):
                continue
            # the three labels must share one row (the subject header row)
            if abs(state_l.y_center - zip_l.y_center) > 3:
                continue
            ry = state_l.y_center
            row = sorted([w for w in wm._words if abs(w.y_center - ry) < 3], key=lambda w: w.x0)
            code = next((w for w in row if w.text.lower().rstrip(":") == "code"
                         and abs(w.x0 - zip_l.x0) < 40), None)
            zip_end = code.x1 if code else zip_l.x1
            _lbl = {"city", "state", "zip", "code", "property", "address"}
            # zip: first 5-digit token at/after the Zip Code label
            for w in row:
                if w.x0 >= zip_end - 2 and re.fullmatch(r"\d{5}(?:-\d{4})?", w.text):
                    result["zip_code"] = w.text[:5]
                    break
            # state: 2-letter US state between the State and Zip labels
            for w in row:
                if state_l.x1 <= w.x0 < zip_l.x0 - 2 and w.text.upper() in _US_STATES:
                    result["state"] = w.text.upper()
                    break
            # city: tokens between the City and State labels
            if city_l and abs(city_l.y_center - ry) <= 3:
                cv = [w.text for w in row
                      if city_l.x1 <= w.x0 < state_l.x0 - 2
                      and w.text.lower().rstrip(":") not in _lbl]
                if cv:
                    result["city"] = " ".join(cv)
            if result:
                result["page"] = pn
                break
        self._subj_cache = (page_maps, result)
        return result

    def _spatial_validated(self, fd, page_maps, dt, pattern, group, valid=None):
        """Spatial label match restricted to subject pages, validated by regex
        (and optional allowed-value set). Returns an ExtractionResult or None."""
        for page_num in sorted(page_maps)[:3]:   # subject section is up front
            wm = page_maps[page_num]
            hit = extract_field_spatially(wm, fd.synonyms, self._known_labels)
            if not hit:
                continue
            raw, method, _ = hit
            m = re.search(pattern, raw.strip())
            if not m:
                continue
            val = m.group(group)
            if valid is not None and val.upper() not in valid:
                continue
            return self._found(fd, dt, val.upper() if valid else val, raw, method,
                               _CONF_SPATIAL_RIGHT, page_num)
        return None

    def _data_pattern_zip(self, fd, full_map, dt):
        all_text = full_map.all_words_as_text()
        # Prefer a zip that follows a 2-letter state code ("TX 77494") — this
        # avoids grabbing the street number (e.g. "28203 Fantail Dr"), which a
        # bare first-5-digit search would wrongly return.
        m = re.search(r"\b([A-Z]{2})\s+(\d{5})(?:-\d{4})?\b", all_text)
        if m:
            return self._found(fd, dt, m.group(2), m.group(0), ExtractionMethod.DATA_PATTERN_ONLY, 0.82, 1)
        m = re.search(r"\b(\d{5})(?:-\d{4})?\b", all_text)
        if m:
            return self._found(fd, dt, m.group(1), m.group(0), ExtractionMethod.DATA_PATTERN_ONLY, 0.7, 1)
        return self._not_found(fd, dt)

    def _data_pattern_state(self, fd, full_map, dt):
        all_text = full_map.all_words_as_text()
        m = re.search(r"\b([A-Z]{2})\s+\d{5}\b", all_text)
        if m:
            return self._found(fd, dt, m.group(1).upper(), m.group(0), ExtractionMethod.DATA_PATTERN_ONLY, 0.78, 1)
        return self._not_found(fd, dt)

    def _structural_appraised_value(self, fd, page_maps, dt):
        """
        Find appraised value using two structural patterns:
        Pattern A: Cover letter format (Equity Solutions / TOTAL software):
          page 1 has "[property address]\n[client]\n[amount]\n[date]"
          The standalone amount immediately before a MM/DD/YYYY date is the appraised value.
        Pattern B: Reconciliation page: two identical large amounts on consecutive lines.
        """
        # Pattern A: cover letter — amount immediately before effective date on page 1-2
        for pn in [1, 2]:
            wm = page_maps.get(pn)
            if not wm:
                continue
            words_sorted = sorted(wm._words, key=lambda w: w.y_center)
            for i, sw in enumerate(words_sorted):
                if re.match(r"^\d{2}/\d{2}/\d{4}$", sw.text):
                    # Found a date — look at the word immediately before it (within 20px)
                    prev_words = [
                        w for w in words_sorted[:i]
                        if abs(w.y_center - sw.y_center) < 30
                        and w.x0 < sw.x0 + 50
                    ]
                    if prev_words:
                        prev = prev_words[-1]
                        raw = prev.text.replace(",", "")
                        try:
                            v = float(raw)
                            if 10000 < v < 100_000_000:
                                return self._found(fd, dt, str(int(v)), prev.text, ExtractionMethod.POSITIONAL_ANCHOR, 0.90, pn)
                        except ValueError:
                            pass

        # Pattern B: reconciliation page — two identical large amounts in word sequence
        for pn, wm in sorted(page_maps.items(), reverse=True):
            text = wm.all_words_as_text()
            m = re.search(r"([\d,]{5,})\s+\1(?:\s|$)", text)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    v = float(raw)
                    if 10000 < v < 100_000_000:
                        return self._found(fd, dt, str(int(v)), m.group(0), ExtractionMethod.POSITIONAL_ANCHOR, 0.88, pn)
                except ValueError:
                    pass

        # Pattern C: label search fallback
        for pn, wm in sorted(page_maps.items()):
            hit = extract_field_spatially(wm, fd.synonyms, self._known_labels)
            if hit:
                raw, method, _ = hit
                norm = self._try_currency(raw)
                if norm:
                    try:
                        v = float(norm)
                        if 10000 < v < 100_000_000:
                            return self._found(fd, dt, norm, raw, method, 0.82, pn)
                    except ValueError:
                        pass
        return self._not_found(fd, dt)

    def _extract_uad_code(self, fd: FieldDefinition, page_maps: Dict, dt: str) -> ExtractionResult:
        """
        Extract UAD condition (C1-C6) or quality (Q1-Q6) code.
        These appear as short codes — look for the pattern near the label.
        """
        prefix = "C" if fd.data_type == "uad_condition" else "Q"
        uad_pattern = re.compile(rf"\b{prefix}([1-6])\b")

        page_range = self._page_range_for_field(fd, max(page_maps.keys()))
        for pn, wm in sorted(page_maps.items()):
            if pn not in page_range:
                continue
            label_bbox = wm.find_label(fd.synonyms, self._known_labels)
            if not label_bbox:
                continue
            lx0, ly0, lx1, ly1, _ = label_bbox
            # Search in a wide area around the label for the UAD code
            candidates = [
                sw for sw in wm._words
                if abs(sw.y_center - (ly0 + ly1) / 2) < 20
                and sw.x0 >= lx0 - 50
                and sw.x0 <= lx1 + 200
                and uad_pattern.match(sw.text.strip())
            ]
            if candidates:
                val = candidates[0].text.strip().upper()
                return self._found(fd, dt, val, val, "spatial_right_of_label", 0.85, pn)
        return self._not_found(fd, dt)

    def _structural_date_from_sig_page(self, fd, page_maps, full_map, dt):
        """Find date from signature page: date before license number pattern."""
        all_text = full_map.all_words_as_text()
        m = re.search(r"(\d{2}/\d{2}/\d{4})\s+([A-Z]{2}\d{4,8})\s", all_text)
        if m:
            raw = m.group(1)
            norm = self._try_date(raw)
            if norm and fd.canonical_name == "effective_date":
                return self._found(fd, dt, norm, m.group(0), ExtractionMethod.POSITIONAL_ANCHOR, 0.85, 1)
        # Try spatial label search as fallback
        for pn, wm in sorted(page_maps.items()):
            hit = extract_field_spatially(wm, fd.synonyms, self._known_labels)
            if hit:
                raw, method, bbox = hit
                norm = self._try_date(raw)
                if norm:
                    return self._found(fd, dt, norm, raw, method, _CONF_SPATIAL_RIGHT, pn)
        return self._not_found(fd, dt)

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    def _normalize(self, raw: str, fd: FieldDefinition) -> str:
        return raw.strip().rstrip(".,;:")

    def _is_known_label_text(self, text: str) -> bool:
        words = text.lower().split()
        return all(w.rstrip(":/.,") in self._known_labels for w in words) if words else True

    def _try_currency(self, raw: str) -> Optional[str]:
        clean = re.sub(r"[$,\s]", "", raw.strip())
        try:
            v = float(clean)
            if v < 0:
                return None
            return str(int(v)) if v == int(v) else str(round(v, 2))
        except ValueError:
            return None

    def _try_numeric(self, raw: str) -> Optional[str]:
        """Extract the FIRST valid number from raw value text.
        Handles cases like '324 # of ...' → '324' by finding the first number token.
        """
        m = re.search(r"\d+(?:\.\d+)?", raw.strip())
        if m:
            try:
                v = float(m.group(0))
                return str(int(v)) if v == int(v) else str(round(v, 3))
            except ValueError:
                pass
        return None

    def _try_year(self, raw: str) -> Optional[str]:
        m = re.search(r"\b((?:19|20)\d{2})\b", raw)
        if m:
            y = int(m.group(1))
            if 1800 <= y <= 2030:
                return str(y)
        return None

    def _try_date(self, raw: str) -> Optional[str]:
        import datetime
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
            try:
                return datetime.datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _match_enum(self, text: str, allowed_values: List[str]) -> Optional[str]:
        text_lower = text.lower()
        for av in allowed_values:
            if av.lower() in text_lower or text_lower in av.lower():
                return av
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _found(self, fd, dt, value, raw, method, conf, page) -> ExtractionResult:
        return ExtractionResult(
            canonical_name=fd.canonical_name,
            document_type=dt,
            value=value,
            raw_source_text=raw,
            extraction_method=method,
            confidence=conf,
            source_page=page,
        )

    def _not_found(self, fd, dt) -> ExtractionResult:
        return ExtractionResult(
            canonical_name=fd.canonical_name,
            document_type=dt,
            extraction_method=ExtractionMethod.NOT_FOUND,
            confidence=0.0,
        )

    @staticmethod
    def _ocr_scanned_page(page, page_num: int) -> SpatialWordMap:
        """Render a scanned page and build a SpatialWordMap of its words.

        Tesseract is the primary engine: it is fast (~1-2 s/page) and reliable
        here, and it is what lets Tier One spatial matching see scanned pages.
        PaddleOCR 3.x is far slower on CPU (~40 s/page), so it is reserved for
        an explicit/GPU path (orchestrator L3) rather than this hot path.
        """
        from PIL import Image
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        return SpatialWordMap.from_tesseract(img, page_num)

    @staticmethod
    def _merge_page_maps(page_maps: Dict[int, SpatialWordMap]) -> SpatialWordMap:
        """Merge all page word maps into one for full-document pattern searches."""
        all_words: List[SpatialWord] = []
        for pn, wm in sorted(page_maps.items()):
            # Offset Y by page number * 10000 to avoid y-collision across pages
            offset = (pn - 1) * 10000
            for w in wm._words:
                all_words.append(SpatialWord(
                    x0=w.x0, y0=w.y0 + offset, x1=w.x1, y1=w.y1 + offset,
                    text=w.text, page_number=w.page_number,
                ))
        return SpatialWordMap(all_words)


# Module-level singleton
spatial_extractor = SpatialTier3Extractor()
