"""form_llm_extractor — Groq LLM gap-fill for all URAR form sections — v0.1.21.

Covers: Subject/Contract (page 1), Neighborhood (N-1 to N-7), Reconciliation,
Cost Approach, Signature block, and USPAP Addendum. Named "form" because it
spans every section of the appraisal form, not only the subject section.

Why this exists: Camelot label regexes and spatial anchors miss whole blocks of
the URAR — the page-1 subject/contract answers, the page-2 reconciliation
values, the cost-approach figures, the signature-block license dates and the
USPAP addendum fields — which leaves the S/C, R-1b, CA-3, DOC-1 and ADD-9 rules
blind (they land on extraction-gap VERIFYs for every report).

This module is the same "brain" pattern as sca_llm_extractor: it reads page
TEXT the deterministic pipeline already produced (the "eyes"), asks the LLM
only for the fields the deterministic layers MISSED, and verbatim-validates
every free-text/numeric answer against the source page before trusting it — a
value that does not literally appear on the page is dropped, so hallucination
cannot pass through. Enum/checkbox-style answers cannot be substring-validated,
so they are emitted BELOW the structured confidence cutoff: the rule engine
then asserts them only as VERIFY, never an automatic FAIL.

Fields are organized into PAGE GROUPS, each with a predicate that locates its
form page; one LLM call covers each group's missing fields. Boundary: returns
{canonical_field: (value, confidence)}. Empty dict on any failure so the caller
keeps its deterministic result (P-6). Performs NO OCR, never sees images.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from app import config
from app.extraction import llm_groq

logger = logging.getLogger(__name__)

SUBJECT_LLM_VERSION = "0.1.21"

# Confidence stamps. Verbatim-validated values sit just above the structured
# cutoff (0.75) — the value literally appears on the page. Enum/checkbox-style
# answers sit below it so rules downgrade any assertion to VERIFY.
CONF_VALIDATED = 0.82
CONF_ENUM = 0.70

# field -> (kind, allowed-values-or-None). kind: text | number | enum
_SUBJECT_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
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

# ---- neighborhood section (page 1 of the URAR) ----
# The deterministic layer reads the narrative fill-ins of this section unreliably
# — it confidently grabs the printed form LABEL (e.g. the "(including support for
# the above conclusions)" caption) instead of the appraiser's text. These go
# through the LLM verbatim reader, which distinguishes label from fill-in.
#
# N-1/N-2 checkbox fields are included here as ENUM fallbacks: the L1 visual
# checkbox extractor and L5 yes/no scanner cover these first; the LLM only fills
# them when those layers return empty (extract_gap_fields_llm skips populated fields).
_NEIGHBORHOOD_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    # N-1 area characteristic checkboxes
    "location":      ("enum", ("Urban", "Suburban", "Rural")),
    "built_up":      ("enum", ("Over 75%", "25-75%", "Under 25%")),
    "growth_rate":   ("enum", ("Rapid", "Stable", "Slow")),
    # N-2 housing trend checkboxes
    "property_values": ("enum", ("Increasing", "Stable", "Declining")),
    "demand_supply":   ("enum", ("Shortage", "In Balance", "Over Supply")),
    "marketing_time":  ("enum", ("Under 3 Mths", "3-6 Mths", "Over 6 Mths")),
    # N-3 price/age grid (in $000 and years respectively)
    "price_low":           ("number", None),
    "price_high":          ("number", None),
    "predominant_price":   ("number", None),
    "age_low":             ("number", None),
    "age_high":            ("number", None),
    "predominant_age":     ("number", None),
    # N-4 land use percentages
    "land_use_one_unit":        ("number", None),
    "land_use_2_4_unit":        ("number", None),
    "land_use_multi_family":    ("number", None),
    "land_use_commercial":      ("number", None),
    "land_use_other":           ("number", None),
    "land_use_other_description": ("text", None),
    # N-5 / N-6 / N-7 narratives
    "neighborhood_boundaries":      ("text", None),
    "neighborhood_description":     ("text", None),
    "market_conditions_commentary": ("text", None),
}

# Narrative fields the deterministic layer reads confidently-wrong (it returns a
# printed label, not blank), so a blank/low-confidence trigger never re-fills
# them. These are always sent to the LLM; the longer/more-complete answer wins.
ALWAYS_REFILL = frozenset({
    "neighborhood_boundaries", "neighborhood_description",
    "market_conditions_commentary",
})

_RECON_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    "indicated_value_cost_approach": ("number", None),
    "indicated_value_income_approach": ("number", None),
    "appraisal_subject_to": ("enum", ("As Is", "Subject To Completion",
                                      "Subject To Repairs", "Subject To Inspection")),
    "final_reconciliation_comment": ("text", None),
}

_COST_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    "site_value_estimate": ("number", None),
    "cost_new_improvements": ("number", None),
    "total_depreciation": ("number", None),
    "depreciated_cost_improvements": ("number", None),
    "remaining_economic_life": ("number", None),
}

_SIGNATURE_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    "date_of_signature": ("text", None),
    "appraiser_cert_expiration_date": ("text", None),
    "appraiser_state_cert_number": ("text", None),
    "appraiser_cert_state": ("text", None),
}

_USPAP_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    "appraisal_report_type": ("enum", ("Appraisal Report", "Restricted Appraisal Report")),
    "reasonable_exposure_time": ("text", None),
    "prior_services_performed": ("text", None),
}

# group -> (page predicate over lowercased page text, field table, page label
# for the prompt). The predicate locates the form page the group lives on.
PAGE_GROUPS = {
    "subject": (
        lambda low: "property address" in low and ("owner of public record" in low
                                                   or "assessor" in low),
        _SUBJECT_FIELDS, "page 1 (SUBJECT and CONTRACT sections)"),
    "neighborhood": (
        lambda low: "present land use" in low or "neighborhood boundaries" in low
                    or ("market conditions" in low and "one-unit housing" in low),
        _NEIGHBORHOOD_FIELDS, "NEIGHBORHOOD section (page 1: characteristics, "
        "housing trends, one-unit price/age ranges, present land use, boundaries, "
        "and the market-conditions narrative)"),
    "reconciliation": (
        lambda low: "indicated value by" in low and ("reconciliation" in low
                                                     or "sales comparison approach" in low),
        _RECON_FIELDS, "RECONCILIATION section (bottom of the sales comparison page)"),
    "cost": (
        lambda low: "opinion of site value" in low or "estimated remaining economic" in low,
        _COST_FIELDS, "COST APPROACH section"),
    "signature": (
        lambda low: "expiration date" in low and ("signature" in low or "appraiser" in low),
        _SIGNATURE_FIELDS, "APPRAISER signature/certification block"),
    "uspap": (
        lambda low: "exposure time" in low or "restricted appraisal report" in low,
        _USPAP_FIELDS, "USPAP addendum"),
}

# union across groups — the overlay computes its missing-fields list from this
GAP_FIELDS: Dict[str, Tuple[str, Optional[tuple]]] = {
    f: spec for _, table, _ in PAGE_GROUPS.values() for f, spec in table.items()
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
    "indicated_value_cost_approach": "Indicated Value by: Cost Approach (if developed) $",
    "indicated_value_income_approach": "Indicated Value by: Income Approach (if developed) $",
    "appraisal_subject_to": "'This appraisal is made' checkbox: As Is / Subject To ...",
    "final_reconciliation_comment": "the reconciliation narrative (which approach was weighted and why), VERBATIM",
    "site_value_estimate": "OPINION OF SITE VALUE $",
    "cost_new_improvements": "total cost-new of improvements $",
    "total_depreciation": "total Depreciation $ (physical+functional+external)",
    "depreciated_cost_improvements": "Depreciated Cost of Improvements $",
    "remaining_economic_life": "Estimated Remaining Economic Life (years)",
    "date_of_signature": "Date of Signature and Report (MM/DD/YYYY as printed)",
    "appraiser_cert_expiration_date": "Expiration Date of Certification or License (as printed)",
    "appraiser_state_cert_number": "State Certification # or License #",
    "appraiser_cert_state": "the State of the certification/license (2-letter code)",
    "appraisal_report_type": "USPAP identification checkbox: Appraisal Report or Restricted Appraisal Report",
    "reasonable_exposure_time": (
        "Copy ONLY the time-period value (e.g. '30-180 Days', 'Under 3 months', '90 days') "
        "from the sentence 'My opinion of a reasonable exposure time … is: <VALUE>'. "
        "Do NOT copy section headings such as 'Additional Certifications'."
    ),
    "prior_services_performed": "the prior-services disclosure (HAVE / HAVE NOT performed services, plus any description)",
    # ---- neighborhood checkboxes (N-1 / N-2) ----
    "location":       "Location checkbox — mark the ONE checked box: Urban, Suburban, or Rural",
    "built_up":       "Built-Up checkbox — mark the ONE checked box: Over 75%, 25-75%, or Under 25%",
    "growth_rate":    "Growth Rate checkbox — mark the ONE checked box: Rapid, Stable, or Slow",
    "property_values":"Property Values checkbox — mark the ONE checked box: Increasing, Stable, or Declining",
    "demand_supply":  "Demand/Supply checkbox — mark the ONE checked box: Shortage, In Balance, or Over Supply",
    "marketing_time": "Marketing Time checkbox — mark the ONE checked box: Under 3 Mths, 3-6 Mths, or Over 6 Mths",
    # ---- neighborhood price/age grid (N-3) — IMPORTANT: these are TWO separate columns ----
    "price_low":          "One-Unit Housing PRICE range LOW — a dollar amount in $(000)s, e.g. 260 means $260,000. This is in the PRICE column (left side of the grid). Do NOT confuse with Age.",
    "price_high":         "One-Unit Housing PRICE range HIGH — a dollar amount in $(000)s, e.g. 725 means $725,000. This is in the PRICE column (left side). Do NOT confuse with Age.",
    "predominant_price":  "One-Unit Housing PRICE Predominant — the most common price in $(000)s. PRICE column.",
    "age_low":            "One-Unit Housing AGE range LOW — the youngest building age in YEARS (0-200). This is in the AGE column (right side of the grid). Do NOT confuse with Price.",
    "age_high":           "One-Unit Housing AGE range HIGH — the oldest building age in YEARS (0-200). AGE column (right side).",
    "predominant_age":    "One-Unit Housing AGE Predominant — the most common building age in YEARS. AGE column.",
    # ---- land use percentages (N-4) ----
    "land_use_one_unit":        "Present Land Use One-Unit %",
    "land_use_2_4_unit":        "Present Land Use 2-4 Unit %",
    "land_use_multi_family":    "Present Land Use Multi-Family %",
    "land_use_commercial":      "Present Land Use Commercial %",
    "land_use_other":           "Present Land Use Other %",
    "land_use_other_description": "Present Land Use 'Other' description text (what the Other category is)",
    # ---- neighborhood narratives (N-5 / N-6 / N-7) ----
    "neighborhood_boundaries": "Neighborhood Boundaries — the appraiser's written boundary description (the fill-in text after the label, NOT the printed 'Neighborhood Boundaries' caption)",
    "neighborhood_description": "Neighborhood Description — the appraiser's narrative fill-in (NOT the printed 'Neighborhood Description' caption)",
    "market_conditions_commentary": "Market Conditions narrative — the appraiser's written analysis. IGNORE the printed caption text 'Market Conditions (including support for the above conclusions)'; return only the appraiser's own sentences",
}

_SYSTEM = (
    "You read pages of a URAR / Form 1004 residential appraisal report. "
    "Output ONLY one valid JSON object and nothing else."
)


def _prompt(page_text: str, fields, page_label: str) -> str:
    lines = "\n".join(f'- "{f}": {_FIELD_HINTS.get(f, f)}' for f in fields)
    return (
        f"Below is the spatially-reconstructed text of the {page_label} of an "
        "appraisal report. Extract ONLY these fields:\n"
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


def _spatial_text(page) -> str:
    """Row-clustered, column-ordered text of one pdfplumber page — labels sit on
    the same line as their fill-in values (same approach as the SCA grid reader)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    lines: Dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"] / 3.0), []).append(w)
    return "\n".join(
        " ".join(w["text"] for w in sorted(lines[yk], key=lambda w: w["x0"]))
        for yk in sorted(lines)
    )


def _group_pages(pdf_path, groups) -> Dict[str, str]:
    """{group: spatial page text} for each requested group whose page is found.

    Page candidates are screened with the cheap embedded-text read; only the
    matched page is spatially reconstructed (pdfplumber is the slow part)."""
    import fitz
    import pdfplumber

    matches: Dict[str, int] = {}
    doc = fitz.open(str(Path(pdf_path)))
    try:
        for i in range(doc.page_count):
            if len(matches) == len(groups):
                break
            low = doc[i].get_text().lower()
            for g in groups:
                if g not in matches and PAGE_GROUPS[g][0](low):
                    matches[g] = i
    finally:
        doc.close()
    if not matches:
        return {}
    out: Dict[str, str] = {}
    with pdfplumber.open(str(Path(pdf_path))) as pdf:
        for g, i in matches.items():
            try:
                out[g] = _spatial_text(pdf.pages[i])
            except Exception as exc:
                logger.debug("Spatial read failed for %s page %d: %s", g, i, exc)
    return out


_DIGITS = re.compile(r"\d+")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _validate(spec, value: str, page_text: str) -> Optional[Tuple[str, float]]:
    """Verbatim-validate one LLM answer against its page. Returns (value, conf)
    or None when the answer cannot be trusted."""
    kind, allowed = spec
    v = str(value).strip()
    if not v or len(v) > 2000:
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


# Land-use category labels the LLM sometimes returns when the boundary fill-in is
# blank/sparse — a real boundary is directional/geographic prose, never one of these.
_LANDUSE_LABEL = re.compile(
    r"^\s*(high|low|avg|average)?\s*"
    r"(commercial|one[\- ]?unit|multi[\- ]?family|2[\- ]?4 ?unit|other|vacant)\s*%?\s*$",
    re.I)


def _field_sane(field: str, value: str) -> bool:
    """Field-specific guard beyond verbatim validation: rejects a value the LLM
    mis-mapped from a neighbouring cell (e.g. a land-use % label returned as the
    neighborhood boundaries, or an age value returned as a price field)."""
    if field == "neighborhood_boundaries":
        if "%" in value or _LANDUSE_LABEL.match(value):
            return False
    # N-3 price/age disambiguation.
    # Prices are in $(000)s — realistic range 10..5000 (= $10K..$5M).
    # Ages are in years — realistic range 0..200.
    # A value of "1" in price_low would mean $1,000 which is implausible;
    # a value of "500" in age_high means 500 years which is implausible.
    _PRICE_FIELDS = {"price_low", "price_high", "predominant_price"}
    _AGE_FIELDS   = {"age_low", "age_high", "predominant_age"}
    if field in _PRICE_FIELDS or field in _AGE_FIELDS:
        try:
            num = float(re.sub(r"[^\d.]", "", value))
        except (ValueError, TypeError):
            return False
        if field in _PRICE_FIELDS and num < 10:
            return False   # < $10K in $000 notation → almost certainly an age value
        if field in _AGE_FIELDS and num > 200:
            return False   # > 200 years → almost certainly a price value
    return True


def _gap_call_by_page(live_pages, wanted) -> Dict[str, Tuple[str, float]]:
    """FORM_LLM_BATCH path: ONE LLM call per UNIQUE PAGE, not per group.

    Several form groups can resolve to the SAME physical page — on a standard URAR
    the Subject (+Contract) and Neighborhood sections are both on page 1; Cost and
    USPAP often share a page. The per-group path sends that page's text once per
    group (pure duplication). This groups by identical page text and makes ONE call
    per page with the UNION of that page's wanted fields — so each page is sent once.

    Safe-by-construction vs the old all-pages merge:
      • Each prompt carries exactly ONE page's text → never exceeds the per-request
        token ceiling (the 413 the all-pages merge hit).
      • The prompt format is the SAME as the per-group path (`_prompt`), only the
        field list is the union → minimal behavioural change.
      • Every value is still verbatim-validated against THIS page (P-14a).
      • If every group is on a different page, this is identical to per-group.
    """
    from collections import OrderedDict
    by_page: "OrderedDict[str, list]" = OrderedDict()
    for g, text in live_pages.items():
        by_page.setdefault(text, []).append(g)

    out: Dict[str, Tuple[str, float]] = {}
    for text, groups in by_page.items():
        field_to_group: Dict[str, str] = {}
        ordered_fields: list = []
        labels: list = []
        for g in groups:
            _, _table, page_label = PAGE_GROUPS[g]
            labels.append(page_label)
            for f in wanted[g]:
                if f not in field_to_group:
                    field_to_group[f] = g
                    ordered_fields.append(f)
        if not ordered_fields:
            continue
        page_label = " + ".join(dict.fromkeys(labels))  # combined, de-duped label
        data = llm_groq.chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _prompt(text[:11000], ordered_fields, page_label)},
            ],
            reasoning_effort="low",
            max_tokens=3072,  # headroom for a page hosting two sections' fields
        )
        if not isinstance(data, dict):
            continue
        for field, raw in data.items():
            g = field_to_group.get(field)
            if g is None or raw is None:
                continue
            _, table, _ = PAGE_GROUPS[g]
            ok = _validate(table[field], str(raw), text)
            if ok is not None and _field_sane(field, ok[0]):
                out[field] = ok
    return out


def extract_gap_fields_llm(pdf_path, missing_fields) -> Dict[str, Tuple[str, float]]:
    """Return {field: (value, confidence)} for the requested missing fields.

    Default: one LLM call per page group that has gaps. When FORM_LLM_BATCH is on
    AND more than one group has gaps, the calls are collapsed into a single combined
    call (same verbatim validation, fewer requests — see _batched_gap_call).

    Only fields listed in PAGE_GROUPS are ever requested; every answer is
    validated before being returned. Empty dict on any failure (P-6).
    """
    if not llm_groq.groq_extraction_available():
        return {}
    wanted = {g: [f for f in missing_fields if f in table]
              for g, (_, table, _) in PAGE_GROUPS.items()}
    wanted = {g: fs for g, fs in wanted.items() if fs}
    if not wanted:
        return {}
    name = getattr(pdf_path, "name", str(pdf_path))
    try:
        pages = _group_pages(pdf_path, list(wanted))
    except Exception as exc:
        logger.warning("Gap-fill page read failed for %s: %s", name, exc)
        return {}

    out: Dict[str, Tuple[str, float]] = {}
    live = {g: t for g, t in pages.items() if t.strip()}
    # Per-page merge: one call per UNIQUE page (co-page groups share one call). When
    # no two groups share a page this is identical to the per-group path, so it is
    # safe to enable broadly. Off by default until measured (P-8) — flip FORM_LLM_BATCH.
    if config.FORM_LLM_BATCH and len(live) >= 1:
        out = _gap_call_by_page(live, wanted)
    else:
        for g, text in live.items():
            _, table, page_label = PAGE_GROUPS[g]
            data = llm_groq.chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _prompt(text[:11000], wanted[g], page_label)},
                ],
                reasoning_effort="low",
                max_tokens=2048,
            )
            if not isinstance(data, dict):
                continue
            for field, raw in data.items():
                if field not in wanted[g] or raw is None:
                    continue
                ok = _validate(table[field], str(raw), text)
                if ok is not None and _field_sane(field, ok[0]):
                    out[field] = ok
    if out:
        logger.info(
            "Gap-fill LLM v%s filled %d/%d requested fields (%s) for %s: %s",
            SUBJECT_LLM_VERSION, len(out), len(missing_fields),
            "+".join(sorted(pages)), name, sorted(out),
        )
    return out


def extract_subject_contract_llm(pdf_path, missing_fields) -> Dict[str, Tuple[str, float]]:
    """Back-compat wrapper: the original subject/contract-only entry point."""
    subject_only = [f for f in missing_fields if f in _SUBJECT_FIELDS]
    return extract_gap_fields_llm(pdf_path, subject_only)
