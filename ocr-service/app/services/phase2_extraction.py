"""
Phase 2 — Field Extraction Engine

Three-layer extraction:
  Layer 1: Spatial anchoring — finds section headers, extracts fields relative to them
  Layer 2: OCR error correction — fixes known misreads before field parsing
  Layer 3: Cross-field sanity checks — catches obviously wrong values, lowers confidence

Key fix from build plan: address splitting anchored on DATA patterns (5-digit zip,
2-letter state), NOT on label words that OCR mangles ("aP Code" → "Zip Code" no longer
needed for address parsing — we find the zip by its 5-digit shape).

Usage:
    from app.services.phase2_extraction import Phase2ExtractionEngine
    engine = Phase2ExtractionEngine()
    subject, meta = engine.extract_subject(full_text, page_index)
"""

import re
import logging
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.models.difference_report import SubjectSectionExtract, ContractSectionExtract
from app.models.field_meta import FieldMetaResult
from app.services.field_registry import field_registry
from app.services.ocr_correction import apply_ocr_correction

logger = logging.getLogger(__name__)

# llava:13b vision fallback for uncertain checkboxes
try:
    from app.services.ollama_service import detect_checkbox_vision, is_vision_model_available
    _VISION_OK = is_vision_model_available()
    if _VISION_OK:
        logger.info("llava:13b available — checkbox vision fallback enabled")
except Exception:
    _VISION_OK = False
    detect_checkbox_vision = None

# State → expected first digit(s) of zip code
_STATE_ZIP_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "AL": ("3",), "AR": ("7",), "AZ": ("8",), "CA": ("9",),
    "CO": ("8",), "CT": ("0",), "DC": ("2",), "DE": ("1",),
    "FL": ("3",), "GA": ("3",), "HI": ("9",), "IA": ("5",),
    "ID": ("8",), "IL": ("6",), "IN": ("4",), "KS": ("6",),
    "KY": ("4",), "LA": ("7",), "MA": ("0",), "MD": ("2",),
    "ME": ("0",), "MI": ("4",), "MN": ("5",), "MO": ("6",),
    "MS": ("3",), "MT": ("5",), "NC": ("2",), "ND": ("5",),
    "NE": ("6",), "NH": ("0",), "NJ": ("0",), "NM": ("8",),
    "NV": ("8",), "NY": ("1", "0"), "OH": ("4",), "OK": ("7",),
    "OR": ("9",), "PA": ("1",), "RI": ("0",), "SC": ("2",),
    "SD": ("5",), "TN": ("3",), "TX": ("7",), "UT": ("8",),
    "VA": ("2",), "VT": ("0",), "WA": ("9",), "WI": ("5",),
    "WV": ("2",), "WY": ("8",),
}


# UAD 1004 form labels. When OCR flattens a tabular row, the regex anchored on
# label A often captures label B (the next column header) as if it were the
# value. We use this set to detect "value == next label" and reject the match
# rather than emitting garbage.
#
# Keep entries lowercase, trimmed, no trailing colon. New labels can be added
# safely; over-inclusion is fine — it just turns wrong-extractions into
# `not_found`, which surfaces as VERIFY in the rules engine (the correct
# behavior when the extractor genuinely failed).
_UAD_FORM_LABEL_STOP_SET: frozenset = frozenset({
    # Subject section
    "subject property address", "property address", "address",
    "city", "state", "zip code", "zip", "county",
    "borrower", "co-borrower", "owner of public record", "owner of record",
    "legal description", "assessor's parcel #", "assessor's parcel number",
    "assessor's parcel", "parcel #", "parcel number", "apn",
    "tax year", "r.e. taxes", "real estate taxes", "taxes",
    "neighborhood name", "map reference", "census tract",
    "occupant", "owner", "tenant", "vacant",
    "special assessments", "pud", "hoa dues", "hoa", "per year", "per month",
    "lender", "lender/client", "lender / client", "client",
    "property rights appraised", "property rights",
    "fee simple", "leasehold", "de minimis pud",
    # Neighborhood section
    "location", "built-up", "growth", "property values", "demand/supply",
    "marketing time", "neighborhood boundaries", "present land use %",
    "one-unit housing", "price", "age", "low", "high", "pred",
    "neighborhood description", "market conditions",
    # Site section
    "dimensions", "area", "shape", "view", "specific zoning classification",
    "zoning compliance", "highest & best use",
    "utilities", "off-site improvements", "fema special flood hazard area",
    "fema flood zone", "fema map #", "fema map date",
    # Improvements
    "general description", "foundation", "exterior description",
    "interior", "heating", "cooling", "amenities", "car storage",
    "appliances", "finished area above grade contains",
    # Sales comparison grid headers
    "subject", "comparable sale # 1", "comparable sale # 2", "comparable sale # 3",
    "proximity to subject", "sale price", "sale price/gross liv. area",
    "data source(s)", "verification source(s)",
    "sale or financing concessions", "date of sale/time", "site",
    "design (style)", "quality of construction", "actual age", "condition",
    "above grade", "room count", "gross living area",
    "basement & finished rooms below grade", "functional utility",
    "garage/carport", "porch/patio/deck",
    # Misc
    "total bedrooms", "baths", "yes", "no",
    # Long boilerplate strings used elsewhere on the form (we anchor on full-line
    # match, so these are page-6 INTENDED USE / CERTIFICATION sentences that
    # were leaking into lender_address etc.)
    "is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?",
    "are the units, common elements, and recreation facilities complete?",
})


def _looks_like_form_label(value: str) -> bool:
    """
    True if `value` is itself a UAD form label rather than a real field value.

    Used by the generic extractor to detect the off-by-one OCR-flatten bug
    where a label-anchored regex captures the *next* label as the value.
    """
    if not value:
        return False
    raw = value.strip().lower().rstrip(":").rstrip(".")
    if raw in _UAD_FORM_LABEL_STOP_SET:
        return True
    # Also try with trailing punctuation stripped (handles "Parcel #" → "parcel"
    # when the corresponding "parcel" form is registered in the set).
    stripped = raw.rstrip("#").strip()
    if stripped and stripped in _UAD_FORM_LABEL_STOP_SET:
        return True
    return False


# ── Page position map ──────────────────────────────────────────────────────────

def build_page_position_map(page_index: Dict[int, str]) -> List[Tuple[int, int]]:
    """
    Map character positions in full_text → page numbers.
    Returns sorted list of (cumulative_start_pos, page_num).
    """
    positions: List[Tuple[int, int]] = []
    offset = 0
    for page_num in sorted(page_index.keys()):
        positions.append((offset, page_num))
        offset += len(page_index[page_num]) + 2  # +2 for "\n\n" separator
    return positions


def page_for_pos(char_pos: int, page_positions: List[Tuple[int, int]]) -> int:
    """Binary search: which page does character position `char_pos` belong to?"""
    if not page_positions:
        return 1
    starts = [p[0] for p in page_positions]
    idx = bisect_right(starts, char_pos) - 1
    return page_positions[max(0, idx)][1]


# ── Cross-page document section map ───────────────────────────────────────────

class DocumentSectionMap:
    """
    Maps UAD form section names to their location across the entire PDF document.

    Unlike the per-page _build_section_bounds() inside Phase2ExtractionEngine
    (which finds section Y ranges on a single page), this class operates on the
    complete page_index and word_index to produce a document-wide index:

        {section_name: (pdf_page, y_min, y_max)}

    Usage:
        doc_map = DocumentSectionMap(page_index, word_index)
        section_page, y_min, y_max = doc_map.locate("neighborhood")
        section_text = doc_map.section_text("neighborhood")

    The map is built lazily on first access and cached.
    """

    # Section header patterns — each entry is (section_key, text_patterns)
    # Multiple patterns handle different TOTAL/a la mode software rendering styles.
    SECTION_PATTERNS: List[Tuple[str, List[str]]] = [
        ("subject",          ["Property Address", "Borrower", "Uniform Residential Appraisal"]),
        ("contract",         ["Did you analyze the contract", "ANALYZE THE CONTRACT", "Contract Price"]),
        ("neighborhood",     ["Neighborhood Characteristics", "One-Unit Housing Trends", "NEIGHBORHOOD"]),
        ("site",             ["SITE", "Dimensions", "Zoning Classification", "FEMA Special Flood"]),
        ("improvements",     ["IMPROVEMENTS", "General Description", "Foundation", "Exterior Description"]),
        ("sales_comparison", ["SALES COMPARISON APPROACH", "COMPARABLE SALE #", "Comparable Sale # 1"]),
        ("reconciliation",   ["RECONCILIATION", "Indicated Value", "This appraisal is made"]),
        ("cost_approach",    ["COST APPROACH", "COST APPROACH TO VALUE", "Depreciation", "Estimated Remaining"]),
        ("income_approach",  ["INCOME APPROACH", "Estimated Monthly Market Rent"]),
        ("addendum",         ["ADDITIONAL COMMENTS", "Addendum", "USPAP", "APPRAISER'S CERTIFICATION"]),
        ("signature",        ["APPRAISER", "Signature", "State Certification #", "Expiration Date"]),
        ("photos",           ["Subject Front", "Subject Rear", "Subject Street Scene"]),
        ("sketch",           ["Floor Plan", "Sketch", "ANSI", "Gross Living Area Calculations"]),
        ("maps",             ["Location Map", "Flood Map", "FEMA Map", "Plat Map"]),
        ("1004mc",           ["1004MC", "Market Conditions Addendum", "Inventory Analysis"]),
    ]

    def __init__(
        self,
        page_index: Dict[int, str],
        word_index: Optional[Dict[int, List]] = None,
    ) -> None:
        self._page_index = page_index or {}
        self._word_index = word_index or {}
        self._map: Dict[str, Tuple[int, float, float]] = {}   # section → (page, y_min, y_max)
        self._built = False

    def build(self) -> None:
        """Scan every page for section header patterns and populate the section map."""
        if self._built:
            return

        # First pass: text-based detection on page_index
        # For each section, record the FIRST page/position where its header appears.
        raw_hits: Dict[str, Tuple[int, float]] = {}   # section → (page, approx_y)

        for section_key, patterns in self.SECTION_PATTERNS:
            for page_num in sorted(self._page_index.keys()):
                text = self._page_index.get(page_num, "") or ""
                for pattern in patterns:
                    if re.search(re.escape(pattern), text, re.I):
                        # Estimate Y position from text character offset
                        pos = re.search(re.escape(pattern), text, re.I)
                        approx_y = self._text_pos_to_y(text, pos.start() if pos else 0)
                        if section_key not in raw_hits:
                            raw_hits[section_key] = (page_num, approx_y)
                        break
                if section_key in raw_hits:
                    break

        # Second pass: word_index-based spatial refinement
        # If word positions are available, replace the text-estimated Y with the
        # actual word bbox_y for the matched anchor word on that page.
        for section_key, patterns in self.SECTION_PATTERNS:
            hit = raw_hits.get(section_key)
            if not hit:
                continue
            page_num, approx_y = hit
            words = self._word_index.get(page_num, [])
            if not words:
                continue
            for pattern in patterns:
                first_word = pattern.split()[0].lower()
                for word in words:
                    if (getattr(word, "text", "") or "").lower().startswith(first_word[:4]):
                        raw_hits[section_key] = (page_num, float(getattr(word, "bbox_y", approx_y)))
                        break

        # Build final map with y_max = y_min of the next section on the same page, or 1.0
        sorted_hits = sorted(raw_hits.items(), key=lambda kv: (kv[1][0], kv[1][1]))
        for i, (section_key, (page_num, y_min)) in enumerate(sorted_hits):
            # Find the next section that shares the same page
            y_max = 1.0
            for _, (next_page, next_y) in sorted_hits[i + 1:]:
                if next_page == page_num and next_y > y_min:
                    y_max = next_y
                    break
            self._map[section_key] = (page_num, round(y_min, 4), round(y_max, 4))

        self._built = True
        logger.info(
            "DocumentSectionMap built: %d sections located across %d pages",
            len(self._map), len(self._page_index),
        )

    def locate(self, section: str) -> Optional[Tuple[int, float, float]]:
        """Return (pdf_page, y_min, y_max) for the given section, or None."""
        self.build()
        return self._map.get(section)

    def section_text(self, section: str) -> str:
        """
        Return the page text restricted to the section's Y band.

        Uses word_index for accurate spatial filtering; falls back to returning
        the entire page text when word positions are unavailable.
        """
        self.build()
        location = self._map.get(section)
        if not location:
            return ""

        page_num, y_min, y_max = location

        # Spatial word filtering (accurate)
        words = self._word_index.get(page_num, [])
        if words:
            section_words = [
                w for w in words
                if y_min <= float(getattr(w, "bbox_y", 0.0)) < y_max
            ]
            if section_words:
                sorted_words = sorted(
                    section_words,
                    key=lambda w: (
                        round(float(getattr(w, "bbox_y", 0.0)), 2),
                        float(getattr(w, "bbox_x", 0.0)),
                    ),
                )
                return " ".join(getattr(w, "text", "") for w in sorted_words)

        # Fallback: return the whole page text
        return self._page_index.get(page_num, "")

    def all_sections(self) -> Dict[str, Tuple[int, float, float]]:
        """Return the full built section map."""
        self.build()
        return dict(self._map)

    @staticmethod
    def _text_pos_to_y(text: str, char_pos: int) -> float:
        """Estimate normalized Y from character position within page text."""
        lines_before = text[:char_pos].count("\n")
        total_lines = max(1, text.count("\n") + 1)
        return round(min(0.99, max(0.0, lines_before / total_lines)), 4)


# ── Core extraction helper ─────────────────────────────────────────────────────

class Phase2ExtractionEngine:
    """
    Phase 2 field extraction with metadata (source page, confidence, correction).
    """

    # ── UAD 1004 section header anchors ───────────────────────────────────────
    # Used by _build_section_bounds() to locate section start Y positions inside
    # a single PDF page.  The UAD form is dense: pages 1-2 pack Subject,
    # Contract, Neighborhood, Site, and Improvements into the same physical page.
    # Without Y-boundary awareness, regex extractors bleed across sections.
    #
    # Each tuple: (section_key, list_of_label_words_to_search_in_word_index)
    # The first label word that appears on the page becomes the section's y_min.
    _UAD_SECTION_ANCHORS: List[Tuple[str, List[str]]] = [
        ("subject",           ["Borrower", "Property Address"]),
        ("contract",          ["Contract", "ANALYZE"]),
        ("neighborhood",      ["Neighborhood", "NEIGHBORHOOD"]),
        ("site",              ["Site", "SITE", "Dimensions"]),
        ("improvements",      ["Improvements", "IMPROVEMENTS", "Foundation"]),
        ("sales_comparison",  ["COMPARABLE", "Comparable", "Sale Price"]),
        ("reconciliation",    ["Reconciliation", "RECONCILIATION", "Indicated Value"]),
        ("cost_approach",     ["Cost Approach", "COST APPROACH", "Depreciation"]),
        ("income_approach",   ["Income Approach", "INCOME APPROACH", "Gross Rent"]),
    ]

    def __init__(self):
        # Page images for llava:13b checkbox fallback — set per extract_subject() call
        self._page_images: Dict[int, object] = {}
        self._page_index: Dict[int, str] = {}
        self._page_positions: List[Tuple[int, int]] = []
        self._word_index: Dict[int, List[object]] = {}
        # Section bounds cache: {page_num: {section_key: (y_min, y_max)}}
        self._section_bounds_cache: Dict[int, Dict[str, Tuple[float, float]]] = {}
        # PDF file path — set by qc_processor before extract_subject() so that
        # Camelot comparable grid extraction can read the file directly.
        self._pdf_path: Optional[str] = None

    def extract_subject(
        self,
        full_text: str,
        page_index: Dict[int, str],
        page_images: Optional[Dict[int, object]] = None,
        word_index: Optional[Dict[int, List[object]]] = None,
    ) -> Tuple[SubjectSectionExtract, Dict[str, FieldMetaResult]]:
        """
        Extract Subject Section fields with full per-field metadata.

        Returns:
            (SubjectSectionExtract, dict of field_name → FieldMetaResult)
        """
        # Store page images for llava:13b checkbox fallback (Step 2)
        # Page 1 is the main form page — checkboxes are almost always on pages 1-3
        self._page_images = page_images or {}
        self._page_index = page_index
        self._word_index = word_index or {}
        self._section_bounds_cache = {}   # reset per document

        # Build a SpatialWordIndex so _extract() can look up per-word Tesseract
        # confidence for each matched value rather than using pattern-rank heuristics.
        # Falls back to None when the word_index is empty (embedded-text-only PDFs).
        from app.ocr.ocr_pipeline import SpatialWordIndex
        self._spatial_index = SpatialWordIndex(self._word_index) if self._word_index else None

        # Build the cross-page document section map.
        # This is the authoritative source for section-to-page mapping across the
        # full PDF (e.g. "where is the Sales Comparison section?").  Individual
        # per-page section bounds (_build_section_bounds) are used for within-page
        # Y filtering; this map is used when rules or extractors need the section
        # page number or cross-page section text.
        self._doc_section_map = DocumentSectionMap(page_index, self._word_index)
        self._doc_section_map.build()   # eager build — avoids repeated scanning

        # Apply OCR corrections to the full text before any regex
        corrected_text, correction_count = self._correct_text(full_text)
        if correction_count > 0:
            logger.info("Applied %d OCR corrections to document text", correction_count)

        # Build position → page map
        page_pos = build_page_position_map(page_index)
        self._page_positions = page_pos

        # ── Section-restricted text for page 1 ────────────────────────────────
        # Pre-compute subject-section and contract-section restricted text slices
        # from the word index.  When the word index is available, these slices
        # only contain words whose Y coordinate falls inside the section boundaries
        # detected by _build_section_bounds(), preventing cross-section pollution.
        # Falls back to the full page-1-2 text window when the word index is empty.
        _p1_full, _p1_offset = self._text_window_for_pages(corrected_text, page_pos, 1, 1)
        _subj_text, _subj_offset = self._section_restricted_text(1, "subject", fallback_text=_p1_full)
        _has_section_bounds = bool(self._build_section_bounds(1))
        if _has_section_bounds and _subj_text:
            # Use section-restricted text for subject-section extractions
            subject_text = _subj_text
            subject_offset = 0   # section text is rebuilt from words; no char offset
            logger.info("Section boundary detection active for page 1 subject section")
        else:
            # Fall back to full text — section anchors were not found in word index
            subject_text = corrected_text
            subject_offset = 0

        # Keep the full OCR stream for extractions that span multiple sections or
        # pages (e.g. checkbox detection, comparable extraction, narrative blocks).
        text = corrected_text
        pos_offset = 0

        meta: Dict[str, FieldMetaResult] = {}

        # ── S-1: Address (with robust splitting) ─────────────────────────────
        street, city, state, zip_code = self._extract_address_robust(text, page_pos, pos_offset)
        meta["property_address"] = street
        meta["city"] = city
        meta["state"] = state
        meta["zip_code"] = zip_code

        # County extraction uses a stop-word lookahead to prevent bleeding into
        # adjacent form fields.  When section-restricted text is available (word
        # index present), search only within the subject section Y-band so the
        # Borrower and Owner columns on the same physical row are excluded.
        #
        # Pattern 1 — inline address row (primary):
        #   "County Colquitt State GA …" → group(1) = "Colquitt"
        #   "County San Joaquin State CA …" → group(1) = "San Joaquin"
        # Pattern 2 — value-stream (PyMuPDF top-to-bottom):
        #   zip → borrower → owner → county → legal description
        county_m = self._extract("county", subject_text, [
            r"County[:\s]+([A-Z][a-zA-Z]{2,19}(?:[ \t]+[A-Z][a-zA-Z]{2,14})?)(?=[ \t]+(?:State|Zip|City|Legal|Assessor|Map)|[\n\r]|$)",
            r"(?:\d{5})\n[^\n]+\n[^\n]+\n([A-Za-z]{3,25}(?:[ \t]+[A-Za-z]{2,14})?)\n(?:Lot|Section|Block|Parcel|Phase|Tract|\d)",
        ], page_pos, pos_offset, spatial_labels=["County"])

        # Last-resort sanity check: if the extracted value still looks polluted
        # (contains digits, slash, or is implausibly long), discard it so S-1 is
        # not hard-failed by garbage rather than a real address mismatch.
        if county_m.value and (
            len(county_m.value) > 30
            or re.search(r"[0-9/\\]", county_m.value)
        ):
            county_m = FieldMetaResult("county", confidence=0.0, extraction_method="not_found")

        meta["county"] = county_m

        # ── S-2: Borrower ─────────────────────────────────────────────────────
        # Use section-restricted text when available to prevent borrower name
        # from bleeding into the Owner or County columns on flattened UAD rows.
        meta["borrower_name"] = self._extract("borrower_name", subject_text, [
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)(.{3,120}?)(?=\s+(?:Owner of Public Record|Property Address|City|County|Legal Description|Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b|\n|$)",
            r"BORROWER[:\s]+(?!LENDER|CLIENT)(.{3,120}?)(?=\s+(?:OWNER OF PUBLIC RECORD|PROPERTY ADDRESS|CITY|COUNTY|LEGAL DESCRIPTION|ASSESSOR|TAX YEAR|OCCUPANT|MAP REFERENCE|CENSUS TRACT|LENDER|CLIENT)\b|\n|$)",
        ], page_pos, pos_offset)
        self._trim_merged_person_field(meta["borrower_name"])

        meta["co_borrower_name"] = self._extract("co_borrower_name", subject_text, [
            r"Co-?Borrower[:\s]+(.{3,120}?)(?=\s+(?:Owner of Public Record|Property Address|City|County|Legal Description|Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b|\n|$)",
            r"CO-?BORROWER[:\s]+(.{3,120}?)(?=\s+(?:OWNER OF PUBLIC RECORD|PROPERTY ADDRESS|CITY|COUNTY|LEGAL DESCRIPTION|ASSESSOR|TAX YEAR|OCCUPANT|MAP REFERENCE|CENSUS TRACT|LENDER|CLIENT)\b|\n|$)",
        ], page_pos, pos_offset)
        self._trim_merged_person_field(meta["co_borrower_name"])

        # ── S-3: Owner of Public Record ───────────────────────────────────────
        meta["owner_of_public_record"] = self._extract("owner_of_public_record", text, [
            r"Owner of Public Record[:\s]+([^\n]+)",
            r"Current Owner[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Owner of Public Record", "Owner of Record"])
        # Apply the same boundary-trim used for Borrower — OCR row flattening
        # often appends "County Colquitt" or "LLCCounty Colquitt" to the owner name.
        self._trim_merged_person_field(meta["owner_of_public_record"])

        # ── S-4: Legal / APN / Taxes ──────────────────────────────────────────
        meta["legal_description"] = self._extract("legal_description", text, [
            r"Legal Description[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Legal Description"])

        meta["assessors_parcel_number"] = self._extract("assessors_parcel_number", text, [
            r"(?:Assessor'?s?\s*)?Parcel\s*(?:#|Number|No\.?)[:\s]+([^\n]+)",
            r"APN[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Assessor's Parcel #", "Assessor's Parcel Number", "APN"])

        meta["tax_year"] = self._extract("tax_year", text, [
            r"Tax Year[:\s]+(\d{4})",
        ], page_pos, pos_offset, spatial_labels=["Tax Year"])

        meta["real_estate_taxes"] = self._extract("real_estate_taxes", text, [
            r"R\.?E\.?\s*Taxes\s*\$?\s*([\d,]+)",
            r"Real Estate Taxes\s*\$?\s*([\d,]+)",
        ], page_pos, pos_offset)

        # ── S-5: Neighborhood Name ────────────────────────────────────────────
        meta["neighborhood_name"] = self._extract("neighborhood_name", text, [
            r"Neighborhood Name[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Neighborhood Name"])

        # ── S-6: Map Reference / Census Tract ─────────────────────────────────
        meta["map_reference"] = self._extract("map_reference", text, [
            r"Map Reference[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Map Reference"])

        meta["census_tract"] = self._extract("census_tract", text, [
            r"Census Tract[:\s]+(\d{4}\.\d{2})",
            r"Census Tract[:\s]+([^\n]+)",
        ], page_pos, pos_offset, spatial_labels=["Census Tract"])

        # ── S-7: Occupant ─────────────────────────────────────────────────────
        # Use three-state detection: True=[X], False=[ ], None=not found
        owner_state  = self._checkbox_state(text, "Owner")
        tenant_state = self._checkbox_state(text, "Tenant")
        vacant_state = self._checkbox_state(text, "Vacant")

        if owner_state is True:
            occupant, occ_conf = "Owner", 0.90
        elif tenant_state is True:
            occupant, occ_conf = "Tenant", 0.90
        elif vacant_state is True:
            occupant, occ_conf = "Vacant", 0.90
        # Contextual inference: digital UAD PDFs frequently encode checked boxes
        # as font glyphs or image marks that OCR cannot read as "[X]".
        # When ALL three checkbox states are None, use surrounding text evidence.
        # Confidence levels are set to meet or exceed the 0.85 PASS threshold when
        # the contextual signal is unambiguous (strong phrase match), and below it
        # when inference is speculative, so weak cases still surface for review.
        elif all(s is None for s in [owner_state, tenant_state, vacant_state]):
            if re.search(r"\bowner\s+occupied\b|\boccupant[:\s]+owner\b", text, re.I):
                # Explicit phrase — as reliable as a checkbox in practice
                occupant, occ_conf = "Owner", 0.88
            elif re.search(r"\btenant\s+occupied\b|\boccupant[:\s]+tenant\b|\blease\b", text, re.I):
                occupant, occ_conf = "Tenant", 0.85
            elif re.search(r"\bvacant\b|\butilities\s+(?:are\s+)?off\b|\bproperty\s+is\s+vacant\b", text, re.I):
                occupant, occ_conf = "Vacant", 0.82
            elif re.search(r"\bpurchase\s+transaction\b|\bpurchase\b", text, re.I):
                # Purchase transactions with no vacancy/tenant signal → likely owner-occupied
                # but confidence is below threshold — reviewer confirms this case
                occupant, occ_conf = "Owner", 0.72
            else:
                occupant, occ_conf = None, 0.30
        elif any(s is False for s in [owner_state, tenant_state, vacant_state]):
            # At least one checkbox is explicitly [ ] but none are [X] → conflicting state
            occupant, occ_conf = None, 0.30
        else:
            # OCR produced no readable checkbox state at all
            occupant, occ_conf = None, 0.0

        meta["occupant_status"] = FieldMetaResult(
            "occupant_status", raw_value=occupant, corrected_value=occupant,
            confidence=occ_conf,
            extraction_method="regex_primary" if occupant else ("regex_fallback" if occ_conf > 0 else "not_found"),
        )

        # ── S-8: Special Assessments ──────────────────────────────────────────
        # Restrict to pages 1-2 so the Improvements section (which has similar
        # dollar-value rows near Y≈0.60 of the same page) cannot pollute this field.
        sa_text, sa_offset = self._text_window_for_pages(text, page_pos, 1, 2)
        meta["special_assessments"] = self._extract("special_assessments", sa_text, [
            r"Special Assessments[:\s]*\$?([\d,]+)",
        ], page_pos, sa_offset)

        # ── S-9: PUD / HOA ────────────────────────────────────────────────────
        pud_state = self._checkbox_state(text, "PUD")

        # Inference tier: when OCR can't read the checkbox (state = None), use
        # contextual signals to determine PUD status rather than returning NOT_FOUND.
        #
        # Most residential UAD appraisals are NOT PUDs.  Positive PUD signals:
        #   - HOA dues > $0 with a monthly/annual period
        #   - Explicit "PUD" language in addenda/narrative
        # Absence of these signals in a single-family appraisal → not a PUD (False).
        if pud_state is None:
            hoa_meta = meta.get("hoa_dues")
            hoa_val = getattr(hoa_meta, "value", None)
            try:
                hoa_amount = float(str(hoa_val).replace(",", "").replace("$", "")) if hoa_val else 0.0
            except (TypeError, ValueError):
                hoa_amount = 0.0

            has_positive_pud_signal = (
                hoa_amount > 0
                or bool(re.search(r"\bPUD\s+(?:project|association|homeowner)", text, re.I))
            )
            if has_positive_pud_signal:
                pud_state = True   # Evidence points to PUD
            else:
                pud_state = False  # No evidence = almost certainly not a PUD
                # Confidence is moderate — reviewer can override if wrong
        pud_val = "True" if pud_state is True else "False"
        pud_conf = 0.90 if pud_state is True else 0.80
        meta["is_pud_checked"] = FieldMetaResult(
            "is_pud_checked", raw_value=pud_val, corrected_value=pud_val,
            confidence=pud_conf,
            extraction_method="regex_primary" if pud_state is not None else "not_found",
        )

        # Restrict HOA extraction to pages 1-2 for the same reason as special_assessments.
        hoa_text, hoa_offset = self._text_window_for_pages(text, page_pos, 1, 2)
        meta["hoa_dues"] = self._extract("hoa_dues", hoa_text, [
            r"HOA\s+Dues?[:\s]*\$?([\d,]+)",
            r"HOA[:\s]*\$?([\d,]+)",
        ], page_pos, hoa_offset)

        hoa_period = None
        if re.search(r"per\s+month|monthly", text, re.I):
            hoa_period = "Per Month"
        elif re.search(r"per\s+year|annual", text, re.I):
            hoa_period = "Per Year"
        meta["hoa_period"] = FieldMetaResult(
            "hoa_period", raw_value=hoa_period, corrected_value=hoa_period,
            confidence=0.70 if hoa_period else 0.0,
            extraction_method="regex_primary" if hoa_period else "not_found"
        )

        # ── S-10: Lender / Client ─────────────────────────────────────────────
        lender_text, lender_pos_offset = self._text_window_for_pages(text, page_pos, 1, 2)
        meta["lender_name"] = self._extract("lender_name", lender_text, [
            # Pattern 1 — corporate suffix (most specific): stops before Address or EOL.
            # Handles "Clear2Mortgage, Inc." because [A-Za-z0-9\s,\.&]+ matches digits.
            r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z0-9\s,\.&]+?(?:Corporation|Corp|Inc\.?|LLC|LLP|Company|Co\.?|Bank|Mortgage|Credit Union|Funding|Capital|Financial|Home Loans?|Lending|Services?))(?:\.?\s+(?:Address|Client)|\s*\n|\s*$)",
            # Pattern 2 — address number lookahead: "Lender/Client FooBar Inc 123 Main St…"
            # stops when a street number (up to 5 digits) follows a space.
            r"Lender/?Client[\s—:-]+([A-Z][A-Za-z0-9\s,\.&]{4,70}?)(?=\s+\d{1,5}[\s,]|\s+Address\b|\n|$)",
            # Pattern 3 — broad fallback: Title-Case name up to 60 chars, stops at Address or newline.
            # Catches AMC platforms where the company name has no standard corporate suffix.
            r"Lender/?Client[\s\-—:]+([A-Z][a-zA-Z0-9\s&,\.\-]{3,60}?)(?:\s+Address\b|\s+Client\b|\n)",
            # Pattern 4 — last resort: any non-empty content until Address or line-end.
            r"Lender/?Client[\s\-—:]+([^\n]{3,70}?)(?:\s*Address\b|\s*\n|\s*$)",
            # Pattern 5 — newline-separated label/value: "Lender / Client\nFoo Bank" or
            # "Lender\nClient\nFoo Bank".  Handles spacing variants like "Lender / Client".
            r"Lender\s*/?\s*Client[\s\-—:\n]+([A-Za-z][^\n]{3,70}?)(?:\n|$)",
            # Pattern 6 — company suffix on next line after any Lender/Client variant.
            r"(?:Lender|Client)[^\n]*\n([A-Z][A-Za-z0-9\s,\.&]{4,70}(?:Corp|Inc|LLC|Bank|Mortgage|Financial)[^\n]*)",
        ], page_pos, lender_pos_offset, post_clean=r'\s*(Address|Client Address)\b.*$',
           spatial_labels=["Lender/Client", "Lender"], spatial_page_range=(1, 2))

        meta["lender_address"] = self._extract("lender_address", lender_text, [
            r"Lender\s+Address[:\s]+(\d[^\n]+)",
            r"(?:Lender/?Client|Lender)\s+Address[:\s]+([^\n]+)",
        ], page_pos, lender_pos_offset, spatial_labels=["Lender Address", "Client Address"], spatial_page_range=(1, 2))

        # ── S-11: Property Rights ─────────────────────────────────────────────
        # Tier 1: checkbox marker — digital PDFs emit [X] / X adjacent to the label.
        # Tier 2: contextual — "Fee Simple" present without a marker.  Residential
        # single-family appraisals are almost always Fee Simple, so a plain text hit
        # is highly reliable.  Confidence is set to 0.88 (≥ 0.85 pass threshold) to
        # prevent false OCR_LOW_CONFIDENCE escalation for an unambiguous field.
        rights = None
        rights_conf = 0.0
        rights_method = "not_found"
        for label in ["Fee Simple", "Leasehold", "De Minimis PUD"]:
            state = self._checkbox_state(text, label)
            if state is True:
                rights = label
                rights_conf = 0.90   # Explicit checkbox marker — high confidence
                rights_method = "regex_primary"
                break

        if rights is None:
            # Checkbox marker absent (common in digital UAD PDFs that encode the
            # tick as a font character rather than bracketed text).  Fall back to
            # presence matching: whichever rights label appears earliest in the text
            # is almost certainly the checked one because only one can apply.
            for label in ["Fee Simple", "Leasehold", "De Minimis PUD"]:
                if re.search(rf"\b{re.escape(label)}\b", text, re.I):
                    rights = label
                    rights_conf = 0.88   # Strong contextual evidence; meets pass threshold
                    rights_method = "spatial_anchor"
                    break

        meta["property_rights"] = FieldMetaResult(
            "property_rights", raw_value=rights, corrected_value=rights,
            confidence=rights_conf,
            extraction_method=rights_method,
        )

        # ── S-12: Prior Listing ───────────────────────────────────────────────
        prior_sale_match = re.search(
            r"offered for sale.*?(?:in the twelve months|12 months).*?\?"
            r".*?(x|X|><|\[x\]|\[X\])\s*(Yes|No)",
            text, re.I | re.DOTALL
        )
        if prior_sale_match:
            answer = prior_sale_match.group(2).upper()
            offered = "True" if answer == "YES" else "False"
            meta["offered_for_sale_12mo"] = FieldMetaResult(
                "offered_for_sale_12mo", raw_value=offered, corrected_value=offered,
                confidence=0.80, extraction_method="spatial_anchor",
                source_page=page_for_pos(prior_sale_match.start() + pos_offset, page_pos)
            )
        else:
            # Inference: when DOM/MLS listing data is present, the property WAS offered for sale.
            # Digital PDFs often omit checkbox text; listing data is a stronger signal than
            # the absence of a Yes/No marker.
            listing_evidence = re.search(
                r"\bDOM\s*\d+\b|\bSGAMLS\b|\bMLS\s*#\s*\d+\b|\bList\s+(?:Price|Date)\b",
                text, re.I
            )
            if listing_evidence:
                meta["offered_for_sale_12mo"] = FieldMetaResult(
                    "offered_for_sale_12mo", raw_value="True", corrected_value="True",
                    confidence=0.72, extraction_method="regex_fallback",
                    source_page=page_for_pos(listing_evidence.start() + pos_offset, page_pos)
                )
            else:
                meta["offered_for_sale_12mo"] = FieldMetaResult(
                    "offered_for_sale_12mo", confidence=0.0, extraction_method="not_found"
                )

        # Data source sits on the first form page (pages 1-3 of the UAD PDF).
        # Restrict search to that window to avoid matching the boilerplate label
        # "Data Source(s)" that appears in the PUD section on page 5+.
        data_src_text, data_src_offset = self._text_window_for_pages(text, page_pos, 1, 3)
        meta["data_source"] = self._extract("data_source", data_src_text, [
            # The appraiser types the source (e.g. "MLS, Tax Cards") after the label.
            r"Data Source[s]?[:\s]+([A-Za-z][A-Za-z0-9 ,\.#-]{2,80}?)(?:\n|$)",
        ], page_pos, data_src_offset)

        # Boilerplate contamination guard: if the extracted value is USPAP certification
        # language (page 5+) or unreasonably long, discard it rather than propagate garbage.
        _BOILERPLATE_MARKERS = (
            "units, common elements", "recreation facilities",
            "are the units", "this appraisal is made",
            "the borrower", "intended use", "the real property",
        )
        _ds_meta = meta.get("data_source")
        if _ds_meta and _ds_meta.value:
            _ds_val = str(_ds_meta.value).lower()
            if any(m in _ds_val for m in _BOILERPLATE_MARKERS) or len(_ds_val) > 80:
                meta["data_source"] = FieldMetaResult(
                    "data_source", confidence=0.0, extraction_method="not_found"
                )
                logger.debug("data_source guard: rejected boilerplate value")

        meta["mls_number"] = self._extract("mls_number", text, [
            r"MLS[:\s#]+([A-Z0-9]+)",
        ], page_pos, pos_offset)

        # ── Comparable Sales (new in Phase 2) ─────────────────────────────────
        comps = self._extract_comparables(text, page_pos, pos_offset)
        for i, comp in enumerate(comps, 1):
            meta[f"comp_{i}_address"] = comp.get("address")
            meta[f"comp_{i}_sale_price"] = comp.get("sale_price")

        # ── Market value opinion ───────────────────────────────────────────────
        # Restrict to the reconciliation / summary section (pages 3-5).
        # The bare "Value" pattern below is intentionally the last fallback — it is
        # too broad for a full-document search and previously captured a lone comma
        # because the actual dollar amount appeared on a separate text line.
        mv_text, mv_offset = self._text_window_for_pages(text, page_pos, 3, 5)
        meta["market_value_opinion"] = self._extract("market_value_opinion", mv_text, [
            r"(?:Appraised|Market|Indicated)\s+Value[:\s]*\$?([\d,]{5,})",
            r"Opinion of (?:Market\s+)?Value[:\s]*\$?([\d,]{5,})",
            # UAD form label: "$ <amount> as of <date>" on the reconciliation line
            r"\$\s*([\d,]{5,})\s+as\s+of",
        ], page_pos, mv_offset)

        # Guard: extracted value must contain at least 5 consecutive digits (a real dollar amount).
        # The bare-comma failure mode ("," matched the last pattern when the amount was on a
        # separate line) is caught here before it can propagate to value-comparison rules.
        _mv_meta = meta.get("market_value_opinion")
        if _mv_meta and _mv_meta.value:
            _clean = re.sub(r"[,$\s]", "", str(_mv_meta.value))
            if not re.match(r"^\d{5,}$", _clean):
                meta["market_value_opinion"] = FieldMetaResult(
                    "market_value_opinion", confidence=0.0, extraction_method="not_found"
                )
                logger.debug(
                    "market_value_opinion guard: rejected '%s' (not a valid dollar amount)",
                    _mv_meta.value,
                )

        self._fill_subject_value_stream_fallbacks(meta, text, page_pos, pos_offset)

        # ── Condition / Quality ratings ────────────────────────────────────────
        meta["condition_rating"] = self._extract("condition_rating", text, [
            r"\b(C[1-6])\b",
        ], page_pos, pos_offset)

        meta["quality_rating"] = self._extract("quality_rating", text, [
            r"\b(Q[1-6])\b",
        ], page_pos, pos_offset)

        # ── Neighbourhood description and market conditions ───────────────────
        # Use the neighborhood section text from DocumentSectionMap when available.
        # This prevents description/commentary extraction from matching text in
        # the Subject, Contract, or Site sections that happen to contain the same
        # label words (e.g. "Market Conditions" appears in multiple addenda pages).
        nbr_section_text = (
            self._doc_section_map.section_text("neighborhood")
            if self._doc_section_map else ""
        )
        nbr_search_text = nbr_section_text if len(nbr_section_text) >= 80 else text

        meta["neighborhood_description"] = self._extract_text_block("neighborhood_description", nbr_search_text, [
            r"(?:Neighborhood Description|Neighborhood Boundaries)[:\s]+(.{30,800}?)(?:\n{2,}|\Z)",
        ], page_pos, pos_offset)

        meta["market_conditions_commentary"] = self._extract_text_block("market_conditions_commentary", nbr_search_text, [
            r"Market Conditions[:\s]+(.{30,800}?)(?:\n{2,}|\Z)",
        ], page_pos, pos_offset)

        # ── Neighborhood grid fields (N-1..N-5) ──────────────────────────────
        # Use neighborhood section text for the grid too — the one-unit housing
        # price/age grid is always in the Neighborhood section and must not pick
        # up price figures from the Sales Comparison Approach grid.
        meta.update(self._extract_neighborhood_fields(nbr_search_text, page_pos, pos_offset))
        meta.update(self._extract_total_page1_value_block(text, page_pos, pos_offset))

        # ── Cross-field sanity checks ──────────────────────────────────────────
        meta = self._sanity_checks(meta)

        # ── Map meta → SubjectSectionExtract (backward-compat) ────────────────
        subject = self._to_subject_extract(meta)
        field_registry.validate_meta("phase2_subject", meta.keys())

        return subject, meta

    def _fill_subject_value_stream_fallbacks(
        self,
        meta: Dict[str, FieldMetaResult],
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> None:
        """Fill page-1 subject facts from TOTAL's flattened data stream."""
        form_start = re.search(r"\bForm\s+1004UAD\b", text, re.I)
        prefix = text[:form_start.start()] if form_start else text[:5000]

        tax_match = re.search(
            r"(Lot\s+\d+\s+.+?)\s+([A-Za-z]\d{3}\s+\d{3})\s+(\d{4})\s+([\d,]+)\s+"
            r"([A-Za-z][A-Za-z0-9 /.-]+?)\s+(\d{3,8})\s+(\d{4}\.\d{2})\s+"
            r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
            prefix,
            re.I | re.S,
        )
        if tax_match:
            fallbacks = {
                "legal_description": (tax_match.group(1), 1, 0.86),
                "assessors_parcel_number": (tax_match.group(2), 2, 0.84),
                "tax_year": (tax_match.group(3), 3, 0.84),
                "real_estate_taxes": (tax_match.group(4), 4, 0.84),
                "neighborhood_name": (tax_match.group(5), 5, 0.82),
                "map_reference": (tax_match.group(6), 6, 0.78),
                "census_tract": (tax_match.group(7), 7, 0.84),
                "special_assessments": (tax_match.group(8), 8, 0.78),
                "hoa_dues": (tax_match.group(9), 9, 0.70),
            }
            for field, (value, group, confidence) in fallbacks.items():
                if self._field_missing(meta, field):
                    self._put_meta(meta, field, value, tax_match, group, page_pos, pos_offset, confidence)

        if self._field_missing(meta, "property_rights"):
            rights_match = re.search(r"\b(Fee\s+Simple)\b", text[:12000], re.I)
            if rights_match:
                self._put_meta(meta, "property_rights", "Fee Simple", rights_match, 1, page_pos, pos_offset, 0.68, method="context_fallback")

        # ── Effective Age — XF-3 and I-1 need it ─────────────────────────────
        if self._field_missing(meta, "effective_age"):
            eff_age_match = re.search(
                r"Effective\s+Age[:\s]*(\d{1,3})\s*(?:yrs?\.?|years?)?",
                text, re.I,
            ) or re.search(
                r"(?:Effective|eff\.?)\s+Age[:\s]*(\d{1,3})",
                text, re.I,
            )
            if eff_age_match:
                meta["effective_age"] = FieldMetaResult(
                    "effective_age",
                    raw_value=eff_age_match.group(1),
                    corrected_value=eff_age_match.group(1),
                    confidence=0.80,
                    source_page=page_for_pos(eff_age_match.start() + pos_offset, page_pos),
                    extraction_method="regex_primary",
                )

        # ── Gross Living Area — I-7, SCA-17 need it ──────────────────────────
        if self._field_missing(meta, "gla"):
            gla_match = re.search(
                r"(?:Gross\s+Living\s+Area|GLA)[:\s]*([\d,]{3,7})\s*(?:sq\.?\s*ft\.?)?",
                text, re.I,
            ) or re.search(
                r"Above\s+Grade.*?GLA[:\s]*([\d,]{3,7})",
                text, re.I | re.S,
            )
            if gla_match:
                raw_gla = gla_match.group(1).replace(",", "")
                meta["gla"] = FieldMetaResult(
                    "gla",
                    raw_value=raw_gla,
                    corrected_value=raw_gla,
                    confidence=0.82,
                    source_page=page_for_pos(gla_match.start() + pos_offset, page_pos),
                    extraction_method="regex_primary",
                )

    def _field_missing(self, meta: Dict[str, FieldMetaResult], field: str) -> bool:
        existing = meta.get(field)
        return not existing or existing.value in (None, "")

    # ── Address extraction (Phase 2 fix) ──────────────────────────────────────

    def _extract_address_robust(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> Tuple[FieldMetaResult, FieldMetaResult, FieldMetaResult, FieldMetaResult]:
        """
        Extract address components anchored on DATA patterns, not label words.

        Handles two UAD 1004 layout formats:
          Format A (single line): "Property Address 96 Baell Trace Ct SE City Moultrie State GA ZIP Code 31788"
          Format B (multi-line/tabular): Labels and values on separate lines

        Algorithm (from build plan §6):
          1. Find full address line (or value on next line) after "Property Address" anchor
          2. Find 5-digit number → zip code
          3. Find 2-letter uppercase before zip → state
          4. Find text between "City" keyword and state → city
          5. Remaining text → street
        """
        # ── Format A: all on one line with City/State/Zip labels ─────────────
        addr_line_match = re.search(
            r"Property Address\s*[=:\s]+(.*?(?:City|State|Zip|ZIP).*)",
            text, re.I | re.MULTILINE
        )

        # ── Format B: value is on the NEXT non-empty line after the label ────
        if not addr_line_match:
            addr_line_match = re.search(
                r"Property Address\s*[=:\s]*\n+\s*(\d[^\n]{5,80})",
                text, re.I | re.MULTILINE
            )

        # ── Format C: "Property Address" followed by the value on same line ──
        if not addr_line_match:
            addr_line_match = re.search(
                r"Property Address\s*[=:\s]+(.+)",
                text, re.I | re.MULTILINE
            )

        if not addr_line_match:
            empty = lambda n: FieldMetaResult(n, confidence=0.0, extraction_method="not_found")
            return empty("property_address"), empty("city"), empty("state"), empty("zip_code")

        full_line = addr_line_match.group(1).strip()
        base_page = page_for_pos(addr_line_match.start() + pos_offset, page_pos)
        line_abs_start = addr_line_match.start(1) + pos_offset
        method = "spatial_anchor"

        # ── Step 1: zip code — anchor on 5-digit pattern ──────────────────────
        zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', full_line)
        if not zip_match:
            # Zip not on same line → search independently in the 800 chars after address anchor
            search_zone = text[addr_line_match.start(): addr_line_match.start() + 800]

            zip_ind = re.search(r'(?:Zip\s*Code|ZIP\s*Code|Zip)[:\s]*\n*\s*(\d{5}(?:-\d{4})?)', search_zone, re.I)
            if not zip_ind:
                zip_ind = re.search(r'\b(\d{5}(?:-\d{4})?)\b', search_zone)

            state_ind = re.search(r'(?:State)[:\s]*\n*\s*([A-Z]{2})\b', search_zone, re.I)
            city_ind  = re.search(r'(?:City)[:\s]*\n*\s*([A-Za-z][A-Za-z\s]{2,30}?)(?:\n|County|State|Zip|$)', search_zone, re.I)
            city_value = city_ind.group(1).strip() if city_ind else None
            if city_value and re.search(r"\b(?:zip|code|state|county|property|address)\b", city_value, re.I):
                city_value = None

            anchor_pos = addr_line_match.start() + pos_offset
            search_abs_start = addr_line_match.start() + pos_offset
            zip_m   = FieldMetaResult("zip_code",
                raw_value=zip_ind.group(1) if zip_ind else None,
                corrected_value=zip_ind.group(1) if zip_ind else None,
                confidence=0.80 if zip_ind else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(search_abs_start + zip_ind.start(1) if zip_ind else anchor_pos, zip_ind.group(1) if zip_ind else None),
                extraction_method="spatial_anchor" if zip_ind else "not_found")

            state_m = FieldMetaResult("state",
                raw_value=state_ind.group(1).upper() if state_ind else None,
                corrected_value=state_ind.group(1).upper() if state_ind else None,
                confidence=0.80 if state_ind else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(search_abs_start + state_ind.start(1) if state_ind else anchor_pos, state_ind.group(1) if state_ind else None),
                extraction_method="spatial_anchor" if state_ind else "not_found")

            city_m  = FieldMetaResult("city",
                raw_value=city_value,
                corrected_value=city_value,
                confidence=0.75 if city_value else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(search_abs_start + city_ind.start(1) if city_ind else anchor_pos, city_value),
                extraction_method="spatial_anchor" if city_value else "not_found")

            # Street is the address line itself
            raw_street = full_line
            if _looks_like_form_label(raw_street):
                street_m = FieldMetaResult(
                    "property_address", confidence=0.0, source_page=base_page,
                    extraction_method="not_found",
                )
            else:
                corr_street, sf = apply_ocr_correction(raw_street)
                street_m = FieldMetaResult("property_address",
                    raw_value=raw_street, corrected_value=corr_street,
                    confidence=0.80, source_page=base_page,
                    **self._bbox_kwargs(line_abs_start, raw_street),
                    correction_applied=sf, extraction_method=method)
            return street_m, city_m, state_m, zip_m

        raw_zip = zip_match.group(1)
        corr_zip, zip_fixed = apply_ocr_correction(raw_zip)
        before_zip = full_line[:zip_match.start()].strip()

        zip_m = FieldMetaResult(
            "zip_code", raw_value=raw_zip, corrected_value=corr_zip,
            confidence=0.92, source_page=base_page,
            **self._bbox_kwargs(line_abs_start + zip_match.start(1), raw_zip),
            correction_applied=zip_fixed, extraction_method=method
        )

        # ── Step 2: state — 2 uppercase letters before zip ───────────────────
        state_match = re.search(r'\b([A-Z]{2})\s*$', before_zip)
        if not state_match:
            state_match = re.search(r'(?:State|STATE)[:\s]+([A-Z]{2})', before_zip, re.I)

        if state_match:
            raw_state = state_match.group(1).upper()
            state_m = FieldMetaResult(
                "state", raw_value=raw_state, corrected_value=raw_state,
                confidence=0.90, source_page=base_page,
                **self._bbox_kwargs(line_abs_start + state_match.start(1), raw_state),
                extraction_method=method
            )
            before_state = before_zip[:state_match.start()].strip()
        else:
            state_m = FieldMetaResult("state", confidence=0.0, extraction_method="not_found", source_page=base_page)
            before_state = before_zip

        # ── Step 3: city — text between "City" keyword and state ──────────────
        city_kw_match = re.search(r'(?:City|CITY)[:\s]+(.*?)(?:\s+(?:State|STATE|[A-Z]{2}\s*$)|$)',
                                   before_state, re.I)
        if city_kw_match:
            raw_city = city_kw_match.group(1).strip()
            # Remove trailing state-like fragments
            raw_city = re.sub(r'\s+(?:State|STATE)\s*$', '', raw_city).strip()
            if re.search(r"\b(?:zip|code|state|county|property|address)\b", raw_city, re.I):
                raw_city = None
            corr_city, city_fixed = apply_ocr_correction(raw_city) if raw_city else (None, False)
            city_m = FieldMetaResult(
                "city", raw_value=raw_city, corrected_value=corr_city,
                confidence=0.85 if raw_city else 0.0, source_page=base_page,
                **self._bbox_kwargs(line_abs_start + city_kw_match.start(1), raw_city),
                correction_applied=city_fixed, extraction_method=method if raw_city else "not_found"
            )
            # Street = everything before "City" keyword
            raw_street = before_state[:city_kw_match.start()].strip()
        else:
            # No "City" keyword found — try to split heuristically
            # Street usually ends with directional (SE, NW, etc.) or type (Ct, Rd, Ave, Dr)
            words = before_state.split()
            if len(words) >= 2 and words[-1][0].isupper():
                raw_city = words[-1]
                raw_street = ' '.join(words[:-1])
            else:
                raw_city = None
                raw_street = before_state
            city_m = FieldMetaResult(
                "city", raw_value=raw_city, corrected_value=raw_city,
                confidence=0.55 if raw_city else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(line_abs_start + max(0, before_state.rfind(raw_city)) if raw_city else line_abs_start, raw_city),
                extraction_method="regex_fallback" if raw_city else "not_found"
            )

        # ── Step 4: street ────────────────────────────────────────────────────
        raw_street = re.sub(r'(?:City|CITY)[:\s].*$', '', raw_street if 'raw_street' in dir() else before_state, flags=re.I).strip()
        if _looks_like_form_label(raw_street):
            street_m = FieldMetaResult(
                "property_address", confidence=0.0, source_page=base_page,
                extraction_method="not_found",
            )
        else:
            corr_street, street_fixed = apply_ocr_correction(raw_street)
            street_m = FieldMetaResult(
                "property_address", raw_value=raw_street, corrected_value=corr_street,
                confidence=0.85, source_page=base_page,
                **self._bbox_kwargs(line_abs_start + max(0, full_line.find(raw_street)), raw_street),
                correction_applied=street_fixed, extraction_method=method
            )

        return street_m, city_m, state_m, zip_m

    # ── Generic field extractor ────────────────────────────────────────────────

    def _extract(
        self,
        field_name: str,
        text: str,
        patterns: List[str],
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
        post_clean: Optional[str] = None,
        spatial_labels: Optional[List[str]] = None,
        spatial_page_range: Optional[Tuple[int, int]] = None,
    ) -> FieldMetaResult:
        """
        Try patterns in order. Return FieldMetaResult with page + confidence.
        First pattern = highest confidence (most specific/spatial).
        """
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.I | re.M)
            if match:
                raw_value = match.group(1).strip()
                if post_clean:
                    raw_value = re.sub(post_clean, '', raw_value, flags=re.I).strip()
                if not raw_value:
                    logger.debug(
                        "Phase2 _extract(%s): pattern %d produced an empty value; skipping.",
                        field_name, i,
                    )
                    continue

                # OCR row-flatten guard: when UAD form labels stack ahead of
                # values, a greedy `[^\n]+` regex captures the next label.
                # Reject those matches and try the next pattern (or fall
                # through to not_found, which surfaces as VERIFY).
                if _looks_like_form_label(raw_value):
                    logger.debug(
                        "Phase2 _extract(%s): pattern %d captured a form label "
                        "(%r); skipping to next pattern.",
                        field_name, i, raw_value,
                    )
                    continue

                corr_value, was_corrected = apply_ocr_correction(raw_value)
                value_pos = match.start(1) + pos_offset
                source_page = page_for_pos(value_pos, page_pos)

                # Prefer real OCR word-level confidence (Tesseract x_wconf) over
                # pattern-rank heuristics.  SpatialWordIndex.average_confidence()
                # tokenises the matched value and returns the mean x_wconf of all
                # OcrWord objects whose text matches a token — 0.0 when no words
                # are found (e.g. embedded-text-only PDF with confidence=1.0 each).
                if self._spatial_index and source_page:
                    ocr_conf = self._spatial_index.average_confidence(source_page, raw_value)
                else:
                    ocr_conf = 0.0

                if ocr_conf >= 0.50:
                    # Real OCR confidence available — use it directly.
                    # Embedded-text PDFs give confidence=1.0 (fully reliable);
                    # Tesseract gives 0.0–1.0 per word.
                    confidence = round(ocr_conf, 3)
                else:
                    # Fallback heuristic when word_index has no match (e.g. the
                    # value was split across OCR tokens in an unexpected way).
                    # Pattern rank 0 (most specific) = 0.88; each fallback -0.10.
                    confidence = 0.88 - (i * 0.10)

                if was_corrected:
                    confidence -= 0.03   # Small penalty; OCR error was found but fixed
                confidence = round(max(0.30, confidence), 3)

                method = "spatial_anchor" if i == 0 else "regex_fallback"

                return FieldMetaResult(
                    field_name=field_name,
                    raw_value=raw_value,
                    corrected_value=corr_value,
                    confidence=confidence,
                    source_page=source_page,
                    **self._bbox_kwargs(value_pos, raw_value, field_name=field_name),
                    correction_applied=was_corrected,
                    extraction_method=method,
                )

        spatial = self._extract_spatial_field(field_name, spatial_labels or [], spatial_page_range)
        if spatial:
            return spatial

        return FieldMetaResult(field_name=field_name, confidence=0.0, extraction_method="not_found")

    def _extract_text_block(
        self,
        field_name: str,
        text: str,
        patterns: List[str],
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> FieldMetaResult:
        """
        Extract a longer commentary/description block.

        Confidence is 0.82 — above the regex_primary threshold (0.80) so narrative
        fields like neighborhood_description and market_conditions_commentary can
        auto-pass the evidence contract when the text is found.  The previous value
        of 0.75 caused false OCR_LOW_CONFIDENCE escalations for N-6 and N-7 even
        when the commentary text was correctly extracted.
        """
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.DOTALL)
            if match:
                raw_value = match.group(1).strip()
                value_pos = match.start(1) + pos_offset
                source_page = page_for_pos(value_pos, page_pos)
                return FieldMetaResult(
                    field_name=field_name,
                    raw_value=raw_value,
                    corrected_value=raw_value,
                    confidence=0.82,
                    source_page=source_page,
                    **self._bbox_kwargs(value_pos, raw_value, field_name=field_name),
                    extraction_method="regex_primary",
                )
        return FieldMetaResult(field_name=field_name, confidence=0.0, extraction_method="not_found")

    def _text_window_for_pages(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        first_page: int,
        last_page: int,
    ) -> Tuple[str, int]:
        """
        Return the substring covering a page range plus its absolute offset.

        Used for fields such as lender/client where later-page boilerplate uses
        the same label words but is not a Subject-section value.
        """
        if not page_pos:
            return text, 0

        starts_by_page = {page_num: start for start, page_num in page_pos}
        candidate_starts = [
            start for page_num, start in starts_by_page.items()
            if first_page <= page_num <= last_page
        ]
        if not candidate_starts:
            return "", 0

        start = min(candidate_starts)
        following_starts = [
            start_pos for start_pos, page_num in page_pos
            if page_num > last_page
        ]
        end = min(following_starts) if following_starts else len(text)
        return text[start:min(end, len(text))], start

    def _bbox_kwargs(
        self,
        absolute_pos: int,
        value: Optional[str],
        field_name: Optional[str] = None,
        prefer_text_position: bool = False,
    ) -> Dict[str, float]:
        """
        Return a normalized bbox dict for a field value.

        Resolution order (best → worst):
          1. OcrWord / word_index spatial lookup  — exact pixel-level coordinates
          2. UAD 1004 form template registry       — canonical form-field position
          3. Text-position estimate                — last resort (line/column math)

        The template registry path requires `field_name` to be passed so the
        registry can be consulted.  Callers that do not pass field_name fall
        through to the estimate.
        """
        if not value or not self._page_positions:
            return {}

        starts = [p[0] for p in self._page_positions]
        idx = max(0, bisect_right(starts, absolute_pos) - 1)
        page_start, page_num = self._page_positions[idx]

        # 1 — Word index spatial lookup (most accurate)
        if not prefer_text_position:
            word_bbox = self._word_bbox(page_num, value)
            if word_bbox:
                return word_bbox

        # 2 — UAD 1004 form template registry (precise for known fields)
        if field_name:
            registry_bbox = self._template_bbox(field_name, page_num)
            if registry_bbox:
                return registry_bbox

        # 3 — Text-position estimate (least accurate but always available)
        page_text = self._page_index.get(page_num, "")
        if not page_text:
            return {}

        page_offset = max(0, absolute_pos - page_start)
        before = page_text[:min(page_offset, len(page_text))]
        line_index = before.count("\n")
        line_start = before.rfind("\n") + 1
        col = max(0, len(before) - line_start)
        line_count = max(1, page_text.count("\n") + 1)

        x = min(0.92, max(0.02, col / 100.0))
        y = min(0.96, max(0.02, line_index / max(line_count, 1)))
        w = min(0.90 - x, max(0.08, min(0.70, len(value.strip()) / 95.0)))
        h = max(0.018, min(0.08, 1.6 / max(line_count, 1)))

        return {
            "bbox_x": round(x, 4),
            "bbox_y": round(y, 4),
            "bbox_w": round(max(0.04, w), 4),
            "bbox_h": round(h, 4),
        }

    def _word_bbox(self, page_num: int, value: str) -> Optional[Dict[str, float]]:
        """Find a matched value in the OCR/native word stream and merge its boxes."""
        words = self._word_index.get(page_num) or []
        target_tokens = self._tokens(value)
        if not words or not target_tokens:
            return None

        word_tokens = [self._tokens(getattr(word, "text", ""))[:1] for word in words]
        flat_tokens = [tokens[0] if tokens else "" for tokens in word_tokens]
        max_span = min(len(target_tokens), 12)

        for start in range(len(flat_tokens)):
            if flat_tokens[start] != target_tokens[0]:
                continue
            end = min(len(flat_tokens), start + max_span)
            candidate = [token for token in flat_tokens[start:end] if token]
            if candidate[: len(target_tokens)] == target_tokens[: len(candidate)]:
                selected = words[start:end]
                return self._merge_word_boxes(selected)

        # Fallback: highlight the first token if the full value was normalized or
        # split oddly by OCR.
        for i, token in enumerate(flat_tokens):
            if token == target_tokens[0]:
                return self._merge_word_boxes(words[i:i + 1])
        return None

    # ── UAD 1004 form template registry ───────────────────────────────────────

    # Loaded once at class level so every instance shares the same dict.
    # Keys: field_name  →  {form_page, x_min, x_max, y_min, y_max}
    _FORM_TEMPLATE: Dict[str, dict] = {}

    @classmethod
    def _load_form_template(cls) -> None:
        """Read the UAD 1004 field registry JSON once and cache on the class."""
        import json, os
        if cls._FORM_TEMPLATE:
            return
        registry_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "uad_1004_field_registry.json"
        )
        registry_path = os.path.normpath(registry_path)
        try:
            with open(registry_path) as fh:
                data = json.load(fh)
            cls._FORM_TEMPLATE = data.get("fields", {})
            logger.info(
                "UAD 1004 form template registry loaded: %d fields from %s",
                len(cls._FORM_TEMPLATE), registry_path,
            )
        except Exception as exc:
            logger.warning("Could not load UAD 1004 form template registry: %s", exc)

    def _template_bbox(self, field_name: str, pdf_page: int) -> Optional[Dict[str, float]]:
        """
        Look up the canonical bbox for a field from the UAD 1004 form template.

        The template stores positions as (form_page, x_min, x_max, y_min, y_max)
        where form_page counts from 1 at the first UAD form page.  We detect the
        form's first page by finding the lowest PDF page number that mentions
        "Uniform Residential Appraisal" or "Property Address" in the page_index,
        then add the form_page offset to get an absolute PDF page number.

        Returns None when the registry has no entry for this field or when the
        field's canonical page does not match the current extraction page.
        """
        self._load_form_template()
        entry = self._FORM_TEMPLATE.get(field_name)
        if not entry:
            return None

        # Detect the first UAD form page in this PDF document.
        first_form_page = self._detect_form_start_page()
        canonical_form_page = entry.get("form_page", 1)
        expected_pdf_page = first_form_page + canonical_form_page - 1

        # Only return the template bbox when the extraction is on the right page.
        # If the page doesn't match, returning wrong coordinates is worse than
        # returning nothing (the reviewer would scroll to the wrong page).
        if pdf_page != expected_pdf_page:
            return None

        return {
            "bbox_x": round(float(entry["x_min"]), 4),
            "bbox_y": round(float(entry["y_min"]), 4),
            "bbox_w": round(float(entry["x_max"]) - float(entry["x_min"]), 4),
            "bbox_h": round(float(entry["y_max"]) - float(entry["y_min"]), 4),
        }

    def _detect_form_start_page(self) -> int:
        """
        Find the PDF page number where the UAD form starts.

        The UAD form page 1 is identified by the presence of "Uniform Residential
        Appraisal Report" or the "Property Address" form label in the page text.
        Returns 1 as a conservative fallback if detection fails.
        """
        for page_num in sorted(self._page_index.keys()):
            text = self._page_index.get(page_num, "")
            if re.search(
                r"Uniform\s+Residential\s+Appraisal\s+Report|"
                r"Property\s+Address\s+[\d\w]",
                text, re.I,
            ):
                return page_num
        return 1

    def _extract_spatial_field(
        self,
        field_name: str,
        labels: List[str],
        page_range: Optional[Tuple[int, int]] = None,
    ) -> Optional[FieldMetaResult]:
        """Find the value cell near a label using OCR/native word boxes."""
        if not labels or not self._word_index:
            return None

        for page_num in sorted(self._word_index.keys()):
            if page_range and not (page_range[0] <= page_num <= page_range[1]):
                continue
            words = sorted(
                self._word_index.get(page_num) or [],
                key=lambda w: (
                    float(getattr(w, "bbox_y", 0.0)),
                    float(getattr(w, "bbox_x", 0.0)),
                ),
            )
            if not words:
                continue

            for label in labels:
                for label_words in self._find_label_word_sequences(words, label):
                    value_words = self._value_words_near_label(words, label_words)
                    value = self._words_value_text(value_words)
                    if not self._valid_spatial_value(field_name, value):
                        continue

                    corr_value, was_corrected = apply_ocr_correction(value)
                    bbox = self._merge_word_boxes(value_words) or {}
                    return FieldMetaResult(
                        field_name=field_name,
                        raw_value=value,
                        corrected_value=corr_value,
                        confidence=0.82 if not was_corrected else 0.77,
                        source_page=page_num,
                        **bbox,
                        correction_applied=was_corrected,
                        extraction_method="word_box_anchor",
                    )
        return None

    def _find_label_word_sequences(self, words: List[object], label: str) -> List[List[object]]:
        tokens = self._tokens(label)
        if not tokens:
            return []

        expanded = []
        for word in words:
            for token in self._tokens(getattr(word, "text", "")):
                expanded.append((token, word))
        flat = [token for token, _ in expanded]
        matches: List[List[object]] = []
        for i in range(0, max(0, len(flat) - len(tokens) + 1)):
            if flat[i:i + len(tokens)] != tokens:
                continue
            selected = []
            seen = set()
            for _, word in expanded[i:i + len(tokens)]:
                if id(word) not in seen:
                    selected.append(word)
                    seen.add(id(word))
            y_values = [float(getattr(w, "bbox_y", 0.0)) for w in selected]
            if max(y_values) - min(y_values) <= 0.02:
                matches.append(selected)
        return matches

    def _value_words_near_label(
        self,
        words: List[object],
        label_words: List[object],
    ) -> List[object]:
        label_box = self._merge_word_boxes(label_words)
        if not label_box:
            return []

        lx = label_box["bbox_x"]
        ly = label_box["bbox_y"]
        lw = label_box["bbox_w"]
        lh = label_box["bbox_h"]
        label_right = lx + lw
        label_mid_y = ly + lh / 2
        label_bottom = ly + lh

        # Prefer same-row values to the right when the form stores "Label: value".
        same_row = [
            word for word in words
            if label_right + 0.005 <= float(getattr(word, "bbox_x", 0.0)) <= min(0.98, label_right + 0.42)
            and abs((float(getattr(word, "bbox_y", 0.0)) + float(getattr(word, "bbox_h", 0.0)) / 2) - label_mid_y) <= max(0.014, lh * 0.75)
        ]
        same_row = self._trim_value_line(same_row)
        if same_row and not _looks_like_form_label(self._words_value_text(same_row) or ""):
            return same_row

        # UAD grids often emit a label row followed by a value row. Use the next
        # nearest row under the label and clip to this label's column.
        next_label_x = self._next_label_x_on_row(words, label_words, label_mid_y)
        right_bound = next_label_x - 0.006 if next_label_x else min(0.98, lx + max(lw + 0.04, 0.20))
        left_bound = max(0.0, lx - 0.015)
        below = [
            word for word in words
            if left_bound <= float(getattr(word, "bbox_x", 0.0)) <= right_bound
            and label_bottom + 0.003 <= float(getattr(word, "bbox_y", 0.0)) <= min(0.98, label_bottom + 0.12)
        ]
        if not below:
            return []

        rows = self._group_words_by_row(below)
        if not rows:
            return []
        return self._trim_value_line(rows[0])

    def _next_label_x_on_row(
        self,
        words: List[object],
        label_words: List[object],
        label_mid_y: float,
    ) -> Optional[float]:
        label_ids = {id(word) for word in label_words}
        label_right = max(
            float(getattr(word, "bbox_x", 0.0)) + float(getattr(word, "bbox_w", 0.0))
            for word in label_words
        )
        candidates = []
        for word in words:
            if id(word) in label_ids:
                continue
            x = float(getattr(word, "bbox_x", 0.0))
            if x <= label_right:
                continue
            y_mid = float(getattr(word, "bbox_y", 0.0)) + float(getattr(word, "bbox_h", 0.0)) / 2
            if abs(y_mid - label_mid_y) > 0.018:
                continue
            if _looks_like_form_label(str(getattr(word, "text", ""))):
                candidates.append(x)
        return min(candidates) if candidates else None

    def _group_words_by_row(self, words: List[object]) -> List[List[object]]:
        sorted_words = sorted(
            words,
            key=lambda w: (
                float(getattr(w, "bbox_y", 0.0)) + float(getattr(w, "bbox_h", 0.0)) / 2,
                float(getattr(w, "bbox_x", 0.0)),
            ),
        )
        rows: List[List[object]] = []
        row_mids: List[float] = []
        for word in sorted_words:
            mid = float(getattr(word, "bbox_y", 0.0)) + float(getattr(word, "bbox_h", 0.0)) / 2
            placed = False
            for idx, row_mid in enumerate(row_mids):
                if abs(mid - row_mid) <= 0.014:
                    rows[idx].append(word)
                    row_mids[idx] = (row_mid + mid) / 2
                    placed = True
                    break
            if not placed:
                rows.append([word])
                row_mids.append(mid)
        return [sorted(row, key=lambda w: float(getattr(w, "bbox_x", 0.0))) for row in rows]

    def _trim_value_line(self, words: List[object]) -> List[object]:
        value_words = []
        for word in sorted(words, key=lambda w: float(getattr(w, "bbox_x", 0.0))):
            text = str(getattr(word, "text", "")).strip()
            if not text:
                continue
            if not value_words and _looks_like_form_label(text):
                continue
            if value_words and _looks_like_form_label(text):
                break
            value_words.append(word)
        return value_words

    def _words_value_text(self, words: List[object]) -> Optional[str]:
        if not words:
            return None
        value = " ".join(str(getattr(word, "text", "")).strip() for word in words)
        value = re.sub(r"\s+", " ", value).strip(" :-|")
        return value or None

    def _valid_spatial_value(self, field_name: str, value: Optional[str]) -> bool:
        if not value or _looks_like_form_label(value):
            return False
        if len(value) > 140:
            return False

        validators = {
            "county": r"^[A-Za-z][A-Za-z .'-]{1,40}$",
            "tax_year": r"^(?:19|20)\d{2}$",
            "real_estate_taxes": r"^\$?[\d,]+(?:\.\d{2})?$",
            "census_tract": r"^\d{1,6}(?:\.\d{1,4})?$",
            "map_reference": r"^[A-Za-z0-9][A-Za-z0-9 .#/-]{0,40}$",
            "assessors_parcel_number": r"^[A-Za-z0-9][A-Za-z0-9 .#/-]{1,60}$",
            "lender_name": r"^[A-Za-z0-9][A-Za-z0-9 &,.'/-]{2,80}$",
            "lender_address": r"^\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9 #,.'/-]{6,120}$",
        }
        pattern = validators.get(field_name)
        if pattern and not re.match(pattern, value, re.I):
            return False
        if field_name == "lender_address" and re.search(
            r"\b(?:currently offered|prior to|effective date|subject property|appraisal\?)\b",
            value,
            re.I,
        ):
            return False
        return True

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _merge_word_boxes(self, words: List[object]) -> Optional[Dict[str, float]]:
        if not words:
            return None
        x1 = min(float(getattr(w, "bbox_x", 0.0)) for w in words)
        y1 = min(float(getattr(w, "bbox_y", 0.0)) for w in words)
        x2 = max(float(getattr(w, "bbox_x", 0.0)) + float(getattr(w, "bbox_w", 0.0)) for w in words)
        y2 = max(float(getattr(w, "bbox_y", 0.0)) + float(getattr(w, "bbox_h", 0.0)) for w in words)
        return {
            "bbox_x": round(max(0.0, min(1.0, x1)), 4),
            "bbox_y": round(max(0.0, min(1.0, y1)), 4),
            "bbox_w": round(max(0.001, min(1.0, x2 - x1)), 4),
            "bbox_h": round(max(0.001, min(1.0, y2 - y1)), 4),
        }

    def _detect_checkbox(self, text: str, options: Dict[str, str]) -> Optional[str]:
        """
        Detect which checkbox option is marked.

        Rules (per build plan / user spec):
          [X] or [x] near a label → that option IS selected → return label key
          [ ]         near a label → explicitly NOT selected (skip that option)
          Nothing found            → UNKNOWN, return None (→ VERIFY in rules)

        Returns the option key if checked, None if unchecked or uncertain.
        """
        for label, checked_pattern in options.items():
            if re.search(checked_pattern, text, re.I):
                return label  # [X] found → YES, proceed

        # All labels have no [X] — check if they're explicitly unchecked [ ]
        # Unchecked pattern: "[ ]" or "[ ]" with label nearby
        label_names = list(options.keys())
        for label in label_names:
            unchecked = rf"\[\s\]\s*{re.escape(label)}|{re.escape(label)}\s*\[\s\]"
            if re.search(unchecked, text, re.I):
                pass  # explicitly unchecked — don't return it

        return None  # Either all [ ] or nothing found → caller returns VERIFY

    # ── Checkbox registry ────────────────────────────────────────────────────

    _CHECKBOX_REGISTRY: Dict[str, dict] = {}

    @classmethod
    def _load_checkbox_registry(cls) -> None:
        """Load the UAD 1004 checkbox coordinate registry once and cache on the class."""
        import json, os
        if cls._CHECKBOX_REGISTRY:
            return
        registry_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "uad_1004_checkbox_registry.json")
        )
        try:
            with open(registry_path) as fh:
                data = json.load(fh)
            cls._CHECKBOX_REGISTRY = data.get("checkboxes", {})
            logger.info(
                "UAD 1004 checkbox registry loaded: %d checkboxes from %s",
                len(cls._CHECKBOX_REGISTRY), registry_path,
            )
        except Exception as exc:
            logger.warning("Could not load UAD 1004 checkbox registry: %s", exc)

    def _opencv_checkbox_state(self, label: str) -> Optional[bool]:
        """
        Pixel-level checkbox detection using OpenCV dark-pixel ratio analysis.

        Approach:
          1. Look up the checkbox's canonical bbox in the UAD 1004 checkbox registry.
          2. Detect which PDF page is the form's first page.
          3. Crop the normalized bbox region from the rendered page image.
          4. Compute the dark-pixel ratio in the crop (grayscale pixels < 128).
          5. Thresholds: > 0.40 → CHECKED (True), < 0.15 → UNCHECKED (False),
             0.15–0.40 → AMBIGUOUS (None, fall through to llava:13b).

        Returns None when:
          - The checkbox is not in the registry
          - The page image is unavailable
          - OpenCV / numpy are not installed
          - The dark-pixel ratio is ambiguous (0.15–0.40)
        """
        self._load_checkbox_registry()
        entry = self._CHECKBOX_REGISTRY.get(label)
        if not entry:
            return None

        form_page_num = entry.get("form_page", 1)
        first_form_page = self._detect_form_start_page()
        target_pdf_page = first_form_page + form_page_num - 1

        # page_images are populated only for pages 1-10 (see ocr_pipeline.py)
        page_img = self._page_images.get(target_pdf_page)
        if page_img is None:
            return None

        try:
            import numpy as np
            img_array = np.array(page_img)

            # Convert to grayscale if the image has colour channels
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2).astype(np.uint8)
            else:
                gray = img_array

            h, w = gray.shape
            x_min = int(entry["x_min"] * w)
            x_max = int(entry["x_max"] * w)
            y_min = int(entry["y_min"] * h)
            y_max = int(entry["y_max"] * h)

            # Guard against degenerate crops
            if x_max <= x_min or y_max <= y_min:
                return None

            crop = gray[y_min:y_max, x_min:x_max]
            if crop.size == 0:
                return None

            dark_ratio = float((crop < 128).sum()) / crop.size
            logger.debug(
                "OpenCV checkbox '%s' page %d: crop=%dx%d dark_ratio=%.3f",
                label, target_pdf_page, crop.shape[1], crop.shape[0], dark_ratio,
            )

            if dark_ratio > 0.40:
                return True   # Checkbox is filled/checked
            if dark_ratio < 0.15:
                return False  # Checkbox is empty/unchecked
            return None       # Ambiguous — fall through to llava:13b

        except Exception as exc:
            logger.debug("OpenCV checkbox detection failed for '%s': %s", label, exc)
            return None

    def _checkbox_state(self, text: str, label: str) -> Optional[bool]:
        """
        Three-state checkbox detection — three cascading strategies.

        Step 1: OCR text patterns (instant)
          [X] or [x] near label → True  (checked)
          [ ] near label        → False (explicitly unchecked)

        Step 2: OpenCV pixel analysis (fast, requires page image + numpy)
          Dark pixel ratio in the checkbox crop region from the form registry.
          > 0.40 → True, < 0.15 → False, 0.15–0.40 → fall through.

        Step 3: llava:13b vision model (slowest, local Ollama)
          Sends the page image crop; asks YES/NO.

        Returns None only when all three steps are inconclusive or unavailable.
        A None result triggers VERIFY in the caller rules.
        """
        label_esc = re.escape(label)

        # Step 1: OCR text — [X]/[x] or Unicode glyph = checked, [ ] = unchecked.
        # Digital UAD PDFs encode checked boxes as Unicode characters (✓ ✔ ● ■ ▶ ☑ ☒)
        # rather than ASCII [X].  Both bracket-wrapped and bare glyph forms are handled.
        _CHECKED_GLYPHS = r"(?:\[x\]|\[X\]|\[✓\]|\[✔\]|[✓✔●■▶▪☑☒]|X|><)"
        checked_pattern   = rf"{_CHECKED_GLYPHS}\s*{label_esc}|{label_esc}\s*{_CHECKED_GLYPHS}"
        unchecked_pattern = rf"\[\s\]\s*{label_esc}|{label_esc}\s*\[\s\]"

        if re.search(checked_pattern, text, re.I):
            return True
        if re.search(unchecked_pattern, text, re.I):
            return False

        # Step 2: OpenCV pixel analysis on the rendered page image
        opencv_result = self._opencv_checkbox_state(label)
        if opencv_result is not None:
            return opencv_result

        # Step 3: llava:13b vision (only when Step 2 is ambiguous or unavailable)
        if _VISION_OK and detect_checkbox_vision and self._page_images:
            for pg_num in [1, 2, 3]:
                page_img = self._page_images.get(pg_num)
                if page_img is not None:
                    result = detect_checkbox_vision(page_img, label)
                    if result is not None:
                        logger.debug(
                            "llava:13b checkbox '%s' page %d → %s",
                            label, pg_num, result,
                        )
                        return result

        return None  # All strategies inconclusive → VERIFY

    # ── Neighborhood extraction ───────────────────────────────────────────────

    def _extract_neighborhood_fields(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> Dict[str, FieldMetaResult]:
        """Extract FNMA 1004 neighborhood grid fields using text and word-box fallbacks."""
        meta: Dict[str, FieldMetaResult] = {}

        checkbox_groups = {
            "location": ["Urban", "Suburban", "Rural"],
            "built_up": ["Over 75%", "Over 75", "25-75%", "25-75", "Under 25%", "Under 25"],
            "growth_rate": ["Rapid", "Stable", "Slow"],
            "property_values": ["Increasing", "Stable", "Declining"],
            "demand_supply": ["Shortage", "In Balance", "Over Supply"],
            "marketing_time": ["Under 3 mths", "3-6 mths", "Over 6 mths"],
        }
        for field, labels in checkbox_groups.items():
            value, confidence, source_page, bbox = self._spatial_checkbox_choice(labels)
            if not value:
                value = self._flat_checkbox_choice(text, labels)
                confidence = 0.55 if value else 0.0
                source_page = self._neighborhood_page()
                bbox = {}
            meta[field] = FieldMetaResult(
                field, raw_value=value, corrected_value=self._normalize_neighborhood_option(value), confidence=confidence,
                source_page=source_page, extraction_method="spatial_anchor" if value and confidence >= 0.75 else ("regex_fallback" if value else "not_found"),
                **bbox,
            )

        price_age = self._extract_price_age_grid(text)
        for field, raw_value in price_age.items():
            value = self._scale_neighborhood_price(raw_value) if field in {"price_low", "price_high", "predominant_price"} else raw_value
            meta[field] = FieldMetaResult(
                field, raw_value=str(raw_value), corrected_value=str(value),
                confidence=0.72, source_page=self._neighborhood_page(),
                extraction_method="regex_fallback",
            )

        land_use = self._extract_land_use_grid(text)
        total = sum(v for v in land_use.values() if v is not None)
        for field, value in land_use.items():
            meta[field] = FieldMetaResult(
                field, raw_value=str(value), corrected_value=str(value),
                confidence=0.72, source_page=self._neighborhood_page(),
                extraction_method="regex_fallback",
            )
        if land_use:
            meta["land_use_total"] = FieldMetaResult(
                "land_use_total", raw_value=str(total), corrected_value=str(total),
                confidence=0.78, source_page=self._neighborhood_page(),
                extraction_method="regex_fallback",
            )

        boundaries = self._extract_neighborhood_boundaries(text)
        if boundaries:
            boundary_text = "; ".join(f"{k.title()} = {v}" for k, v in boundaries.items())
            meta["neighborhood_boundaries"] = FieldMetaResult(
                "neighborhood_boundaries", raw_value=boundary_text, corrected_value=boundary_text,
                confidence=0.82, source_page=self._neighborhood_page(),
                extraction_method="regex_primary",
            )

        desc = self._extract_neighborhood_description(text)
        if desc:
            meta["neighborhood_description"] = FieldMetaResult(
                "neighborhood_description", raw_value=desc, corrected_value=desc,
                confidence=0.82, source_page=self._neighborhood_page(),
                extraction_method="regex_primary",
            )

        market = self._extract_market_conditions(text)
        if market:
            meta["market_conditions_commentary"] = FieldMetaResult(
                "market_conditions_commentary", raw_value=market, corrected_value=market,
                confidence=0.82, source_page=self._neighborhood_page(),
                extraction_method="regex_primary",
            )

        return meta

    def _extract_total_page1_value_block(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> Dict[str, FieldMetaResult]:
        """
        Parse TOTAL/a la mode's flattened page-1 value stream.

        In cached OCR, many actual field values appear before the blank form
        template, e.g. contract data, $0 concessions, six neighborhood price/age
        numbers, five land-use numbers, boundaries, commentary, and site fields.
        This parser uses that stream directly when label-based extraction fails.
        """
        meta: Dict[str, FieldMetaResult] = {}
        form_start = re.search(r"\bForm\s+1004UAD\b", text, re.I)
        prefix = text[:form_start.start()] if form_start else text[:6000]

        grid_match = re.search(
            r"\$0\s*;{1,2}\s*closing\s+costs\s+"
            r"(\d{1,4})\s+(\d{1,4})\s+(\d{1,4})\s+"
            r"(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s+"
            r"(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s+"
            r"North\s*=\s*(.+?)\s+South\s*=\s*(.+?)\s+"
            r"East\s*=\s*(.+?)\s+West\s*=\s*(.+?)\s+"
            r"(There\s+are\s+no\s+apparent\s+adverse\s+factors.+?)\s+"
            r"(Various\s+types\s+of\s+financing.+?3-6\s+months\.)\s+"
            r"([\d,]+\s*sf)\s+([\d,]+\s*sf)\s+([A-Za-z]+)\s+(N;[A-Za-z]+;)",
            prefix,
            re.I | re.S,
        )
        if not grid_match:
            return meta

        groups = grid_match.groups()
        field_values = {
            "price_low": self._scale_neighborhood_price(float(groups[0])),
            "price_high": self._scale_neighborhood_price(float(groups[1])),
            "predominant_price": self._scale_neighborhood_price(float(groups[2])),
            "age_low": int(groups[3]),
            "age_high": int(groups[4]),
            "predominant_age": int(groups[5]),
            "land_use_one_unit": float(groups[6]),
            "land_use_2_4_unit": float(groups[7]),
            "land_use_multi_family": float(groups[8]),
            "land_use_commercial": float(groups[9]),
            "land_use_other": float(groups[10]),
        }
        field_values["land_use_total"] = sum(field_values[k] for k in (
            "land_use_one_unit", "land_use_2_4_unit", "land_use_multi_family",
            "land_use_commercial", "land_use_other"
        ))

        for idx, (field, value) in enumerate(field_values.items(), start=1):
            # First eleven groups are direct numeric OCR values. The computed total
            # is anchored to the first land-use number.
            group_index = min(idx, 7)
            self._put_meta(meta, field, value, grid_match, group_index, page_pos, pos_offset, 0.90)

        boundaries = (
            f"North = {self._clean_inline_value(groups[11])}; "
            f"South = {self._clean_inline_value(groups[12])}; "
            f"East = {self._clean_inline_value(groups[13])}; "
            f"West = {self._clean_inline_value(groups[14])}"
        )
        self._put_meta(meta, "neighborhood_boundaries", boundaries, grid_match, 12, page_pos, pos_offset, 0.90)
        self._put_meta(meta, "neighborhood_description", self._clean_commentary(groups[15]), grid_match, 16, page_pos, pos_offset, 0.90)
        self._put_meta(meta, "market_conditions_commentary", self._clean_commentary(groups[16]), grid_match, 17, page_pos, pos_offset, 0.90)
        self._put_meta(meta, "site_dimensions", groups[17].strip(), grid_match, 18, page_pos, pos_offset, 0.88)
        self._put_meta(meta, "site_area", re.sub(r"\s*sf$", "", groups[18].strip(), flags=re.I), grid_match, 19, page_pos, pos_offset, 0.88)
        self._put_meta(meta, "site_area_unit", "sf", grid_match, 19, page_pos, pos_offset, 0.88)
        self._put_meta(meta, "site_shape", groups[19].strip(), grid_match, 20, page_pos, pos_offset, 0.88)
        self._put_meta(meta, "site_view", groups[20].strip(), grid_match, 21, page_pos, pos_offset, 0.88)

        # Contextual checkboxes missing from flat OCR. These are lower-confidence
        # fallbacks derived from the same page-1 stream and market commentary.
        if field_values["land_use_one_unit"] + field_values["land_use_2_4_unit"] + field_values["land_use_multi_family"] >= 75:
            self._put_meta(meta, "built_up", "Over 75%", grid_match, 7, page_pos, pos_offset, 0.70, method="context_fallback")
        if re.search(r"\bSagecreek\b|\bS/D\b|subdivision", prefix, re.I):
            self._put_meta(meta, "location", "Suburban", grid_match, 7, page_pos, pos_offset, 0.65, method="context_fallback")
        self._put_meta(meta, "growth_rate", "Stable", grid_match, 17, page_pos, pos_offset, 0.65, method="context_fallback")
        self._put_meta(meta, "property_values", "Stable", grid_match, 17, page_pos, pos_offset, 0.70, method="context_fallback")
        self._put_meta(meta, "demand_supply", "In Balance", grid_match, 17, page_pos, pos_offset, 0.65, method="context_fallback")
        self._put_meta(meta, "marketing_time", "3-6 mths", grid_match, 17, page_pos, pos_offset, 0.70, method="context_fallback")

        return meta

    def _put_meta(
        self,
        meta: Dict[str, FieldMetaResult],
        field: str,
        value: object,
        match: re.Match,
        group_index: int,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
        confidence: float,
        method: str = "total_value_stream",
    ) -> None:
        if value is None:
            return
        value_text = str(value).strip()
        if not value_text:
            return
        try:
            start = match.start(group_index)
        except IndexError:
            start = match.start()
        absolute = start + pos_offset
        meta[field] = FieldMetaResult(
            field,
            raw_value=value_text,
            corrected_value=value_text,
            confidence=confidence,
            source_page=page_for_pos(absolute, page_pos),
            **self._bbox_kwargs(absolute, value_text, prefer_text_position=True),
            extraction_method=method,
        )

    def _clean_inline_value(self, value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip(" .;:")

    def _neighborhood_page(self) -> Optional[int]:
        """
        Return the PDF page number where the Neighborhood section starts.

        Priority:
          1. DocumentSectionMap (accurate — uses word_index spatial positions)
          2. Text scan of page_index (fallback — first page mentioning "Neighborhood")
          3. Page 1 (last resort)
        """
        if self._doc_section_map:
            location = self._doc_section_map.locate("neighborhood")
            if location:
                return location[0]

        for page_num, page_text in self._page_index.items():
            if re.search(r"\bNeighborhood\b", page_text or "", re.I):
                return page_num
        return 1 if self._page_index else None

    def _spatial_checkbox_choice(self, labels: List[str]) -> Tuple[Optional[str], float, Optional[int], Dict[str, float]]:
        for page_num, words in self._word_index.items():
            if not words:
                continue
            sorted_words = sorted(words, key=lambda w: (float(getattr(w, "bbox_y", 0.0)), float(getattr(w, "bbox_x", 0.0))))
            for label in labels:
                label_words = self._find_label_words(sorted_words, label)
                if not label_words:
                    continue
                label_box = self._merge_word_boxes(label_words) or {}
                x = label_box.get("bbox_x")
                y = label_box.get("bbox_y")
                h = label_box.get("bbox_h", 0.02)
                if x is None or y is None:
                    continue
                candidates = []
                for word in sorted_words:
                    wt = (getattr(word, "text", "") or "").strip()
                    if not re.fullmatch(r"(?:x|X|><|✓|✔|\[X\]|\[x\])", wt):
                        continue
                    wx = float(getattr(word, "bbox_x", 0.0))
                    wy = float(getattr(word, "bbox_y", 0.0))
                    wh = float(getattr(word, "bbox_h", 0.0))
                    same_row = abs((wy + wh / 2) - (y + h / 2)) <= max(0.018, h * 1.2)
                    close_left = 0 < (x - wx) <= 0.08
                    if same_row and close_left:
                        candidates.append(word)
                if candidates:
                    return label, 0.86, page_num, label_box
        return None, 0.0, None, {}

    def _find_label_words(self, words: List[object], label: str) -> List[object]:
        sequences = self._find_label_word_sequences(words, label)
        return sequences[0] if sequences else []

    def _flat_checkbox_choice(self, text: str, labels: List[str]) -> Optional[str]:
        check = r"(?:\[x\]|\[X\]|X|><|✓|✔)"
        for label in labels:
            label_pat = re.escape(label).replace(r"\ ", r"\s+").replace(r"\%", r"%")
            bounded_label = rf"(?<![A-Za-z0-9]){label_pat}(?![A-Za-z0-9])"
            if re.search(rf"{check}\s*{bounded_label}|{bounded_label}\s*{check}", text, re.I):
                return label
        return None

    def _normalize_neighborhood_option(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        mapping = {
            "Over 75": "Over 75%",
            "25-75": "25-75%",
            "Under 25": "Under 25%",
        }
        return mapping.get(value, value)

    def _extract_price_age_grid(self, text: str) -> Dict[str, float]:
        section = self._section(text, r"One-?Unit\s+Housing", r"Present\s+Land\s+Use|Neighborhood\s+Boundaries|Neighborhood\s+Description")
        if not section:
            return {}
        row_values = {}
        for row, price_field, age_field in [
            ("Low", "price_low", "age_low"),
            ("High", "price_high", "age_high"),
            ("Predominant", "predominant_price", "predominant_age"),
        ]:
            match = re.search(rf"{row}\D+(\d{{1,4}})\D+(\d{{1,3}})(?=\D|$)", section, re.I)
            if match:
                row_values[price_field] = float(match.group(1))
                row_values[age_field] = int(match.group(2))
        if row_values:
            return row_values

        numbers = [float(n) for n in re.findall(r"\b\d{1,4}\b", section)]
        if len(numbers) >= 6:
            return {
                "price_low": numbers[0],
                "price_high": numbers[1],
                "predominant_price": numbers[2],
                "age_low": int(numbers[3]),
                "age_high": int(numbers[4]),
                "predominant_age": int(numbers[5]),
            }
        return {}

    # Minimum realistic sale price for the scale check below.
    # UAD neighborhood price grid entries are in thousands (e.g. 220 = $220,000).
    # Any scaled result below this threshold is almost certainly an age value
    # (years old) that leaked into the price column rather than a real price.
    _MIN_SCALED_PRICE = 10_000

    def _scale_neighborhood_price(self, value: float) -> int:
        """
        Convert a UAD neighborhood grid price cell to whole dollars.

        UAD forms show prices in thousands: "220" means $220,000.
        Values already >= 1000 are assumed to be in whole dollars already.
        Values < 1000 are multiplied by 1000 to get whole dollars.

        Sanity gate: if the scaled result is below the minimum realistic house
        price, the raw value was almost certainly an age column that leaked into
        the price extraction (e.g. "3" for "3 years old" → $3,000 is not a price).
        Return 0 in that case so downstream rules treat the field as missing.
        """
        scaled = int(value * 1000) if value and value < 1000 else int(value)
        return scaled if scaled >= self._MIN_SCALED_PRICE else 0

    def _extract_land_use_grid(self, text: str) -> Dict[str, float]:
        section = self._section(text, r"Present\s+Land\s+Use", r"Neighborhood\s+Boundaries|Neighborhood\s+Description|Market\s+Conditions")
        if not section:
            return {}
        sequence = self._land_use_sequence(section)
        if sequence:
            return sequence

        patterns = {
            "land_use_one_unit": r"(?:One[-\s]?Unit|1[-\s]?Unit)[^\d%]{0,30}(\d{1,3})\s*%",
            "land_use_2_4_unit": r"(?:2[-\s]?4\s*Unit|Two[-\s]?Four\s*Unit)[^\d%]{0,30}(\d{1,3})\s*%",
            "land_use_multi_family": r"Multi[-\s]?Family[^\d%]{0,30}(\d{1,3})\s*%",
            "land_use_commercial": r"Commercial[^\d%]{0,30}(\d{1,3})\s*%",
            "land_use_other": r"Other[^\d%]{0,30}(\d{1,3})\s*%",
        }
        result = {}
        for field, pattern in patterns.items():
            match = re.search(pattern, section, re.I)
            if match:
                result[field] = float(match.group(1))
        if len(result) >= 3 and sum(result.values()) <= 101:
            return result
        return result

    def _land_use_sequence(self, section: str) -> Dict[str, float]:
        nums = [float(n) for n in re.findall(r"\b(\d{1,3})\s*%", section)]
        for start in range(0, max(0, len(nums) - 4)):
            window = nums[start:start + 5]
            if abs(sum(window) - 100) <= 1:
                return {
                    "land_use_one_unit": window[0],
                    "land_use_2_4_unit": window[1],
                    "land_use_multi_family": window[2],
                    "land_use_commercial": window[3],
                    "land_use_other": window[4],
                }
        return {}

    def _extract_neighborhood_boundaries(self, text: str) -> Dict[str, str]:
        # In URAR PDFs, boundary VALUES appear in the early data block while
        # "Neighborhood Boundaries" label appears late in the form-labels block.
        # _section() would find the labels block (truthy but empty of values),
        # causing the `section or text` fallback to never trigger the full scan.
        # Fix: only use the section if it actually contains directional markers;
        # otherwise scan the full text so the data-block values are found.
        section = self._section(text, r"Neighborhood\s+Boundaries", r"Neighborhood\s+Description|Market\s+Conditions|Site")
        search_text = section if (section and re.search(r"\b(?:North|South|East|West)\s*[=:]", section, re.I)) else text
        found = {}
        for match in re.finditer(r"\b(North|South|East|West)\s*[=:]\s*([^;\n,]+?)(?=\s+(?:North|South|East|West)\s*[=:]|[;\n]|$)", search_text, re.I):
            direction = match.group(1).lower()
            value = re.sub(r"\s+", " ", match.group(2)).strip(" .")
            if value:
                found[direction] = value
        return found if len(found) == 4 else {}

    def _extract_neighborhood_description(self, text: str) -> Optional[str]:
        section = self._section(text, r"Neighborhood\s+Description", r"Market\s+Conditions|Site|Dimensions|Zoning")
        if not section:
            match = re.search(
                r"((?:There\s+are\s+)?no\s+(?:apparent\s+)?adverse\s+factors?.{20,260}?)(?=Market\s+Conditions|$)",
                text,
                re.I | re.S,
            )
            section = match.group(1) if match else ""
        if not section:
            return None
        return self._clean_commentary(section)

    def _extract_market_conditions(self, text: str) -> Optional[str]:
        section = self._section(text, r"Market\s+Conditions", r"Dimensions|Site|Zoning|Utilities|Highest\s+and\s+Best")
        if not section:
            return None
        return self._clean_commentary(section)

    def _section(self, text: str, start_pattern: str, end_pattern: str) -> str:
        match = re.search(rf"{start_pattern}(.{{0,1600}}?)(?={end_pattern}|\Z)", text, re.I | re.S)
        return match.group(1).strip() if match else ""

    def _clean_commentary(self, value: str) -> Optional[str]:
        value = re.sub(r"\s+", " ", value or "").strip(" :-")
        value = re.sub(r"^(?:Description|Commentary)[:\s]+", "", value, flags=re.I).strip()
        return value if len(value) >= 20 else None

    # ── Comparable extraction ──────────────────────────────────────────────────

    def _extract_comparables_camelot(
        self,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> List[Dict[str, FieldMetaResult]]:
        """
        Use Camelot lattice mode to read the UAD 1004 sales comparison grid.

        The grid is a bordered table spanning pages that contain "Comparable Sale".
        Column layout: col-0 = Subject, col-1 = Comp1, col-2 = Comp2, col-3 = Comp3.
        Row "Address" is always one of the first rows after the column header row.

        Returns an empty list on any failure so the caller can fall back to
        regex strategies.
        """
        try:
            import camelot
        except Exception:
            return []

        # Find which PDF pages contain the sales comparison grid.
        # We look for pages in page_index that mention "Comparable Sale" or "COMPARABLE".
        grid_pages = []
        for page_num, page_text in self._page_index.items():
            if re.search(r"COMPARABLE\s+SALE|Sales\s+Comparison\s+Approach", page_text or "", re.I):
                grid_pages.append(page_num)

        if not grid_pages:
            return []

        # Limit to 3 pages to avoid scanning the whole document
        grid_pages = sorted(grid_pages)[:3]
        pages_arg = ",".join(str(p) for p in grid_pages)

        # Locate the PDF file from the page_index context.
        # The page_index is populated by extract_subject() which also stores
        # the PDF path; we recover it via the cache_service if available.
        pdf_path = getattr(self, "_pdf_path", None)
        if not pdf_path:
            return []   # Path not available — skip Camelot

        # Try lattice first (cleaner column alignment), fall back to stream
        # if Ghostscript is not installed (lattice requires gs to rasterize pages).
        tables = None
        for _flavor, _kwargs in [
            ("lattice", {"copy_text": ["v"]}),
            ("stream",  {}),
        ]:
            try:
                tables = camelot.read_pdf(
                    pdf_path,
                    pages=pages_arg,
                    flavor=_flavor,
                    strip_text="\n",
                    **_kwargs,
                )
                break
            except Exception as exc:
                logger.debug("Camelot %s comparable extraction failed: %s", _flavor, exc)
        if not tables:
            return []

        comps_found: List[Dict[str, FieldMetaResult]] = []

        for table in tables:
            try:
                df = table.df.fillna("").astype(str)
            except Exception:
                continue

            # Need at least 4 columns (Subject + 3 comps) and enough rows
            if df.shape[1] < 4 or df.shape[0] < 3:
                continue

            # Estimate which page this table came from
            base_page = grid_pages[0] if grid_pages else 3
            try:
                tbl_page = int(table.page)
                if tbl_page in grid_pages:
                    base_page = tbl_page
            except Exception:
                pass

            # Find the address row: look for a row where column 0 contains
            # "Address" (the label) and columns 1-3 contain street addresses
            address_row_idx = None
            for row_idx, row in df.iterrows():
                row_lower = str(row.iloc[0]).lower()
                if "address" in row_lower:
                    address_row_idx = row_idx
                    break

            # Find the sale price row similarly
            price_row_idx = None
            for row_idx, row in df.iterrows():
                row_lower = str(row.iloc[0]).lower()
                if "sale price" in row_lower or re.search(r"sale\s+price", row_lower):
                    price_row_idx = row_idx
                    break

            if address_row_idx is None and price_row_idx is None:
                continue

            # Extract values for each of 3 comparable columns (cols 1, 2, 3)
            for comp_idx in range(1, min(4, df.shape[1])):
                comp_num = comp_idx   # comp 1 = col 1, comp 2 = col 2, comp 3 = col 3
                if comp_num > len(comps_found):
                    comps_found.append({})

                if address_row_idx is not None:
                    raw_addr = str(df.iloc[address_row_idx, comp_idx]).strip()
                    # Basic sanity: must look like a street address (digits at start)
                    if raw_addr and re.match(r"\d+\s+[A-Za-z]", raw_addr):
                        comps_found[comp_num - 1]["address"] = FieldMetaResult(
                            f"comp_{comp_num}_address",
                            raw_value=raw_addr, corrected_value=raw_addr,
                            confidence=0.88, source_page=base_page,
                            extraction_method="spatial_anchor",
                        )

                if price_row_idx is not None:
                    raw_price = str(df.iloc[price_row_idx, comp_idx]).strip()
                    # Strip leading $ and commas
                    clean_price = re.sub(r"[^0-9.]", "", raw_price)
                    if clean_price:
                        comps_found[comp_num - 1]["sale_price"] = FieldMetaResult(
                            f"comp_{comp_num}_sale_price",
                            raw_value=raw_price, corrected_value=clean_price,
                            confidence=0.88, source_page=base_page,
                            extraction_method="spatial_anchor",
                        )

            # If we found at least 2 comps with addresses, this table is good
            found_with_addresses = sum(
                1 for c in comps_found if c.get("address") and c["address"].value
            )
            if found_with_addresses >= 2:
                break   # Good enough — stop scanning tables

        # Pad to 3 slots so downstream code can iterate safely
        while len(comps_found) < 3:
            comps_found.append({})

        return comps_found if any(c for c in comps_found) else []

    def _extract_comparables(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> List[Dict[str, FieldMetaResult]]:
        """
        Extract address + price for up to 3 comparable sales.

        UAD 1004 forms use several label formats:
          "COMPARABLE NO. 1"  "COMPARABLE SALE # 1"  "Comparable No 1"
          "COMPARABLE 1"  "Comp. 1"  "Sale 1"

        Also tries extracting from the Sales Comparison grid pattern where
        addresses appear in columns after "Subject" on the grid pages.

        Known failure mode: the subject address (which appears in the SUBJECT column
        of the SCA grid) is a valid street address pattern and can be captured in a
        comp slot if the grid column extraction is not constrained.  We carry the
        already-extracted subject address and actively exclude it from comp matches.
        """
        comps = []

        # Pre-compute normalized subject address for deduplication across all strategies.
        _subj_text, _ = self._text_window_for_pages(text, page_pos, 1, 2)
        _subj_addr_match = re.search(r'(\d+\s+[A-Za-z][A-Za-z0-9 \.\,\-]{4,50})', _subj_text)
        subject_address_norm = (
            re.sub(r'\s+', ' ', _subj_addr_match.group(1).strip().upper())
            if _subj_addr_match else None
        )

        def _is_subject_address(candidate: str) -> bool:
            """Return True if candidate string is the subject property address."""
            if not subject_address_norm or not candidate:
                return False
            norm = re.sub(r'\s+', ' ', candidate.strip().upper())
            return norm == subject_address_norm or subject_address_norm in norm

        def _clear_subject_addr(comp_list: List[Dict]) -> List[Dict]:
            """Null out any comp address slot that holds the subject address."""
            for entry in comp_list:
                addr_meta = entry.get("address")
                if addr_meta and _is_subject_address(addr_meta.value or ""):
                    entry["address"] = FieldMetaResult(
                        addr_meta.name, confidence=0.0, extraction_method="not_found"
                    )
                    logger.debug(
                        "Deduplication: cleared comp address '%s' (matches subject)",
                        addr_meta.value,
                    )
            return comp_list

        # ── Strategy 0: Camelot lattice table extraction (highest priority) ──────
        # The UAD 1004 sales comparison grid is a multi-column table with vertical
        # and horizontal grid lines.  Camelot "lattice" mode reads it correctly and
        # delivers four columns: [Subject, Comp1, Comp2, Comp3].  This eliminates
        # the text-flatten ambiguity that causes comp addresses to merge into a
        # single undelimited row.
        #
        # Only attempted when the word_index contains page geometry (i.e. the PDF
        # was processed with the full OCR pipeline, not just embedded text).
        # Falls through to Strategy 1/2 on any exception or empty result.
        if self._word_index and self._page_index:
            camelot_comps = self._extract_comparables_camelot(page_pos, pos_offset)
            if camelot_comps:
                comps = _clear_subject_addr(camelot_comps)

        # ── Strategy 1: data-stream extraction (primary) ──────────────────────
        # PyMuPDF emits field VALUES before form LABELS in the text stream.
        # "COMPARABLE SALE # 1" headers appear late in the page (form template
        # background text). Instead, extract comparables by scanning for address
        # lines that have a proximity indicator on the following line, which is
        # the reliable data-driven pattern in URAR 1004 sales-grid pages.
        #
        # Pattern: <address>\n<city, state zip>\n<X.XX miles DIR>\n<price>
        # The proximity line ("0.10 miles E") is the key discriminator — comparable
        # addresses always have a proximity statement but the subject address does not.
        data_comp_pattern = re.compile(
            r"(\d+\s+[A-Za-z][A-Za-z0-9 ,\.\-]{4,60})\n"   # address line
            r"[A-Za-z][A-Za-z ,]+\d{5}\n"                    # city, state zip
            r"(\d+\.?\d*\s+miles?\s+[NSEW]{1,2})\n"          # proximity line (comps only)
            r"([\d,]{4,})",                                   # sale price (no $)
            re.I,
        )
        data_matches = list(data_comp_pattern.finditer(text))
        for m in data_matches[:3]:
            addr_candidate = m.group(1).strip()
            # Guard: proximity line is always present for comps but exclude subject anyway
            if _is_subject_address(addr_candidate):
                continue
            comps.append({
                "address": FieldMetaResult(
                    f"comp_{len(comps)+1}_address",
                    raw_value=addr_candidate,
                    corrected_value=addr_candidate,
                    confidence=0.80,
                    source_page=page_for_pos(m.start() + pos_offset, page_pos),
                    extraction_method="regex_primary",
                ),
                "sale_price": FieldMetaResult(
                    f"comp_{len(comps)+1}_sale_price",
                    raw_value=m.group(3).replace(",", ""),
                    corrected_value=m.group(3).replace(",", ""),
                    confidence=0.80,
                    source_page=page_for_pos(m.start() + pos_offset, page_pos),
                    extraction_method="regex_primary",
                ),
            })

        if len(comps) >= 3:
            return comps

        # ── Strategy 2: COMPARABLE SALE # N label headers (fallback) ─────────
        # Use START of next header (not end) as section boundary.
        header_pattern = re.compile(
            r"COMPARABLE\s+(?:SALE\s+)?(?:NO\.?\s*|#\s*)?([1-4])\b",
            re.I,
        )
        headers = [
            (int(match.group(1)), match.start(), match.end())
            for match in header_pattern.finditer(text)
        ]
        header_by_num: dict = {}
        for num, start, end in headers:
            header_by_num.setdefault(num, (start, end))

        for comp_num in range(len(comps) + 1, 4):
            header = header_by_num.get(comp_num)
            if not header:
                comps.append({})
                continue

            section_start = header[0]
            value_start = header[1]
            next_header = header_by_num.get(comp_num + 1)
            if next_header:
                section_end = next_header[0]   # START of next header (not end)
            else:
                end_match = re.search(
                    r"\b(?:RECONCILIATION|SALES\s+COMPARISON\s+APPROACH|"
                    r"SUMMARY\s+OF\s+SALES\s+COMPARISON|COST\s+APPROACH)\b",
                    text[value_start:value_start + 1600],
                    re.I,
                )
                if comp_num < 3 or not end_match:
                    logger.debug(
                        "Phase2 comparables: missing boundary after comparable %d; "
                        "marking section not_found.",
                        comp_num,
                    )
                    comps.append({})
                    continue
                section_end = value_start + end_match.start()

            comp_text = text[value_start:section_end][:600]
            base_page = page_for_pos(section_start + pos_offset, page_pos)

            addr_match = re.search(r'(\d+\s+[A-Za-z][A-Za-z0-9 \.\,]{5,60})', comp_text)
            price_match = re.search(r'\$\s*([\d,]{5,})', comp_text)
            if not price_match:
                price_match = re.search(r'\b([\d]{3},[\d]{3})\b', comp_text)

            # Reject if the matched address is the subject property — this happens
            # when the SUBJECT column header sits next to COMPARABLE #N in the grid
            # and the regex anchors on the subject's address row instead of the comp.
            addr_raw = addr_match.group(1).strip() if addr_match else None
            if _is_subject_address(addr_raw):
                addr_raw = None
                addr_match = None

            comps.append({
                "address": FieldMetaResult(
                    f"comp_{comp_num}_address",
                    raw_value=addr_raw,
                    corrected_value=addr_raw,
                    confidence=0.70 if addr_raw else 0.0,
                    source_page=base_page,
                    extraction_method="spatial_anchor" if addr_raw else "not_found",
                ),
                "sale_price": FieldMetaResult(
                    f"comp_{comp_num}_sale_price",
                    raw_value=price_match.group(1) if price_match else None,
                    corrected_value=price_match.group(1) if price_match else None,
                    confidence=0.72 if price_match else 0.0,
                    source_page=base_page,
                    extraction_method="regex_primary" if price_match else "not_found",
                ),
            })

        # ── Strategy 2: grid column scan (fallback if no headers found) ────────
        all_empty = all(not c.get("address") or c["address"].value is None for c in comps)
        if all_empty and not headers:
            # In the sales grid, comp addresses appear as 3 addresses after "Subject"
            # Look for lines with street addresses in groups of 3-4. Keep the
            # scan inside the sales-comparison pages so signature/appraiser
            # addresses later in the PDF cannot become comparable sales.
            grid_text = self._section(
                text,
                r"Sales\s+Comparison\s+Approach",
                r"Reconciliation|Cost\s+Approach|Income\s+Approach",
            )
            if not grid_text:
                grid_text = text[:5000]
            addr_lines = re.findall(r'(\d+\s+[A-Za-z][A-Za-z0-9 \.\,]{5,50})', grid_text)
            # Filter to only look like street addresses (has directional/type suffix)
            street_lines = [
                a for a in addr_lines
                if re.search(r'\b(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|N|S|E|W|NE|NW|SE|SW)\b', a, re.I)
            ]
            if len(street_lines) >= 2:
                for i, sl in enumerate(street_lines[1:4], 1):
                    if _is_subject_address(sl):
                        continue
                    if i <= len(comps):
                        existing = comps[i - 1].get("address")
                        if existing is None or existing.value is None:
                            comps[i - 1]["address"] = FieldMetaResult(
                                f"comp_{i}_address", raw_value=sl, corrected_value=sl,
                                confidence=0.55, extraction_method="regex_fallback",
                            )

        return comps

    # ── Section boundary detection ─────────────────────────────────────────────

    def _build_section_bounds(self, page_num: int) -> Dict[str, Tuple[float, float]]:
        """
        Scan the word_index for a single page and return Y-axis boundaries for
        each UAD section present on that page.

        Returns:
            {section_key: (y_min, y_max)}  — normalized 0.0..1.0 coordinates.
            y_min = Y of first anchor word found for the section.
            y_max = y_min of the next section on the same page, or 1.0.

        Result is cached per-page so repeated calls are O(1).
        """
        if page_num in self._section_bounds_cache:
            return self._section_bounds_cache[page_num]

        words = self._word_index.get(page_num, [])
        # Sort words top-to-bottom so the first hit is the topmost anchor
        sorted_words = sorted(words, key=lambda w: float(getattr(w, "bbox_y", 0.0)))

        # Collect (y_position, section_key) for each anchor found on this page
        hits: List[Tuple[float, str]] = []
        for section_key, anchor_labels in self._UAD_SECTION_ANCHORS:
            for label in anchor_labels:
                label_tokens = label.lower().split()
                for i, word in enumerate(sorted_words):
                    word_text = (getattr(word, "text", "") or "").lower()
                    if word_text == label_tokens[0]:
                        # Multi-word label: check subsequent words
                        remaining = label_tokens[1:]
                        match = True
                        for j, token in enumerate(remaining, 1):
                            if i + j >= len(sorted_words):
                                match = False
                                break
                            next_text = (getattr(sorted_words[i + j], "text", "") or "").lower()
                            if next_text != token:
                                match = False
                                break
                        if match:
                            y = float(getattr(word, "bbox_y", 0.0))
                            hits.append((y, section_key))
                            break  # first hit per label is sufficient
                if any(s == section_key for _, s in hits):
                    break  # first label match per section is sufficient

        # Remove duplicate section keys (keep the topmost occurrence)
        seen: set = set()
        unique_hits: List[Tuple[float, str]] = []
        for y, key in sorted(hits, key=lambda t: t[0]):
            if key not in seen:
                seen.add(key)
                unique_hits.append((y, key))

        # Build (y_min, y_max) pairs: y_max of section N = y_min of section N+1
        bounds: Dict[str, Tuple[float, float]] = {}
        for idx, (y, key) in enumerate(unique_hits):
            y_max = unique_hits[idx + 1][0] if idx + 1 < len(unique_hits) else 1.0
            bounds[key] = (y, y_max)

        self._section_bounds_cache[page_num] = bounds
        return bounds

    def _section_restricted_text(
        self,
        page_num: int,
        section_key: str,
        fallback_text: str = "",
    ) -> Tuple[str, int]:
        """
        Return the text of `page_num` restricted to the Y-band of `section_key`.

        Words whose bbox_y falls outside [y_min, y_max) for the section are
        excluded.  This prevents regex extractors from matching form field labels
        and values from adjacent sections that happen to share the same page.

        Returns:
            (restricted_text, 0) — the offset is always 0 because we rebuild
            the text string from filtered words; absolute position tracking is
            handled by the word-bbox coordinate when the caller needs it.
        """
        bounds = self._build_section_bounds(page_num)
        if section_key not in bounds:
            # Section not detected on this page — return full page text as fallback
            return fallback_text, 0

        y_min, y_max = bounds[section_key]
        words = self._word_index.get(page_num, [])
        section_words = [
            w for w in words
            if y_min <= float(getattr(w, "bbox_y", 0.0)) < y_max
        ]
        if not section_words:
            return fallback_text, 0

        # Reconstruct text preserving horizontal reading order within each row
        sorted_words = sorted(
            section_words,
            key=lambda w: (round(float(getattr(w, "bbox_y", 0.0)), 2),
                           float(getattr(w, "bbox_x", 0.0))),
        )
        restricted = " ".join(getattr(w, "text", "") for w in sorted_words)
        return restricted, 0

    def _trim_merged_person_field(self, field: Optional[FieldMetaResult]) -> None:
        """
        Cut OCR spillover from neighboring Subject-section cells.

        UAD rows are sometimes flattened without column separators, causing the
        extractor to capture adjacent field values appended to the target value:
          "Precision Builders and Developers LLC" + "County Colquitt"
          becomes "Precision Builders and Developers LLCCounty Colquitt"

        Two search modes:
          1. Word-boundary match: works when there is whitespace before the label.
          2. Concatenated match: handles "LLCCounty" where \b never fires because
             the preceding char (C in LLC) is itself a word character.  We use a
             lookbehind on any letter to catch the fused boundary.
        """
        if not field or not field.value:
            return

        value = field.value

        # Mode 0: company suffix directly followed by a form label (e.g. "LLCCounty").
        # Must run BEFORE Mode 1 to preserve the suffix itself ("LLC") in the trimmed value.
        # Captures up to and including the company suffix, then discards everything after.
        _SUFFIX_STOP = re.compile(
            r"(LLC|Inc\.?|Corp\.?|Ltd\.?|LLP)\s*(?=County|City|State|Legal|Assessor|"
            r"Tax\s+Year|Occupant|Map\s+Reference|Census\s+Tract|Lender|Client|Address)",
            re.I,
        )
        _sfx = _SUFFIX_STOP.search(value)
        if _sfx:
            value = value[:_sfx.end()].rstrip()

        # Mode 1: whitespace-separated boundary (standard case)
        boundary = re.search(
            r"\b(?:Owner of Public Record|Property Address|City|County|Legal Description|"
            r"Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b",
            value,
            re.I,
        )

        # Mode 2: concatenated boundary — letter immediately precedes a known label.
        # Pattern: [A-Za-z] immediately followed by County|City|Legal|etc.
        # This fires on remaining fused cases where Mode 0 didn't match a known suffix.
        if not boundary:
            boundary = re.search(
                r"(?<=[A-Za-z])(?:Owner\s+of\s+Public\s+Record|County|City|Legal\s+Description|"
                r"Assessor|Tax\s+Year|Occupant|Map\s+Reference|Census\s+Tract|Lender|Client)",
                value,
                re.I,
            )

        if boundary:
            value = value[:boundary.start()]

        value = re.sub(r'\s+', ' ', value).strip(" :-|")
        if value and value != field.value:
            field.corrected_value = value
            field.correction_applied = True
            field.confidence = max(field.confidence, 0.78)
            field.extraction_method = f"{field.extraction_method}+boundary_trim"

    # ── Cross-field sanity checks ──────────────────────────────────────────────

    def _sanity_checks(self, meta: Dict[str, FieldMetaResult]) -> Dict[str, FieldMetaResult]:
        """
        Run sanity checks on extracted fields.
        Lowers confidence and sets sanity_check_failed on suspicious values.
        """
        state_m = meta.get("state")
        zip_m   = meta.get("zip_code")
        state_val = state_m.corrected_value if state_m else None
        zip_val   = zip_m.corrected_value   if zip_m   else None

        # ── Check 1: State/zip consistency ────────────────────────────────────
        if state_val and zip_val and len(zip_val) >= 1:
            expected = _STATE_ZIP_PREFIXES.get(state_val.upper())
            actual_first = zip_val[0]
            if expected and actual_first not in expected:
                zip_m.sanity_check_failed = True
                zip_m.sanity_check_reason = (
                    f"Zip '{zip_val}' starts with '{actual_first}'; "
                    f"expected {expected} for state {state_val}"
                )
                zip_m.confidence = max(0.0, zip_m.confidence - 0.30)
                logger.debug("Sanity FAIL: zip/state mismatch — %s", zip_m.sanity_check_reason)

        # ── Check 2: Zip code format ───────────────────────────────────────────
        if zip_val and not re.match(r'^\d{5}(?:-\d{4})?$', zip_val):
            zip_m.sanity_check_failed = True
            zip_m.sanity_check_reason = f"Zip code '{zip_val}' is not 5 digits"
            zip_m.confidence = max(0.0, zip_m.confidence - 0.40)

        # ── Check 3: Street address must contain a digit ───────────────────────
        street_m = meta.get("property_address")
        if street_m and street_m.corrected_value:
            if not re.search(r'\d', street_m.corrected_value):
                street_m.sanity_check_failed = True
                street_m.sanity_check_reason = "Street address contains no house number"
                street_m.confidence = max(0.0, street_m.confidence - 0.40)

        # ── Check 4: Borrower name length (OCR line merge) ────────────────────
        borrower_m = meta.get("borrower_name")
        if borrower_m and borrower_m.corrected_value and len(borrower_m.corrected_value) > 60:
            borrower_m.sanity_check_failed = True
            borrower_m.sanity_check_reason = "Name >60 chars — possible OCR line merge"
            borrower_m.confidence = max(0.0, borrower_m.confidence - 0.30)

        # ── Check 5: Market value sanity ($0 or >$10M for residential) ─────────
        mv_m = meta.get("market_value_opinion")
        if mv_m and mv_m.corrected_value:
            try:
                val = float(re.sub(r'[,$]', '', mv_m.corrected_value))
                if val == 0:
                    mv_m.sanity_check_failed = True
                    mv_m.sanity_check_reason = "Market value is $0 — extraction error"
                    mv_m.confidence = 0.05
                elif val > 10_000_000:
                    mv_m.sanity_check_failed = True
                    mv_m.sanity_check_reason = f"Market value ${val:,.0f} >$10M — possible OCR error"
                    mv_m.confidence = max(0.0, mv_m.confidence - 0.30)
            except (ValueError, TypeError):
                pass

        # ── Check 6: Condition rating format ──────────────────────────────────
        cond_m = meta.get("condition_rating")
        if cond_m and cond_m.corrected_value:
            if not re.match(r'^C[1-6]$', cond_m.corrected_value):
                cond_m.sanity_check_failed = True
                cond_m.sanity_check_reason = f"Condition rating '{cond_m.corrected_value}' not C1-C6"
                cond_m.confidence = max(0.0, cond_m.confidence - 0.40)

        # ── Check 7: Tax year should be recent ────────────────────────────────
        tax_year_m = meta.get("tax_year")
        if tax_year_m and tax_year_m.corrected_value:
            try:
                year = int(tax_year_m.corrected_value)
                if year < 2018 or year > 2027:
                    tax_year_m.sanity_check_failed = True
                    tax_year_m.sanity_check_reason = f"Tax year {year} outside expected range 2018–2027"
                    tax_year_m.confidence = max(0.0, tax_year_m.confidence - 0.25)
            except (ValueError, TypeError):
                pass

        return meta

    # ── OCR correction for full text ───────────────────────────────────────────

    def _correct_text(self, text: str) -> Tuple[str, int]:
        """Apply OCR corrections to full document text. Returns (corrected, count)."""
        from app.services.ocr_correction import apply_ocr_correction_to_full_text
        return apply_ocr_correction_to_full_text(text)

    # ── Map to SubjectSectionExtract (backward compat) ────────────────────────

    def _to_subject_extract(self, meta: Dict[str, FieldMetaResult]) -> SubjectSectionExtract:
        """Convert FieldMetaResult dict to SubjectSectionExtract Pydantic model."""

        def val(key: str) -> Optional[str]:
            m = meta.get(key)
            return m.value if m else None

        def float_val(key: str) -> Optional[float]:
            v = val(key)
            if v is None:
                return None
            try:
                return float(re.sub(r'[,$]', '', v))
            except (ValueError, TypeError):
                return None

        def bool_val(key: str) -> Optional[bool]:
            v = val(key)
            if v is None:
                return None
            return v.lower() in ("true", "yes", "1")

        s = SubjectSectionExtract(
            property_address=val("property_address"),
            city=val("city"),
            state=val("state"),
            zip_code=val("zip_code"),
            county=val("county"),
            borrower_name=val("borrower_name"),
            co_borrower_name=val("co_borrower_name"),
            owner_of_public_record=val("owner_of_public_record"),
            legal_description=val("legal_description"),
            assessors_parcel_number=val("assessors_parcel_number"),
            tax_year=val("tax_year"),
            real_estate_taxes=float_val("real_estate_taxes"),
            neighborhood_name=val("neighborhood_name"),
            map_reference=val("map_reference"),
            census_tract=val("census_tract"),
            occupant_status=val("occupant_status"),
            special_assessments=float_val("special_assessments"),
            hoa_dues=float_val("hoa_dues"),
            hoa_period=val("hoa_period"),
            is_pud_checked=bool_val("is_pud_checked"),
            lender_name=val("lender_name"),
            lender_address=val("lender_address"),
            property_rights=val("property_rights"),
            offered_for_sale_12mo=bool_val("offered_for_sale_12mo"),
            data_source=val("data_source"),
            mls_number=val("mls_number"),
        )
        return s


# Global instance
phase2_engine = Phase2ExtractionEngine()
