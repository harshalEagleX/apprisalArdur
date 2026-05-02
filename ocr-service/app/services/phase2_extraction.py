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
from app.services.ocr_correction import apply_ocr_correction

logger = logging.getLogger(__name__)

# LLaVA vision fallback for uncertain checkboxes
try:
    from app.services.ollama_service import detect_checkbox_vision, is_vision_model_available
    _VISION_OK = is_vision_model_available()
    if _VISION_OK:
        logger.info("LLaVA available — checkbox vision fallback enabled")
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


# ── Core extraction helper ─────────────────────────────────────────────────────

class Phase2ExtractionEngine:
    """
    Phase 2 field extraction with metadata (source page, confidence, correction).
    """
    def __init__(self):
        # Page images for LLaVA checkbox fallback — set per extract_subject() call
        self._page_images: Dict[int, object] = {}
        self._page_index: Dict[int, str] = {}
        self._page_positions: List[Tuple[int, int]] = []
        self._word_index: Dict[int, List[object]] = {}

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
        # Store page images for LLaVA checkbox fallback (Step 2)
        # Page 1 is the main form page — checkboxes are almost always on pages 1-3
        self._page_images = page_images or {}
        self._page_index = page_index
        self._word_index = word_index or {}

        # Apply OCR corrections to the full text before any regex
        corrected_text, correction_count = self._correct_text(full_text)
        if correction_count > 0:
            logger.info("Applied %d OCR corrections to document text", correction_count)

        # Build position → page map
        page_pos = build_page_position_map(page_index)
        self._page_positions = page_pos

        # Anchor to report start
        report_start = re.search(r"Uniform Residential Appraisal Report", corrected_text, re.I)
        text = corrected_text[report_start.start():] if report_start else corrected_text
        pos_offset = report_start.start() if report_start else 0

        meta: Dict[str, FieldMetaResult] = {}

        # ── S-1: Address (with robust splitting) ─────────────────────────────
        street, city, state, zip_code = self._extract_address_robust(text, page_pos, pos_offset)
        meta["property_address"] = street
        meta["city"] = city
        meta["state"] = state
        meta["zip_code"] = zip_code

        county_m = self._extract("county", text, [
            r"County[:\s]+([A-Za-z][A-Za-z\s]+?)(?:\s*\n|$)",
        ], page_pos, pos_offset)
        meta["county"] = county_m

        # ── S-2: Borrower ─────────────────────────────────────────────────────
        meta["borrower_name"] = self._extract("borrower_name", text, [
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)(.{3,120}?)(?=\s+(?:Owner of Public Record|Property Address|City|County|Legal Description|Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b|\n|$)",
            r"BORROWER[:\s]+(?!LENDER|CLIENT)(.{3,120}?)(?=\s+(?:OWNER OF PUBLIC RECORD|PROPERTY ADDRESS|CITY|COUNTY|LEGAL DESCRIPTION|ASSESSOR|TAX YEAR|OCCUPANT|MAP REFERENCE|CENSUS TRACT|LENDER|CLIENT)\b|\n|$)",
        ], page_pos, pos_offset)
        self._trim_merged_person_field(meta["borrower_name"])

        meta["co_borrower_name"] = self._extract("co_borrower_name", text, [
            r"Co-?Borrower[:\s]+(.{3,120}?)(?=\s+(?:Owner of Public Record|Property Address|City|County|Legal Description|Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b|\n|$)",
            r"CO-?BORROWER[:\s]+(.{3,120}?)(?=\s+(?:OWNER OF PUBLIC RECORD|PROPERTY ADDRESS|CITY|COUNTY|LEGAL DESCRIPTION|ASSESSOR|TAX YEAR|OCCUPANT|MAP REFERENCE|CENSUS TRACT|LENDER|CLIENT)\b|\n|$)",
        ], page_pos, pos_offset)
        self._trim_merged_person_field(meta["co_borrower_name"])

        # ── S-3: Owner of Public Record ───────────────────────────────────────
        meta["owner_of_public_record"] = self._extract("owner_of_public_record", text, [
            r"Owner of Public Record[:\s]+([^\n]+)",
            r"Current Owner[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        # ── S-4: Legal / APN / Taxes ──────────────────────────────────────────
        meta["legal_description"] = self._extract("legal_description", text, [
            r"Legal Description[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        meta["assessors_parcel_number"] = self._extract("assessors_parcel_number", text, [
            r"(?:Assessor'?s?\s*)?Parcel\s*(?:#|Number|No\.?)[:\s]+([^\n]+)",
            r"APN[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        meta["tax_year"] = self._extract("tax_year", text, [
            r"Tax Year[:\s]+(\d{4})",
        ], page_pos, pos_offset)

        meta["real_estate_taxes"] = self._extract("real_estate_taxes", text, [
            r"R\.?E\.?\s*Taxes\s*\$?\s*([\d,]+)",
            r"Real Estate Taxes\s*\$?\s*([\d,]+)",
        ], page_pos, pos_offset)

        # ── S-5: Neighborhood Name ────────────────────────────────────────────
        meta["neighborhood_name"] = self._extract("neighborhood_name", text, [
            r"Neighborhood Name[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        # ── S-6: Map Reference / Census Tract ─────────────────────────────────
        meta["map_reference"] = self._extract("map_reference", text, [
            r"Map Reference[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        meta["census_tract"] = self._extract("census_tract", text, [
            r"Census Tract[:\s]+(\d{4}\.\d{2})",
            r"Census Tract[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

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
        elif any(s is False for s in [owner_state, tenant_state, vacant_state]):
            # Some are explicitly [ ] but none are [X] — problem field
            occupant, occ_conf = None, 0.30
        else:
            # OCR couldn't read any checkbox
            occupant, occ_conf = None, 0.0

        meta["occupant_status"] = FieldMetaResult(
            "occupant_status", raw_value=occupant, corrected_value=occupant,
            confidence=occ_conf,
            extraction_method="regex_primary" if occupant else ("regex_fallback" if occ_conf > 0 else "not_found"),
        )

        # ── S-8: Special Assessments ──────────────────────────────────────────
        meta["special_assessments"] = self._extract("special_assessments", text, [
            r"Special Assessments[:\s]*\$?([\d,]+)",
        ], page_pos, pos_offset)

        # ── S-9: PUD / HOA ────────────────────────────────────────────────────
        pud_state = self._checkbox_state(text, "PUD")
        # True=[X] → PUD checked, False=[ ] → explicitly no PUD, None → unknown
        pud_val = "True" if pud_state is True else ("False" if pud_state is False else None)
        pud_conf = 0.90 if pud_state is not None else 0.0
        meta["is_pud_checked"] = FieldMetaResult(
            "is_pud_checked", raw_value=pud_val, corrected_value=pud_val,
            confidence=pud_conf,
            extraction_method="regex_primary" if pud_state is not None else "not_found",
        )

        meta["hoa_dues"] = self._extract("hoa_dues", text, [
            r"HOA\s+Dues?[:\s]*\$?([\d,]+)",
            r"HOA[:\s]*\$?([\d,]+)",
        ], page_pos, pos_offset)

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
        meta["lender_name"] = self._extract("lender_name", text, [
            # Pattern 1: company name keyword (most specific)
            r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z0-9\s,\.&]+(?:Corporation|Corp|Inc|LLC|LLP|Company|Co\.?|Bank|Mortgage|Credit Union|Funding|Capital|Financial|Home Loans?|Lending|Services?))(?:\s+Address|\s*$|\n)",
            # Pattern 2: looks for line starting with a number-street (lender address often follows inline)
            r"Lender/?Client[\s—:-]+([A-Z][A-Za-z0-9\s,\.&]{4,60}?)(?=\s+\d{1,5}\s|\s+Address|\n|$)",
            # Pattern 3: anything that looks like a proper name (Title Case, reasonable length, no slash-junk)
            r"Lender/?Client[\s\-—:]+([A-Z][a-zA-Z0-9\s&,\.]{3,50}?)(?:\s+Address|\n)",
        ], page_pos, pos_offset, post_clean=r'\s*(Address|Client Address).*$')

        meta["lender_address"] = self._extract("lender_address", text, [
            r"(?:Lender/?Client|Lender)\s+Address[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        # ── S-11: Property Rights ─────────────────────────────────────────────
        # Three-state: [X] = this rights type applies, [ ] = explicit no, None = unknown
        rights = None
        rights_conf = 0.0
        for label in ["Fee Simple", "Leasehold", "De Minimis PUD"]:
            state = self._checkbox_state(text, label)
            if state is True:
                rights = label
                rights_conf = 0.90
                break
        meta["property_rights"] = FieldMetaResult(
            "property_rights", raw_value=rights, corrected_value=rights,
            confidence=rights_conf,
            extraction_method="regex_primary" if rights else "not_found",
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
            meta["offered_for_sale_12mo"] = FieldMetaResult(
                "offered_for_sale_12mo", confidence=0.0, extraction_method="not_found"
            )

        meta["data_source"] = self._extract("data_source", text, [
            r"Data Source[s]?[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        meta["mls_number"] = self._extract("mls_number", text, [
            r"MLS[:\s#]+([A-Z0-9]+)",
        ], page_pos, pos_offset)

        # ── Comparable Sales (new in Phase 2) ─────────────────────────────────
        comps = self._extract_comparables(text, page_pos, pos_offset)
        for i, comp in enumerate(comps, 1):
            meta[f"comp_{i}_address"] = comp.get("address")
            meta[f"comp_{i}_sale_price"] = comp.get("sale_price")

        # ── Market value opinion ───────────────────────────────────────────────
        meta["market_value_opinion"] = self._extract("market_value_opinion", text, [
            r"(?:Appraised|Market)\s+Value[:\s]*\$?([\d,]+)",
            r"Opinion of Value[:\s]*\$?([\d,]+)",
            r"Value[:\s]*\$?([\d,]+)",
        ], page_pos, pos_offset)

        # ── Condition / Quality ratings ────────────────────────────────────────
        meta["condition_rating"] = self._extract("condition_rating", text, [
            r"\b(C[1-6])\b",
        ], page_pos, pos_offset)

        meta["quality_rating"] = self._extract("quality_rating", text, [
            r"\b(Q[1-6])\b",
        ], page_pos, pos_offset)

        # ── Neighbourhood description text ─────────────────────────────────────
        meta["neighborhood_description"] = self._extract_text_block("neighborhood_description", text, [
            r"(?:Neighborhood Description|Neighborhood Boundaries)[:\s]+(.{30,800}?)(?:\n{2,}|\Z)",
        ], page_pos, pos_offset)

        # ── Market conditions commentary ───────────────────────────────────────
        meta["market_conditions_commentary"] = self._extract_text_block("market_conditions_commentary", text, [
            r"Market Conditions[:\s]+(.{30,800}?)(?:\n{2,}|\Z)",
        ], page_pos, pos_offset)

        # ── Cross-field sanity checks ──────────────────────────────────────────
        meta = self._sanity_checks(meta)

        # ── Map meta → SubjectSectionExtract (backward-compat) ────────────────
        subject = self._to_subject_extract(meta)

        return subject, meta

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

            anchor_pos = addr_line_match.start() + pos_offset
            zip_m   = FieldMetaResult("zip_code",
                raw_value=zip_ind.group(1) if zip_ind else None,
                corrected_value=zip_ind.group(1) if zip_ind else None,
                confidence=0.80 if zip_ind else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(anchor_pos, zip_ind.group(1) if zip_ind else None),
                extraction_method="spatial_anchor" if zip_ind else "not_found")

            state_m = FieldMetaResult("state",
                raw_value=state_ind.group(1).upper() if state_ind else None,
                corrected_value=state_ind.group(1).upper() if state_ind else None,
                confidence=0.80 if state_ind else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(anchor_pos, state_ind.group(1) if state_ind else None),
                extraction_method="spatial_anchor" if state_ind else "not_found")

            city_m  = FieldMetaResult("city",
                raw_value=city_ind.group(1).strip() if city_ind else None,
                corrected_value=city_ind.group(1).strip() if city_ind else None,
                confidence=0.75 if city_ind else 0.0,
                source_page=base_page,
                **self._bbox_kwargs(anchor_pos, city_ind.group(1) if city_ind else None),
                extraction_method="spatial_anchor" if city_ind else "not_found")

            # Street is the address line itself
            raw_street = full_line
            corr_street, sf = apply_ocr_correction(raw_street)
            street_m = FieldMetaResult("property_address",
                raw_value=raw_street, corrected_value=corr_street,
                confidence=0.80, source_page=base_page,
                **self._bbox_kwargs(anchor_pos, raw_street),
                correction_applied=sf, extraction_method=method)
            return street_m, city_m, state_m, zip_m

        raw_zip = zip_match.group(1)
        corr_zip, zip_fixed = apply_ocr_correction(raw_zip)
        before_zip = full_line[:zip_match.start()].strip()

        zip_m = FieldMetaResult(
            "zip_code", raw_value=raw_zip, corrected_value=corr_zip,
            confidence=0.92, source_page=base_page,
            **self._bbox_kwargs(addr_line_match.start() + pos_offset, raw_zip),
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
                **self._bbox_kwargs(addr_line_match.start() + pos_offset, raw_state),
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
            corr_city, city_fixed = apply_ocr_correction(raw_city)
            city_m = FieldMetaResult(
                "city", raw_value=raw_city, corrected_value=corr_city,
                confidence=0.85, source_page=base_page,
                **self._bbox_kwargs(addr_line_match.start() + pos_offset, raw_city),
                correction_applied=city_fixed, extraction_method=method
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
                **self._bbox_kwargs(addr_line_match.start() + pos_offset, raw_city),
                extraction_method="regex_fallback" if raw_city else "not_found"
            )

        # ── Step 4: street ────────────────────────────────────────────────────
        raw_street = re.sub(r'(?:City|CITY)[:\s].*$', '', raw_street if 'raw_street' in dir() else before_state, flags=re.I).strip()
        corr_street, street_fixed = apply_ocr_correction(raw_street)
        street_m = FieldMetaResult(
            "property_address", raw_value=raw_street, corrected_value=corr_street,
            confidence=0.85, source_page=base_page,
            **self._bbox_kwargs(addr_line_match.start() + pos_offset, raw_street),
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

                corr_value, was_corrected = apply_ocr_correction(raw_value)
                source_page = page_for_pos(match.start() + pos_offset, page_pos)

                # Confidence decreases for fallback patterns
                confidence = 0.88 - (i * 0.10)
                if was_corrected:
                    confidence -= 0.05
                confidence = round(max(0.30, confidence), 3)

                method = "spatial_anchor" if i == 0 else "regex_fallback"

                return FieldMetaResult(
                    field_name=field_name,
                    raw_value=raw_value,
                    corrected_value=corr_value,
                    confidence=confidence,
                    source_page=source_page,
                    **self._bbox_kwargs(match.start() + pos_offset, raw_value),
                    correction_applied=was_corrected,
                    extraction_method=method,
                )

        return FieldMetaResult(field_name=field_name, confidence=0.0, extraction_method="not_found")

    def _extract_text_block(
        self,
        field_name: str,
        text: str,
        patterns: List[str],
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> FieldMetaResult:
        """Extract a longer commentary/description block."""
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.DOTALL)
            if match:
                raw_value = match.group(1).strip()
                source_page = page_for_pos(match.start() + pos_offset, page_pos)
                return FieldMetaResult(
                    field_name=field_name,
                    raw_value=raw_value,
                    corrected_value=raw_value,
                    confidence=0.75,
                    source_page=source_page,
                    **self._bbox_kwargs(match.start() + pos_offset, raw_value),
                    extraction_method="regex_primary",
                )
        return FieldMetaResult(field_name=field_name, confidence=0.0, extraction_method="not_found")

    def _bbox_kwargs(self, absolute_pos: int, value: Optional[str]) -> Dict[str, float]:
        """
        Build a normalized approximate bbox from text position.

        The current OCR cache stores page text but not Tesseract/PDF word boxes.
        This gives the reviewer a stable field-neighborhood highlight now; true
        OCR geometry can replace these values later without changing the API.
        """
        if not value or not self._page_positions:
            return {}

        starts = [p[0] for p in self._page_positions]
        idx = max(0, bisect_right(starts, absolute_pos) - 1)
        page_start, page_num = self._page_positions[idx]
        word_bbox = self._word_bbox(page_num, value)
        if word_bbox:
            return word_bbox

        page_text = self._page_index.get(page_num, "")
        if not page_text:
            return {}

        page_offset = max(0, absolute_pos - page_start)
        before = page_text[: min(page_offset, len(page_text))]
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

    def _checkbox_state(self, text: str, label: str) -> Optional[bool]:
        """
        Three-state checkbox detection with LLaVA vision fallback.

        Step 1: OCR text patterns (instant, always runs first)
          [X] or [x] near label → True  (YES, checked)
          [ ] near label        → False (NO, explicitly unchecked)

        Step 2: LLaVA vision (only when Step 1 returns None)
          Sends the page image crop to local LLaVA model
          Asks: "Is the checkbox next to '{label}' checked? YES or NO only."

        Returns None only when both steps fail → VERIFY in rules.
        """
        label_esc = re.escape(label)

        # Step 1: OCR text — [X]/[x] = checked, [ ] = unchecked
        checked   = rf"(?:\[x\]|\[X\]|X|><)\s*{label_esc}|{label_esc}\s*(?:\[x\]|\[X\]|X|><)"
        unchecked = rf"\[\s\]\s*{label_esc}|{label_esc}\s*\[\s\]"

        if re.search(checked, text, re.I):
            return True
        if re.search(unchecked, text, re.I):
            return False

        # Step 2: LLaVA vision (page_image stored in self._page_images by extract_subject)
        if _VISION_OK and detect_checkbox_vision and self._page_images:
            # Try page 1 first (main form), then pages 2 and 3
            for pg_num in [1, 2, 3]:
                page_img = self._page_images.get(pg_num)
                if page_img is not None:
                    result = detect_checkbox_vision(page_img, label)
                    if result is not None:
                        logger.debug(
                            "LLaVA checkbox '%s' page %d -> %s",
                            label, pg_num, result
                        )
                        return result

        return None  # both steps failed → VERIFY

    # ── Comparable extraction ──────────────────────────────────────────────────

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
        """
        comps = []

        # ── Strategy 1: find explicit COMPARABLE headers ──────────────────────
        for comp_num in range(1, 4):
            next_num = comp_num + 1
            section_match = re.search(
                rf"COMPARABLE\s+(?:SALE\s+)?(?:NO\.?\s*|#\s*)?{comp_num}[^\d](.*?)"
                rf"(?:COMPARABLE\s+(?:SALE\s+)?(?:NO\.?\s*|#\s*)?{next_num}[^\d]|$)",
                text, re.I | re.DOTALL
            )

            if not section_match:
                comps.append({})
                continue

            comp_text = section_match.group(1)[:600]
            base_page = page_for_pos(section_match.start() + pos_offset, page_pos)

            addr_match = re.search(r'(\d+\s+[A-Za-z][A-Za-z0-9 \.\,]{5,60})', comp_text)
            price_match = re.search(r'\$\s*([\d,]{5,})', comp_text)
            if not price_match:
                price_match = re.search(r'\b([\d]{3},[\d]{3})\b', comp_text)

            comps.append({
                "address": FieldMetaResult(
                    f"comp_{comp_num}_address",
                    raw_value=addr_match.group(1).strip() if addr_match else None,
                    corrected_value=addr_match.group(1).strip() if addr_match else None,
                    confidence=0.70 if addr_match else 0.0,
                    source_page=base_page,
                    extraction_method="spatial_anchor" if addr_match else "not_found",
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
        if all_empty:
            # In the sales grid, comp addresses appear as 3 addresses after "Subject"
            # Look for lines with street addresses in groups of 3-4
            addr_lines = re.findall(r'(\d+\s+[A-Za-z][A-Za-z0-9 \.\,]{5,50})', text)
            # Filter to only look like street addresses (has directional/type suffix)
            street_lines = [
                a for a in addr_lines
                if re.search(r'\b(?:St|Ave|Rd|Blvd|Ln|Dr|Way|Ct|Pl|Cir|Hwy|N|S|E|W|NE|NW|SE|SW)\b', a, re.I)
            ]
            if len(street_lines) >= 2:
                for i, sl in enumerate(street_lines[1:4], 1):
                    if i <= len(comps):
                        existing = comps[i - 1].get("address")
                        if existing is None or existing.value is None:
                            comps[i - 1]["address"] = FieldMetaResult(
                                f"comp_{i}_address", raw_value=sl, corrected_value=sl,
                                confidence=0.55, extraction_method="regex_fallback",
                            )

        return comps

    def _trim_merged_person_field(self, field: Optional[FieldMetaResult]) -> None:
        """Cut OCR spillover from the neighboring Subject-section cells."""
        if not field or not field.value:
            return

        value = field.value
        boundary = re.search(
            r"\b(?:Owner of Public Record|Property Address|City|County|Legal Description|"
            r"Assessor|Tax Year|Occupant|Map Reference|Census Tract|Lender|Client)\b",
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
