"""LLM gap-fill of the SUBJECT + CONTRACT sections — extraction layer v0.1.17.

Why this exists: the deterministic layers (Camelot label regexes, spatial
anchors) read the page-1 subject/contract blocks of the URAR unevenly — fields
like Tax Year, Map Reference, Census Tract, Special Assessments, Occupancy and
the contract-section answers are frequently NOT_FOUND, which leaves the S-4/S-6/
S-7/S-8 and C-1/C-3/C-4 rules blind.

This module is the same "brain" pattern as sca_llm_extractor: it reads page TEXT
that the deterministic pipeline already produced (the "eyes"), asks the LLM only
for the fields the deterministic layers MISSED, and verbatim-validates every
free-text/numeric answer against the source text before trusting it — a value
that does not literally appear on the page is dropped, so hallucination cannot
pass through. Enum/boolean answers cannot be substring-validated (checkbox
glyphs), so they are emitted at LOWER confidence than the structured cutoff:
the rule engine then asserts them only as VERIFY, never an automatic FAIL.

Boundary: returns {canonical_field: value}. Empty dict on any failure so the
caller keeps its deterministic result (P-6). Performs NO OCR, never sees images.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.extraction import llm_groq

logger = logging.getLogger(__name__)

SUBJECT_LLM_VERSION = "0.1.17"

# Confidence stamps. Verbatim-validated values sit just above the structured
# cutoff (0.75) — the value literally appears on the page. Enum/checkbox-style
# answers sit below it so rules downgrade any assertion to VERIFY.
CONF_VALIDATED = 0.82
CONF_ENUM = 0.70

# field -> (kind, allowed-values-or-None). kind: text | number | enum
GAP_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    # ---- subject section ----
    "owner_of_public_record": ("text", None),
    "legal_description": ("text", None),
    "assessors_parcel_number": ("text", None),
    "tax_year": ("number", None),
    "real_estate_taxes": ("number", None),
    "neighborhood_name": ("text", None),
    "map_reference": ("text", None),
    "census_tract": ("text", None),
    "special_assessments": ("number", None),
    "hoa_dues": ("number", None),
    "data_source": ("text", None),
    "occupant_status": ("enum", ("Owner", "Tenant", "Vacant")),
    "property_rights": ("enum", ("Fee Simple", "Leasehold", "De Minimis PUD", "Other")),
    "offered_for_sale_12mo": ("enum", ("Yes", "No")),
    # ---- contract section (page 1 of the URAR) ----
    "contract_price": ("number", None),
    "contract_date": ("text", None),
    "sale_type": ("enum", ("Arms-Length", "Non Arms-Length", "REO", "Short Sale",
                           "Court Ordered", "Estate Sale", "Foreclosure")),
    "did_analyze_contract": ("enum", ("Yes", "No")),
    "is_seller_owner_of_record": ("enum", ("Yes", "No")),
    "owner_record_data_source": ("text", None),
    "has_financial_assistance": ("enum", ("Yes", "No")),
    "financial_assistance_amount": ("number", None),
    "financial_assistance_description": ("text", None),
}

_FIELD_HINTS = {
    "owner_of_public_record": "Owner of Public Record",
    "legal_description": "Legal Description",
    "assessors_parcel_number": "Assessor's Parcel # (APN)",
    "tax_year": "Tax Year (4 digits)",
    "real_estate_taxes": "R.E. Taxes $ (annual amount)",
    "neighborhood_name": "Neighborhood Name",
    "map_reference": "Map Reference",
    "census_tract": "Census Tract",
    "special_assessments": "Special Assessments $ amount",
    "hoa_dues": "HOA $ dues amount",
    "data_source": "Data Source(s) for the offered-for-sale question",
    "occupant_status": "Occupant checkbox: Owner, Tenant or Vacant",
    "property_rights": "Property Rights Appraised checkbox",
    "offered_for_sale_12mo": "Is the subject currently/was offered for sale in the prior 12 months: Yes/No",
    "contract_price": "Contract Price $ (contract section)",
    "contract_date": "Date of Contract (MM/DD/YYYY as printed)",
    "sale_type": "type of sale identified in the contract analysis",
    "did_analyze_contract": "'I did / did not analyze the contract for sale' — Yes if did",
    "is_seller_owner_of_record": "Is the property seller the owner of public record: Yes/No",
    "owner_record_data_source": "Data Source(s) for the seller/owner-of-record question",
    "has_financial_assistance": "Is there any financial assistance/concessions: Yes/No",
    "financial_assistance_amount": "financial assistance / concession $ amount",
    "financial_assistance_description": "description of items to be paid by any party",
}

_SYSTEM = (
    "You read page 1 (SUBJECT and CONTRACT sections) of a URAR / Form 1004 "
    "residential appraisal report. Output ONLY one valid JSON object and nothing else."
)


def _prompt(page_text: str, fields) -> str:
    lines = "\n".join(f'- "{f}": {_FIELD_HINTS.get(f, f)}' for f in fields)
    return (
        "Below is the spatially-reconstructed text of an appraisal report page "
        "containing the SUBJECT and CONTRACT sections. Extract ONLY these fields:\n"
        f"{lines}\n\n"
        "Rules:\n"
        "- Copy free-text values VERBATIM as they appear in the text (same casing, "
        "same punctuation). Do NOT paraphrase, complete, or normalize.\n"
        "- For dollar/number fields return digits only (no $ or commas).\n"
        "- For checkbox questions answer with the marked option only (an 'X' or "
        "similar mark sits next to the selected option).\n"
        "- OMIT any field whose value is not actually present on the page. Never guess.\n"
        'Return JSON: {"<field>": "<value>", ...} with only the fields you found.\n\n'
        "PAGE TEXT:\n" + page_text
    )


def _page_one_text(pdf_path) -> str:
    """Spatially reconstruct the subject/contract page: cluster words by row (y),
    sort by column (x) — same approach as the SCA grid reader, so labels sit on
    the same line as their fill-in values."""
    import pdfplumber

    with pdfplumber.open(str(Path(pdf_path))) as pdf:
        # subject+contract are on the first form page; scan the first 3 pages and
        # pick the first that looks like the URAR page 1.
        for i in range(min(3, len(pdf.pages))):
            page = pdf.pages[i]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            lines: Dict[int, list] = {}
            for w in words:
                lines.setdefault(round(w["top"] / 3.0), []).append(w)
            text = "\n".join(
                " ".join(w["text"] for w in sorted(lines[yk], key=lambda w: w["x0"]))
                for yk in sorted(lines)
            )
            low = text.lower()
            if "property address" in low and ("owner of public record" in low
                                              or "assessor" in low):
                return text
    return ""


_DIGITS = re.compile(r"\d+")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _validate(field: str, value: str, page_text: str) -> Optional[Tuple[str, float]]:
    """Verbatim-validate one LLM answer against the page. Returns (value, conf)
    or None when the answer cannot be trusted."""
    kind, allowed = GAP_FIELDS[field]
    v = str(value).strip()
    if not v or len(v) > 300:
        return None
    if kind == "enum":
        # accept only an allowed option (case-insensitive); never substring-check
        for opt in allowed:
            if _norm_ws(v) == _norm_ws(opt):
                return opt, CONF_ENUM
        return None
    if kind == "number":
        digits = re.sub(r"[^\d]", "", v)
        if not digits:
            return None
        # the digit-run must literally appear on the page (commas/$ stripped so
        # "8,555" validates a returned "8555")
        runs = set(_DIGITS.findall(re.sub(r"[,$]", "", page_text)))
        if digits not in runs:
            return None
        return digits, CONF_VALIDATED
    # text: normalized substring containment
    if _norm_ws(v) not in _norm_ws(page_text):
        return None
    return v, CONF_VALIDATED


def extract_subject_contract_llm(pdf_path, missing_fields) -> Dict[str, Tuple[str, float]]:
    """Return {field: (value, confidence)} for the requested missing fields.

    Only fields listed in GAP_FIELDS are ever requested; every answer is
    validated before being returned. Empty dict on any failure (P-6).
    """
    fields = [f for f in missing_fields if f in GAP_FIELDS]
    if not fields or not llm_groq.groq_extraction_available():
        return {}
    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        text = _page_one_text(pdf_path)
    except Exception as exc:
        logger.warning("Subject-LLM page read failed for %s: %s", name, exc)
        return {}
    if not text.strip():
        return {}

    data = llm_groq.chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(text[:11000], fields)},
        ],
        reasoning_effort="low",
        max_tokens=2048,
    )
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Tuple[str, float]] = {}
    for field, raw in data.items():
        if field not in fields or raw is None:
            continue
        ok = _validate(field, str(raw), text)
        if ok is not None:
            out[field] = ok
    if out:
        logger.info(
            "Subject-LLM v%s gap-filled %d/%d requested fields for %s: %s",
            SUBJECT_LLM_VERSION, len(out), len(fields), name, sorted(out),
        )
    return out
