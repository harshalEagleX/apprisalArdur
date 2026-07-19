"""
extraction/plausibility.py — step 8: type/range/format sanity per field.

SHALqc.md §3.2 step 8 / §3.3: "Value fails plausibility (garbage OCR) →
Suppressed → field = MISSING. Rule outcome: VERIFY, never FAIL." Column-based
and OCR-based extractors read a field by its position with no proof the value
*belongs* there — a 2-letter state code can land in `county`, a mailing zip in
a name field, an adjustment digit-bleed in a comp cell. This module is the
gate: it runs once, after merge, over the winning value per field, and
SUPPRESSES (never silently drops — the raw value survives in `raw_value`,
SHALqc.md P2) any value that is categorically impossible for its field.

Ported from ocr-service/app/extraction/field_validators.py, re-pointed at the
ExtractedField contract.

Scope, stated honestly: this catches type-confusion (values that CANNOT be
right for the field) at high precision. It does not catch a plausible-but-
wrong swap (e.g. appraised_value holding the contract_price) — that needs a
positive label anchor or a cross-field rule, not a range check.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, Optional

from app.extraction.result import ExtractedField

__version__ = "pla-1.0.0"

logger = logging.getLogger(__name__)

_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})
_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
_DIGITS_RE = re.compile(r"^[\d.,]+$")
_UAD_QUALITY = frozenset({"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"})
_UAD_CONDITION = frozenset({"C1", "C2", "C3", "C4", "C5", "C6"})

_MAX_SITE_ACRES = 250.0
_MAX_STRUCTURE_AGE = 150
_NET_ADJ_TOLERANCE = 5.0
_MAX_COMPS = 9


def _num(value: str) -> Optional[float]:
    try:
        # a leading "=" is a form/spreadsheet artifact ("= $158,868"); strip it,
        # but NEVER strip internal whitespace — "$575,000 $475,000" is a genuine
        # multi-value concatenation that must still fail to parse (and be rejected).
        return float(str(value).strip().lstrip("=").replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _field_num(fields: Dict[str, ExtractedField], name: str) -> Optional[float]:
    r = fields.get(name)
    return _num(r.value) if (r and r.value is not None) else None


# ── Validators ─────────────────────────────────────────────────────────────
# validator(value, fields) -> True if PLAUSIBLE. Must only return False when
# the value is categorically impossible — a false positive here destroys
# correct data (SHALqc.md P4: doubt degrades to VERIFY, never invents a FAIL).

def _valid_county(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().upper().rstrip(".")
    if v in _US_STATES:
        return False
    if _DIGITS_RE.match(v):
        return False
    return True


def _valid_state(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().upper().rstrip(".")
    if _DIGITS_RE.match(v):
        return False
    if len(v) == 2:
        return v in _US_STATES
    return v.replace(" ", "").isalpha()


def _valid_real_estate_taxes(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    if n is None:
        return False
    # The >=100 floor rejects PDF caption fragments ("1", "5"). But an EXACT 0 is a
    # real, common answer — tax-exempt and land-bank parcels state $0.00 (verified
    # ESMI-0049134: _TAX@_TotalTaxAmount="0", Detroit/Wayne County). Rejecting it made
    # the taxes check read "blank" on a report that answered the question.
    return n == 0 or n >= 100


def _valid_total_rooms(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 1 <= n <= 30 and n == int(n)


def _valid_bedrooms(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 0 <= n <= 20 and n == int(n)


def _valid_appraised_value(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 10_000 <= n <= 100_000_000


def _valid_supervisory_name(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip()
    if not v:
        return False
    if _ZIP_RE.match(v) or _DIGITS_RE.match(v):
        return False
    return any(c.isalpha() for c in v)


def _valid_appraiser_email(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _valid_mls_number(value: str, fields: Dict[str, ExtractedField]) -> bool:
    """F7 (445 Sparrow): the URAR data-source caption bleeds provider names into
    mls_number ("Corelogic, GeoData,"). A real MLS number is an identifier — it has
    a digit. A comma-separated list of alphabetic words with NO digit is caption/
    data-source bleed, not an MLS id → suppress."""
    v = value.strip()
    if not v:
        return False
    # an MLS NUMBER is an identifier — it has a digit. Verified across 10 RANDOM
    # orders: real ids ("57050211542", "#F10491575…", "#VALO2126558/LO") all carry
    # digits, while the bleed ("results of", "General Row", "increased", "correct",
    # "Corelogic, GeoData,") never does. No-digit → not an MLS number → suppress.
    return any(c.isdigit() for c in v)


# P2 / F2: a PERSON-name field ("2 PGS 102-104" bled in from the legal description)
# must be name-shaped. Detected by field-name SHAPE (person parties only — NOT
# company/lender/amc, which legitimately carry digits & suffixes), so a new party
# field is covered automatically. High precision: a real name is mostly letters.
_PERSON_NAME_FIELD_RX = re.compile(
    r"(?:^|_)(borrower|co_borrower|owner|seller|buyer|appraiser_name|"
    r"supervisory_appraiser_name|co_appraiser|contact_name|preparer)(?:_name)?$")


def _looks_like_person_name_field(fname: str) -> bool:
    return bool(_PERSON_NAME_FIELD_RX.search(fname))


def _name_shaped(value: str) -> bool:
    """A plausible person name: has an alphabetic token of length >=2 AND letters
    are the majority of its non-space characters. Rejects legal-description / page
    fragments ("2 PGS 102-104"), zips, and pure-digit bleed."""
    v = value.strip()
    if not v or _ZIP_RE.match(v) or _DIGITS_RE.match(v):
        return False
    non_space = [c for c in v if not c.isspace()]
    if not non_space:
        return False
    alpha = sum(1 for c in non_space if c.isalpha())
    has_word = any(len(t) >= 2 and t.isalpha() for t in re.split(r"[\s,]+", v))
    return has_word and alpha / len(non_space) >= 0.5


def _valid_contract_price(value: str, fields: Dict[str, ExtractedField]) -> bool:
    # A label-proximity read of a BLANK contract cell on a refinance bleeds in
    # adjacent glyphs ("$", "Is"). A real contract price is a dollar amount in
    # the thousands — a value with no multi-digit number cannot be one.
    n = _num(value)
    return n is not None and n >= 1000


def _valid_contract_date(value: str, fields: Dict[str, ExtractedField]) -> bool:
    from app.normalize import dates
    return dates.parse_date(value) is not None


def _valid_concessions_amount(value: str, fields: Dict[str, ExtractedField]) -> bool:
    # Concessions are a dollar amount ($0 is valid — an explicit "no
    # concessions"). Non-numeric prose ("gift or downpayment") is a misread.
    return _num(value) is not None


def _valid_gla(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    if n is None:
        return False
    hoa = fields.get("hoa_monthly_assessment")
    if hoa and hoa.value:
        hoa_n = _num(hoa.value)
        if hoa_n is not None and abs(n - hoa_n) < 1:
            return False
    return 100 <= n <= 25000


def _valid_site_area(value: str, fields: Dict[str, ExtractedField]) -> bool:
    v = value.strip().lower()
    m = re.match(r"[\d,]+(?:\.\d+)?", v)
    n = _num(m.group(0)) if m else None
    if n is None:
        return False
    if "ac" in v:
        unit = "ac"
    elif "sf" in v or "sq" in v:
        unit = "sf"
    else:
        sib = fields.get("site_area_unit")
        unit = (sib.value or "").lower() if sib else ""
    if unit.startswith("ac"):
        return 0.01 <= n <= _MAX_SITE_ACRES
    return 200 <= n <= 5_000_000


def _valid_comp_quality(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return value.strip().upper() in _UAD_QUALITY


def _valid_comp_condition(value: str, fields: Dict[str, ExtractedField]) -> bool:
    return value.strip().upper() in _UAD_CONDITION


def _valid_comp_age(value: str, fields: Dict[str, ExtractedField]) -> bool:
    n = _num(value)
    return n is not None and 0 <= n <= _MAX_STRUCTURE_AGE and n == int(n)


def _comp_net_adjustment_validator(prefix: str) -> Callable[[str, Dict[str, ExtractedField]], bool]:
    """Assert the grid's own arithmetic identity for one comp:
    signed_net_adjustment == adjusted_sale_price - sale_price."""
    def _validate(value: str, fields: Dict[str, ExtractedField]) -> bool:
        sale = _field_num(fields, f"{prefix}_sale_price")
        adj = _field_num(fields, f"{prefix}_adjusted_sale_price")
        mag = _num(value)
        if sale is None or adj is None or mag is None:
            return True
        has_minus = value.strip().startswith("-")
        pos = fields.get(f"{prefix}_net_adj_positive")
        pos_v = (pos.value or "").strip().upper() if pos else ""
        if not has_minus and pos_v == "" and mag != 0:
            return True
        signed = -abs(mag) if (has_minus or pos_v == "N") else abs(mag)
        return abs((adj - sale) - signed) <= _NET_ADJ_TOLERANCE
    return _validate


_FIELD_VALIDATORS: Dict[str, Callable[[str, Dict[str, ExtractedField]], bool]] = {
    "county":                     _valid_county,
    "state":                      _valid_state,
    "gla":                        _valid_gla,
    "real_estate_taxes":          _valid_real_estate_taxes,
    "total_rooms":                _valid_total_rooms,
    "bedrooms":                   _valid_bedrooms,
    "appraised_value":            _valid_appraised_value,
    "supervisory_appraiser_name": _valid_supervisory_name,
    "appraiser_email":            _valid_appraiser_email,
    "site_area":                  _valid_site_area,
    "contract_price":             _valid_contract_price,
    "contract_date":              _valid_contract_date,
    "concessions_amount":         _valid_concessions_amount,
    "mls_number":                 _valid_mls_number,
}

for _pfx in ["subject_grid"] + [f"comp_{_i}" for _i in range(1, _MAX_COMPS + 1)]:
    _FIELD_VALIDATORS[f"{_pfx}_quality_rating"] = _valid_comp_quality
    _FIELD_VALIDATORS[f"{_pfx}_condition_rating"] = _valid_comp_condition
    _FIELD_VALIDATORS[f"{_pfx}_age"] = _valid_comp_age
for _i in range(1, _MAX_COMPS + 1):
    _FIELD_VALIDATORS[f"comp_{_i}_net_adjustment"] = _comp_net_adjustment_validator(f"comp_{_i}")
del _pfx, _i


def _suppress(result: ExtractedField, reason: str) -> None:
    """Reject an implausible value: raw value stays visible (P2), `found`
    flips to False so downstream rules see MISSING and degrade to VERIFY/NA,
    never a confident wrong verdict."""
    if not result.raw_value:
        result.raw_value = result.value
    result.suppressed = True
    result.suppression_reason = f"rejected as implausible {result.canonical_name}: {reason} (was '{result.value}')"


# ── generic schema-driven gate ───────────────────────────────────────────────
#
# The per-field validators above are a hand-curated allowlist — they only cover
# the ~15 fields someone has already gotten burned by. A layout-anchored PDF
# reader (label-proximity, spatial-row, checkbox) can miss on ANY field: the
# printed form label itself ("of", "is", the option list next to an unchecked
# checkbox) is grammatically indistinguishable from a real value unless you
# know what KIND of value that field is allowed to hold. field_schema.yaml
# already carries that knowledge (data_type, allowed_values) for every field —
# this reuses it, generically, with zero per-field code, so a field added to
# the schema tomorrow is covered automatically (2026-07-13 dry-run causes #1).
_NUMERIC_TYPES = frozenset({"integer", "number", "currency", "percent", "float"})

# Function/stop words that can never be a real field value on their own — a
# form's printed label text ("Yes  or  No", "...analysis of...") is built from
# these; a genuine answer never is. Deliberately excludes yes/no/true/false —
# those ARE legitimate boolean answers.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "is", "are", "was", "were", "be", "been", "being",
    "or", "and", "nor", "but", "if", "then", "than", "so", "as", "at", "by",
    "for", "from", "in", "into", "on", "onto", "to", "with", "within", "this",
    "that", "these", "those", "it", "its", "not", "no.", "which", "who",
})


def _enum_plausible(fd, value: str) -> bool:
    v = value.strip().upper()
    allowed = {a.strip().upper() for a in fd.allowed_values}
    if v in allowed:
        return True
    # a value the reader concatenated across a checkbox's option list ("FWA
    # HWBB Radiant") is the JOIN of 2+ allowed tokens, never a single one of
    # them — reject; a genuine multi-select answer for a field that legitimately
    # allows one is still an exact/singular match handled above.
    tokens = {t.strip().rstrip(".,;:") for t in re.split(r"[\s/,]+", v) if t.strip()}
    return bool(tokens) and tokens <= allowed and len(tokens) == 1


# MISMO controlled-vocabulary tokens → the UAD-display string the schema enum
# uses. MISMO ships its own enumerations (_BuiltupRangeType="Over75Percent",
# _TypicalMarketingTimeDurationType="UnderThreeMonths", dwelling "Detached") that
# no amount of token/camelCase matching reconciles with the schema's display form
# ("Over 75%", "Under 3 mths", "Det.") — % vs Percent, word vs abbreviation. Keyed
# by squished-lowercase; the target is only returned if the FIELD actually allows
# it, so an entry can never inject a value into a field that doesn't list it. An
# unknown MISMO spelling simply falls through to suppression (today's behavior) —
# so this table is strictly additive and safe. Seeded from the 3 test orders
# (ESNV/ESTX/ESCA); extend as new AMCs surface new MISMO spellings.
_MISMO_ENUM_SYNONYMS: Dict[str, str] = {
    # _BuiltupRangeType
    "over75percent": "Over 75%",
    "2575percent": "25-75%", "twentyfivetoseventyfivepercent": "25-75%", "25to75percent": "25-75%",
    "under25percent": "Under 25%", "undertwentyfivepercent": "Under 25%",
    # _TypicalMarketingTimeDurationType
    "underthreemonths": "Under 3 mths", "under3months": "Under 3 mths",
    "threetosixmonths": "3-6 mths", "3to6months": "3-6 mths",
    "oversixmonths": "Over 6 mths", "over6months": "Over 6 mths",
    # dwelling type
    "detached": "Det.", "attached": "Att.",
    "semidetached": "S-Det./End Unit", "semidetachedendunit": "S-Det./End Unit",
    # units_count (MISMO carries the integer; schema enumerates the word). 2-4 cover
    # the FNM1025 multi-unit form, whose LivingUnitCount is 2/3/4.
    "1": "One", "2": "Two", "3": "Three", "4": "Four",
    # GSESaleType
    "armslengthsale": "Arms-Length", "nonarmslengthsale": "Non Arms-Length",
    "shortsale": "Short Sale", "reosale": "REO", "reo": "REO",
    # GSEZoningComplianceType — MISMO "Nonconforming" ≡ UAD "Legal Non-Conforming"
    # (ESMI-0049134: SITE._ZoningComplianceType="Nonconforming" was suppressed, so
    # EQ-30 saw the field as absent). "LegalNonconforming" spelling covered too.
    "nonconforming": "Legal Non-Conforming", "legalnonconforming": "Legal Non-Conforming",
    # GSEFoundationType — MISMO packages basement as a single "Basement" token; the UAD
    # form splits Full/Partial. Map to "Full Basement" (the dominant case, and either
    # value satisfies EQ-44's "a basement checkbox is marked"); has_full_basement carries
    # the finer distinction. Suppressed on ESMI-0049134 (FOUNDATION._Type="Basement").
    "basement": "Full Basement",
    # GSEHeatingType / GSECoolingType — MISMO spells the system out, the UAD form uses
    # the abbreviation. ESMI-0049134: HEATING@_Type="ForcedWarmAir" was suppressed, so
    # the HVAC check saw no heating on a gas forced-air house.
    "forcedwarmair": "FWA", "forcedairunit": "FWA", "forcedair": "FWA",
    "hotwaterbaseboard": "HWBB", "hotwater": "HWBB", "baseboard": "HWBB",
    "radiantheat": "Radiant",
}


def _enum_tokens(s: str) -> frozenset:
    """Uppercased word tokens, splitting on whitespace/slash/comma AND camelCase
    boundaries — so MISMO's 'FeeSimple'/'OwnerOccupied' tokenize the same way as
    the schema's 'Fee Simple'/'Owner Occupied'."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return frozenset(t.rstrip(".,;:") for t in re.split(r"[\s/,]+", spaced.upper()) if t.strip())


def _enum_squish(s: str) -> str:
    """All separators/case removed — 'FeeSimple' and 'Fee Simple' both → 'FEESIMPLE'."""
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _canonicalize_enum(fd, value: str) -> Optional[str]:
    """Map a raw enum value to the schema's allowed_value it UNAMBIGUOUSLY names,
    or None if it matches none / more than one.

    MISMO XML carries terse/camelCase enum tokens ("Purchase", "FeeSimple",
    "OwnerOccupied") while the schema allowed_values are verbose UAD phrases
    ("Purchase Transaction", "Fee Simple", "Owner"). Before 2026-07-13 the generic
    gate compared them VERBATIM and suppressed the terse-but-correct XML answer as
    implausible — so every conditional check keyed on that field saw an absent
    label and hedged to REVIEW. Canonicalizing (not merely accepting) rewrites the
    value to the enum the downstream judge/rules expect. Match order, each gated on
    EXACTLY ONE allowed value:
      1. squish-equal ('FeeSimple'=='Fee Simple');
      2. value's tokens ⊆ an allowed value's tokens ('Purchase' → 'Purchase Transaction');
      3. an allowed value's tokens ⊆ value's tokens ('OwnerOccupied' → 'Owner').
    'FWA HWBB Radiant' (a concatenated checkbox join) matches THREE allowed values
    under rule 3, so the single-match guard still correctly rejects it."""
    allowed = [a.strip() for a in fd.allowed_values]
    vsq = _enum_squish(value)
    if not vsq:
        return None
    exact = [a for a in allowed if _enum_squish(a) == vsq]
    if exact:
        return exact[0]
    vtok = _enum_tokens(value)
    if not vtok:
        return None
    sub = [a for a in allowed if vtok <= _enum_tokens(a)]           # value is terser
    if len(sub) == 1:
        return sub[0]
    sup = [a for a in allowed if _enum_tokens(a) <= vtok]           # value has extra word(s)
    if len(sup) == 1:
        return sup[0]
    # controlled-vocabulary synonym, returned only if the field lists it
    syn = _MISMO_ENUM_SYNONYMS.get(vsq.lower())
    if syn:
        ssq = _enum_squish(syn)
        for a in allowed:
            if _enum_squish(a) == ssq:
                return a
    return None


def _uad_numeric_prefix(value: str) -> Optional[str]:
    """The number from a UAD "<value>;<source>" cell — "7;Per Metrolist" → "7".

    Only fires when the text BEFORE the first ';' is purely a number: "7;Per
    Metrolist" and "120;MLS" qualify, "Fee Simple;Leasehold" does not, so an enum
    or free-text cell is never silently reduced to a digit it happens to contain.
    """
    head = str(value or "").split(";", 1)[0].strip()
    if not head:
        return None
    cleaned = head.replace(",", "").replace("$", "").replace("%", "").strip()
    if not cleaned:
        return None
    try:
        float(cleaned)
    except ValueError:
        return None
    return head


def _numeric_plausible(value: str) -> bool:
    return _num(value) is not None


_BOOLEAN_TOKENS = frozenset({"yes", "no", "y", "n", "true", "false", "1", "0"})


def _boolean_plausible(value: str) -> bool:
    return value.strip().lower().rstrip(".") in _BOOLEAN_TOKENS


# P2 / F7: a printed FORM CAPTION uses the "(s)" pluralization artifact — "Report
# data source(s) used, offering price(s), and date(s)" — that a real extracted value
# never carries. Detected by shape (no caption list to maintain), so a reader that
# grabbed the caption instead of the answer is suppressed → the field reads MISSING
# and the check degrades to VERIFY/CANNOT_EVALUATE, never a garbage-value REVIEW.
_CAPTION_ARTIFACT_RX = re.compile(r"[A-Za-z]\(s\)")


def _caption_artifact(value: str) -> bool:
    return bool(_CAPTION_ARTIFACT_RX.search(value))


# P2 / F8: a grid DESCRIPTIVE cell that concatenated a whole grid ROW (subject +
# comp columns) shows the same cell block repeated across columns —
# "CvPor,CvPat CvPor,CvPat Prch/Patio/Deck 0 Prch/Patio/Deck 0". A single real cell
# never repeats its own content. Detected by SHAPE (>=2 distinct content tokens each
# appearing >=2x, >=4 tokens total), so a legit multi-word value ("Concrete Slab
# Foundation") or a single repeated token ("Residential Residential") is never
# touched. The proper fix is column-bbox anchoring (see
# BBOX_PROVENANCE_REGISTRY_PLAN.md Phase 2); this is the safe interim guard.
_GRID_CELL_MAX_CHARS = 300   # a 7-comp "Porch/Patio/Deck" bleed ≈ 120 chars; prose is 1000s


# English function words that recur in ANY sentence. A repeated content token is
# evidence of a bled grid cell; a repeated "has"/"with"/"the" is evidence of prose.
_PROSE_FUNCTION_WORDS = frozenset("""
and are but for from has had have her his its not our out per she that the their
them then there these they this those was were what when which who will with you
your are can may off own too via able also been being both each into more most
some such than that upon very well were will would about after over under while
""".split())


def _repeated_grid_cell(value: str) -> bool:
    # A grid cell — or its worst-case bleed across all comps — is SHORT: a handful of
    # terse tokens. Free narrative (addendum_text, long comments) repeats common words
    # by nature and is NEVER a grid cell; a length ceiling far above any real multi-comp
    # bleed keeps prose from being nuked as row-bleed (ESMI-0049134: a 40 KB
    # AppraisalAddendumText was suppressed here, punting ~12 narrative checks to REVIEW).
    if len(value) > _GRID_CELL_MAX_CHARS:
        return False
    # split on / and , too, so NEAR-duplicate bleed fragments ("Porch/Patio
    # Porch/Deck Porch/Pat/Deck") repeat on their shared stems (Porch/Patio/Deck)
    # while a legit single cell ("Prch/Patio/Deck", "Concrete Slab Foundation")
    # still has no repeated token. Verified on ESNV + ESMI (445 Sparrow / H8354).
    tokens = [t for t in re.split(r"[\s/,]+", value.strip()) if len(t) >= 3]
    if len(tokens) < 3:
        return False
    # Count only CONTENT tokens. Grid bleed repeats the cell's own content
    # ("Porch/Patio Porch/Deck", "Fee Simple Fee Simple", "2Balcony 2Balcony");
    # ordinary English repeats FUNCTION words by nature, and counting those made
    # this guard fire on genuine prose that sits under the length ceiling.
    #
    # 2026-07-19, third instance of this defect (after neighborhood_boundaries and
    # conforms_to_neighborhood_comment): ESWA-0002168's additional_features —
    # "Home is mostly in original condtion with little evidence of remodeling or
    # updating over it's lifespan. Has detached garage. Has finished attic with two
    # bedrooms." — is 157 chars, so the ceiling did not protect it, and "Has"×2 +
    # "with"×2 satisfied the 2-distinct-repeats rule. EQ-49 then told the reviewer
    # "Additional Features field is blank" about a filled field. Filtering function
    # words fixes the CAUSE, so it no longer depends on the field being named
    # narrative-ishly.
    from collections import Counter
    counts = Counter(t for t in tokens if t.lower() not in _PROSE_FUNCTION_WORDS)
    if not counts:
        return False
    # a real cell never repeats the SAME token 3+ times ("2Balcony 2Balcony
    # 2Balcony" = one value bled across comps), nor repeats 2+ DISTINCT tokens
    # ("Porch/Patio Porch/Deck Porch/Pat/Deck"). Either shape → row bleed.
    if any(c >= 3 for c in counts.values()):
        return True
    return len(tokens) >= 4 and sum(1 for c in counts.values() if c >= 2) >= 2


# P2 (445 Sparrow, comps 2-6): a field can carry its OWN printed caption as the
# value when the appraiser left the cell blank and the software emitted the label
# ("Prch/Patio/Deck" for porch_patio_deck). Detected by matching the value against
# the field's CANONICAL NAME only (never its value-like synonyms such as "Balcony"),
# devoweled so an abbreviation ("Prch"≡"Porch") still matches — so a real value like
# "2Balcony" (nowhere near "porch patio deck") is untouched. Source-agnostic: works
# whether the caption came from the XML or the PDF grid.
def _devowel(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[aeiou]", "", (s or "").lower()))


def _caption_echo_of_field(canonical_name: str, value: str) -> bool:
    base = re.sub(r"^(?:comp_\d+|subject_grid|prior_comp_\d+)_", "", canonical_name)
    cap = _devowel(base.replace("_", " "))
    val = _devowel(value)
    return len(cap) >= 4 and val == cap


def _string_plausible(value: str) -> bool:
    """Reject a value whose every token is a stopword ("of", "is", "or", a
    label fragment with no content word), or that carries a form-caption "(s)"
    artifact — never true for a real answer."""
    if _caption_artifact(value):
        return False
    tokens = [t for t in re.split(r"\s+", value.strip().lower()) if t]
    if not tokens:
        return False
    return not all(t.rstrip(".,;:()") in _STOPWORDS for t in tokens)


def _generic_schema_gate(merged: Dict[str, ExtractedField]) -> int:
    from app.extraction.schema import NARRATIVE_NAME_TOKENS, schema_loader

    suppressed = 0
    for fname, ef in list(merged.items()):
        if not ef.found:
            continue
        fd = schema_loader.get_field(fname)
        value = str(ef.value)
        if fd is None:
            # comp_N_/subject-grid descriptive fields aren't registered by exact name
            # (the schema keys the subject template only), so get_field misses them —
            # yet they still carry values (e.g. XML comp_N_porch_patio_deck). Apply the
            # source-agnostic, value-shape-only guards (caption echo of the field's own
            # label; grid cell bleed) — both proven no-false-positive on the golden set.
            # The grid-bleed guard is for SHORT structured cells; multi-clause prose
            # is what a narrative field is supposed to contain, so the guard reads a
            # good comment as a bled row. The schematized branch already exempts
            # narrative fields via `fd._is_narrative` — an UNSCHEMATIZED field
            # deserves the same exemption, since the exemption follows the field's
            # nature, not whether it happens to be registered in the schema.
            #
            # 2026-07-18: `conforms_to_neighborhood_comment` is not in the schema, so
            # it fell here and was suppressed on 4 of 8 orders — every one read from
            # the AUTHORITATIVE XML at 0.97 and every one real prose ("The subject
            # property conforms well with the market area. No adverse conditions were
            # noted."). Same defect as neighborhood_boundaries, one branch over.
            # Caption-echo still applies: a narrative field echoing its own label IS
            # a blank-cell placeholder.
            narrative_name = any(k in fname.lower() for k in NARRATIVE_NAME_TOKENS)
            if _caption_echo_of_field(fname, value) or (
                    not narrative_name and _repeated_grid_cell(value)):
                logger.info("Plausibility (unschematized) rejected %s='%s'", fname, value)
                _suppress(ef, "caption-echo/grid-bleed")
                suppressed += 1
            continue
        ok = True
        reason = ""
        if fd.allowed_values:
            # canonicalize a terse-but-valid enum ("Purchase" → "Purchase
            # Transaction") to the schema value before judging plausibility, so a
            # correct XML answer is kept (rewritten), not suppressed.
            canon = _canonicalize_enum(fd, value)
            if canon is not None:
                if canon != ef.value:
                    logger.info("Plausibility: canonicalized %s='%s' → '%s'", fname, value, canon)
                    ef.value = canon
                ok = True
            else:
                ok = False
            reason = f"not one of allowed_values={fd.allowed_values}"
        elif fd.data_type in _NUMERIC_TYPES:
            # UAD writes "<value>;<source>" in a single cell ("7;Per Metrolist",
            # "120;MLS"). Suppressing the whole thing as non-numeric threw away a
            # number we had read correctly — EQ-13 "Subject Listed/Sold within 12
            # Months" hedged on 7 of 7 orders because days_on_market="7;Per
            # Metrolist" was discarded rather than parsed to 7. Rewrite to the
            # numeric part, exactly as the enum branch canonicalizes rather than
            # suppresses; the provenance is preserved in raw_value.
            numeric = _uad_numeric_prefix(value)
            if numeric is not None and not _numeric_plausible(value):
                logger.info("Plausibility: parsed UAD value;source %s='%s' → '%s'",
                            fname, value, numeric)
                ef.value = numeric
                value = numeric
            ok = _numeric_plausible(value)
            reason = f"not numeric (data_type={fd.data_type})"
        elif fd.data_type == "boolean":
            ok = _boolean_plausible(value)
            reason = "not a recognized yes/no/true/false token"
        elif fd.data_type == "string" and not fd._is_narrative:
            if _caption_echo_of_field(fname, value):
                ok = False
                reason = "value is the field's own caption/label (blank cell placeholder)"
            elif _looks_like_person_name_field(fname):
                ok = _name_shaped(value)
                reason = "not name-shaped (legal-desc/page/digit fragment in a person-name field)"
            elif _repeated_grid_cell(value):
                # a value that repeats >=2 distinct blocks is a grid ROW that bled
                # subject+comp cells into one field — never a single real cell.
                ok = False
                reason = "grid cell bleed (row/multi-cell concatenation)"
            else:
                ok = _string_plausible(value)
                reason = "value is only stopwords/label-fragment text"
        if not ok:
            logger.info("Plausibility (generic) rejected %s='%s': %s", fname, value, reason)
            _suppress(ef, reason)
            suppressed += 1
    return suppressed


def validate_fields(merged: Dict[str, ExtractedField]) -> int:
    """Run every field validator over the merged fields in place.

    Returns the number of values suppressed (for report.degradations[] / P11).
    """
    suppressed = 0
    for fname, validator in _FIELD_VALIDATORS.items():
        ef = merged.get(fname)
        if ef is None or not ef.found:
            continue
        try:
            ok = validator(str(ef.value), merged)
        except Exception as exc:  # a buggy validator never breaks extraction (P6)
            logger.debug("Validator for %s raised %s — leaving value untouched", fname, exc)
            continue
        if not ok:
            logger.info("Plausibility rejected %s='%s'", fname, ef.value)
            _suppress(ef, "failed plausibility check")
            suppressed += 1

    try:
        suppressed += _generic_schema_gate(merged)
    except Exception as exc:  # a buggy gate never breaks extraction (P6)
        logger.debug("Generic schema gate raised %s — leaving values untouched", exc)

    return suppressed
