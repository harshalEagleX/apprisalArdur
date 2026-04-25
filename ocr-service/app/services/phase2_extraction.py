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

    def extract_subject(
        self,
        full_text: str,
        page_index: Dict[int, str],
    ) -> Tuple[SubjectSectionExtract, Dict[str, FieldMetaResult]]:
        """
        Extract Subject Section fields with full per-field metadata.

        Returns:
            (SubjectSectionExtract, dict of field_name → FieldMetaResult)
        """
        # Apply OCR corrections to the full text before any regex
        corrected_text, correction_count = self._correct_text(full_text)
        if correction_count > 0:
            logger.info("Applied %d OCR corrections to document text", correction_count)

        # Build position → page map
        page_pos = build_page_position_map(page_index)

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
            r"Borrower[:\s]+(?!Lender|Client|File|Property|Owner)([^\n]{3,80})",
            r"BORROWER[:\s]+(?!LENDER|CLIENT)([^\n]{3,80})",
        ], page_pos, pos_offset)

        meta["co_borrower_name"] = self._extract("co_borrower_name", text, [
            r"Co-?Borrower[:\s]+([^\n]{3,80})",
            r"CO-?BORROWER[:\s]+([^\n]{3,80})",
        ], page_pos, pos_offset)

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
        occupant = self._detect_checkbox(text, {
            "Owner":  r"(?:\[x\]|\[X\]|X|><)\s*[Oo]wner|[Oo]wner\s*(?:\[x\]|\[X\]|X|><)",
            "Tenant": r"(?:\[x\]|\[X\]|X|><)\s*[Tt]enant|[Tt]enant\s*(?:\[x\]|\[X\]|X|><)",
            "Vacant": r"(?:\[x\]|\[X\]|X|><)\s*[Vv]acant|[Vv]acant\s*(?:\[x\]|\[X\]|X|><)",
        })
        occ_m = FieldMetaResult("occupant_status", raw_value=occupant, corrected_value=occupant,
                                confidence=0.75 if occupant else 0.0,
                                extraction_method="regex_primary" if occupant else "not_found")
        meta["occupant_status"] = occ_m

        # ── S-8: Special Assessments ──────────────────────────────────────────
        meta["special_assessments"] = self._extract("special_assessments", text, [
            r"Special Assessments[:\s]*\$?([\d,]+)",
        ], page_pos, pos_offset)

        # ── S-9: PUD / HOA ────────────────────────────────────────────────────
        pud = bool(re.search(r"(?:\[x\]|\[X\]|X|><)\s*PUD|PUD\s*(?:\[x\]|\[X\]|X|><)", text))
        meta["is_pud_checked"] = FieldMetaResult(
            "is_pud_checked", raw_value=str(pud), corrected_value=str(pud),
            confidence=0.70, extraction_method="regex_primary"
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
            r"Lender/?Client[\s—:-]+([A-Za-z][A-Za-z\s]+(?:Corporation|Corp|Inc|LLC|Company|Co\.?|Bank|Mortgage|Credit Union))(?:\s+Address|$|\n)",
            r"Lender/?Client[\s—:-]+([^\n]{5,80})(?:Address|\n)",
        ], page_pos, pos_offset, post_clean=r'\s*Address.*$')

        meta["lender_address"] = self._extract("lender_address", text, [
            r"(?:Lender/?Client|Lender)\s+Address[:\s]+([^\n]+)",
        ], page_pos, pos_offset)

        # ── S-11: Property Rights ─────────────────────────────────────────────
        rights = self._detect_checkbox(text, {
            "Fee Simple":    r"(?:\[x\]|\[X\]|X|><)\s*[Ff]ee\s+[Ss]imple|[Ff]ee\s+[Ss]imple\s*(?:\[x\]|\[X\]|X|><)",
            "Leasehold":     r"(?:\[x\]|\[X\]|X|><)\s*[Ll]easehold|[Ll]easehold\s*(?:\[x\]|\[X\]|X|><)",
            "De Minimis PUD":r"(?:\[x\]|\[X\]|X|><)\s*[Dd]e\s+[Mm]inimis|[Dd]e\s+[Mm]inimis\s*(?:\[x\]|\[X\]|X|><)",
        })
        meta["property_rights"] = FieldMetaResult(
            "property_rights", raw_value=rights, corrected_value=rights,
            confidence=0.80 if rights else 0.0,
            extraction_method="regex_primary" if rights else "not_found"
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

            zip_m   = FieldMetaResult("zip_code",
                raw_value=zip_ind.group(1) if zip_ind else None,
                corrected_value=zip_ind.group(1) if zip_ind else None,
                confidence=0.80 if zip_ind else 0.0,
                source_page=base_page,
                extraction_method="spatial_anchor" if zip_ind else "not_found")

            state_m = FieldMetaResult("state",
                raw_value=state_ind.group(1).upper() if state_ind else None,
                corrected_value=state_ind.group(1).upper() if state_ind else None,
                confidence=0.80 if state_ind else 0.0,
                source_page=base_page,
                extraction_method="spatial_anchor" if state_ind else "not_found")

            city_m  = FieldMetaResult("city",
                raw_value=city_ind.group(1).strip() if city_ind else None,
                corrected_value=city_ind.group(1).strip() if city_ind else None,
                confidence=0.75 if city_ind else 0.0,
                source_page=base_page,
                extraction_method="spatial_anchor" if city_ind else "not_found")

            # Street is the address line itself
            raw_street = full_line
            corr_street, sf = apply_ocr_correction(raw_street)
            street_m = FieldMetaResult("property_address",
                raw_value=raw_street, corrected_value=corr_street,
                confidence=0.80, source_page=base_page,
                correction_applied=sf, extraction_method=method)
            return street_m, city_m, state_m, zip_m

        raw_zip = zip_match.group(1)
        corr_zip, zip_fixed = apply_ocr_correction(raw_zip)
        before_zip = full_line[:zip_match.start()].strip()

        zip_m = FieldMetaResult(
            "zip_code", raw_value=raw_zip, corrected_value=corr_zip,
            confidence=0.92, source_page=base_page,
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
                confidence=0.90, source_page=base_page, extraction_method=method
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
                extraction_method="regex_fallback" if raw_city else "not_found"
            )

        # ── Step 4: street ────────────────────────────────────────────────────
        raw_street = re.sub(r'(?:City|CITY)[:\s].*$', '', raw_street if 'raw_street' in dir() else before_state, flags=re.I).strip()
        corr_street, street_fixed = apply_ocr_correction(raw_street)
        street_m = FieldMetaResult(
            "property_address", raw_value=raw_street, corrected_value=corr_street,
            confidence=0.85, source_page=base_page,
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
                    extraction_method="regex_primary",
                )
        return FieldMetaResult(field_name=field_name, confidence=0.0, extraction_method="not_found")

    def _detect_checkbox(self, text: str, options: Dict[str, str]) -> Optional[str]:
        """Detect which checkbox is marked. Returns option key or None."""
        for label, pattern in options.items():
            if re.search(pattern, text):
                return label
        return None

    # ── Comparable extraction ──────────────────────────────────────────────────

    def _extract_comparables(
        self,
        text: str,
        page_pos: List[Tuple[int, int]],
        pos_offset: int,
    ) -> List[Dict[str, FieldMetaResult]]:
        """Extract address + price for up to 3 comparable sales."""
        comps = []
        for comp_num in range(1, 4):
            # Find the comparable section header
            section_match = re.search(
                rf"COMPARABLE\s+(?:SALE)?\s*(?:NO\.?\s*)?[#]?\s*{comp_num}(.*?)"
                rf"(?:COMPARABLE\s+(?:SALE)?\s*(?:NO\.?\s*)?[#]?\s*{comp_num+1}|$)",
                text, re.I | re.DOTALL
            )
            if not section_match:
                comps.append({})
                continue

            comp_text = section_match.group(1)
            base_page = page_for_pos(section_match.start() + pos_offset, page_pos)

            # Address: first line that looks like a street address
            addr_match = re.search(r'(\d+\s+[A-Za-z][^\n]{5,60})', comp_text)
            address_m = FieldMetaResult(
                f"comp_{comp_num}_address",
                raw_value=addr_match.group(1).strip() if addr_match else None,
                corrected_value=addr_match.group(1).strip() if addr_match else None,
                confidence=0.70 if addr_match else 0.0,
                source_page=base_page,
                extraction_method="regex_primary" if addr_match else "not_found"
            )

            # Sale price: dollar amount
            price_match = re.search(r'\$?\s*([\d,]{5,})', comp_text)
            raw_price = price_match.group(1) if price_match else None
            price_m = FieldMetaResult(
                f"comp_{comp_num}_sale_price",
                raw_value=raw_price,
                corrected_value=raw_price,
                confidence=0.72 if raw_price else 0.0,
                source_page=base_page,
                extraction_method="regex_primary" if raw_price else "not_found"
            )

            comps.append({"address": address_m, "sale_price": price_m})

        return comps

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
