"""
Engagement-letter (order form) extractor — label-anchored.

Engagement letters are clean digital text but a FREE-FORM layout, not a URAR
form, so the URAR-tuned spatial extractor mis-reads them (it grabbed the AMC's
Michigan zip as the property zip, merged lender name+address, etc.). This
extractor anchors on the order-form's own labels and parses the property /
client blocks directly, which is what the cross-document QC rules depend on.

Handles the two formats seen in the corpus:
  Format A (Equity Solutions): "Label:" on one line, value on the NEXT line(s);
            property block is "Map Link\\n<street>, <city>, <state>, <zip>\\n<county> County".
  Format B (ESFL/ASAP "Order Information"): "Label: value" on the SAME line.

Output: ExtractionResultSet of canonical engagement fields, high confidence
(label-anchored), method "engagement_label".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

from app.core.result import ExtractionResult, ExtractionResultSet

_CONF = 0.92  # label-anchored on clean digital text

_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
_ABBRS = set(_STATE_ABBR.values())

# canonical field -> ordered list of label variants (lowercased, no trailing colon).
# Variants are sorted longest-first in _LABEL_LOOKUP so the most specific label
# wins when a line could match multiple synonyms.
#
# Common AMC order-form label variations observed across Equity Solutions USA,
# ASAP Appraisals, and similar AMC templates are included here. Add new variants
# as new AMC templates are onboarded — never delete existing ones.
_LABELS: Dict[str, List[str]] = {
    "_property_block": [
        "property address", "subject property address", "subject property",
        "property location", "property", "address", "subject address",
    ],
    "county": ["property county", "county", "subject county"],
    "borrower_name": [
        "borrower name(s)", "borrower name", "borrower(s)", "borrower",
        "applicant name", "applicant(s)", "applicant",
        "client name", "mortgagor",
    ],
    "co_borrower_name": [
        "co-borrower name(s)", "co-borrower name", "co-borrower(s)",
        "co-borrower", "coborrower name", "coborrower",
        "co applicant", "co-applicant",
    ],
    "lender_name": [
        "lender on report", "lender/client", "lender / client",
        "client", "lender", "client name",
        "intended user", "mortgagee",
    ],
    "lender_address": ["lender address", "client address", "lender/client address"],
    "form_type": [
        "form", "product", "report type", "order type",
        "appraisal type", "form type", "product type",
    ],
    "loan_type": [
        "loan type", "loan product", "financing type", "mortgage type",
    ],
    "assignment_type": [
        "intended use", "transaction type", "loan purpose",
        "purpose of appraisal", "purpose", "order type",
    ],
    "file_id": [
        "file id", "order number", "order #", "file #",
        "reference #", "reference number", "order no",
        "order id", "amc order #", "amc order number",
        "eqs order #", "eqs order number",
    ],
    "loan_number": [
        "loan #", "loan number", "loan no", "loan id",
        "lender loan #", "lender loan number",
    ],
    "fha_case_number": ["fha case number", "fha case #"],
    "legal_description": ["legal description"],
    "appraiser_name": [
        "appraiser", "vendor", "appraiser name",
        "assigned appraiser", "appraisal company",
    ],
    "amc_reg_number": [
        "amc reg. number", "amc reg number", "amc registration",
        "amc reg #", "amc license",
    ],
}

_LABEL_LOOKUP = sorted(
    {lbl for variants in _LABELS.values() for lbl in variants},
    key=len, reverse=True,
)


def _label_of(line: str) -> Optional[str]:
    """Return the lowercased 'Label' if the line begins 'Label:' (any label)."""
    m = re.match(r"\s*([A-Za-z][A-Za-z /#'\.\-\(\)]{1,34}?)\s*:", line)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1).strip().lower())


# Parties whose address on the order form is NOT the subject property — the
# AMC/vendor, the appraiser, the lender/client, the borrower. A generic
# "Address:"/"Property:" label that belongs to one of these must never fill the
# subject property block. AMC forms routinely wrap a long label across two lines
# ("Vendor Mailing" \n "Address:"), so the disqualifying word sits on the line
# ABOVE the "Address:" label — that is why we look back one line.
_NON_SUBJECT_OWNER_RE = re.compile(
    r"\b(vendor|appraiser|client|lender|mortgagee|company|mailing|"
    r"borrower|applicant|contact|amc|escrow|title|billing|remit)\b",
    re.I,
)


def _prev_nonblank(lines: List[str], idx: int) -> str:
    """The nearest non-blank line above idx (for detecting wrapped labels)."""
    j = idx - 1
    while j >= 0:
        if lines[j].strip():
            return lines[j].strip()
        j -= 1
    return ""


def _is_non_subject_address(lines: List[str], idx: int) -> bool:
    """True when the 'Address:'/'Property:' label at idx belongs to a non-subject
    party (vendor/client/appraiser/…) rather than the subject property — either
    because that party word is on the label line itself or on the wrapped line
    directly above it (e.g. 'Vendor Mailing' \\n 'Address:')."""
    here = lines[idx]
    if _NON_SUBJECT_OWNER_RE.search(here):
        return True
    prev = _prev_nonblank(lines, idx)
    # Only a bare continuation prefix (no colon of its own) counts as part of this
    # label; a preceding 'Something: value' line is the previous field, not a prefix.
    return bool(prev) and ":" not in prev and _NON_SUBJECT_OWNER_RE.search(prev) is not None


def _line_is_label(line: str) -> Optional[str]:
    """Return the label only if it is one we extract (used for canonical mapping)."""
    lbl = _label_of(line)
    return lbl if (lbl and lbl in set(_LABEL_LOOKUP)) else None


def _is_boundary(line: str) -> bool:
    """A following line ends a value block if it itself looks like 'AnyLabel:'."""
    return _label_of(line) is not None


def _collect_block(lines: List[str], start: int) -> Tuple[List[str], int]:
    """Value after a 'Label:': same-line value, else following non-label lines.
    Returns the value as a list of source lines (so callers can split name/address)."""
    line = lines[start]
    after = line.split(":", 1)[1].strip() if ":" in line else ""
    if after:
        return [after], start
    out: List[str] = []
    j = start + 1
    while j < len(lines):
        nxt = lines[j].strip()
        if not nxt:
            if out:
                break
            j += 1
            continue
        if _is_boundary(nxt):          # stop at ANY 'Label:' line, known or not
            break
        out.append(nxt)
        j += 1
        if len(out) >= 3:
            break
    return out, j - 1


# Secondary-address unit components ("Ste 212", "Suite 100", "Unit 4", "#212",
# "Apt 3B", "Bldg 2", "Floor 3"). In a comma-separated mailing address these sit
# between the street and the city — they belong to the STREET, never the city.
_UNIT_RE = re.compile(
    r"^(?:#\s*\w+"
    r"|(?:ste|suite|unit|apt|apartment|bldg|building|floor|fl|rm|room|dept|department)\b"
    r"\.?\s*#?\s*\w*)$",
    re.I,
)


def _looks_like_unit(token: str) -> bool:
    """True when a token is a secondary-address unit (suite/apt/floor/#…), not a city."""
    t = (token or "").strip()
    return bool(t) and _UNIT_RE.match(t) is not None


def parse_address(raw: str) -> Dict[str, str]:
    """Parse '<street>, <city>, <state>, <zip>' or '<street>, <city> ST zip'.

    Secondary-unit components (e.g. "Ste 212") are folded into the street, never
    read as the city — a mis-read suite is exactly what caused S-1 to compare the
    subject city against a suite number ("Ste 212") and false-FAIL.
    """
    out: Dict[str, str] = {}
    s = re.sub(r"\bMap Link\b", "", raw, flags=re.I)
    s = re.sub(r"\(.*?\)", "", s)                       # drop "( Additional Resources )"
    s = re.sub(r"\s+", " ", s).strip().strip(",")
    if not s:
        return out
    zips = re.findall(r"\b(\d{5})(?:-\d{4})?\b", s)
    if zips:
        out["zip_code"] = zips[-1]                      # LAST 5-digit group = real zip
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 4:
        # Format A: street[, unit], city, state[, zip]. Skip past any secondary-unit
        # component so the city is read from the right position, not the suite.
        street_bits = [parts[0]]
        idx = 1
        while idx < len(parts) - 1 and _looks_like_unit(parts[idx]):
            street_bits.append(parts[idx])
            idx += 1
        out["property_address"] = ", ".join(street_bits)
        if idx < len(parts):
            out["city"] = parts[idx]
        st_tokens = parts[idx + 1].split() if idx + 1 < len(parts) else []
        st_raw = st_tokens[0] if st_tokens else ""
        st = st_raw.lower()
        out["state"] = _STATE_ABBR.get(st, st_raw.upper() if st_raw.upper() in _ABBRS else "")
    else:
        # Tail "... city ST zip" / "... city Statename zip"
        m = re.search(r"(.+?)\s+([A-Za-z]{2,})\s+\d{5}", s)
        if m:
            stok = m.group(2).lower()
            out["state"] = (_STATE_ABBR.get(stok)
                            or (m.group(2).upper() if m.group(2).upper() in _ABBRS else ""))
            head = m.group(1).strip().strip(",").strip()
            if "," in head:
                # "street, city" → split on last comma
                street, city = head.rsplit(",", 1)
                out["property_address"] = street.strip()
                if city.strip():
                    out["city"] = city.strip()
            else:
                # no comma — can't reliably split street/city; keep combined,
                # leave city unset so a wrong city never causes a false FAIL.
                out["property_address"] = head
        else:
            out["property_address"] = parts[0]
    if out.get("state") and out["state"] not in _ABBRS:
        out["state"] = ""
    # Final guard: a real U.S. city name has no digits and is not a unit token. If we
    # somehow still landed on a suite/number, drop it — leaving city unset (VERIFY) is
    # always safer than a wrong city driving a false cross-doc FAIL (P-6).
    if out.get("city") and (_looks_like_unit(out["city"]) or any(ch.isdigit() for ch in out["city"])):
        out.pop("city", None)
    return {k: v for k, v in out.items() if v}


def _loan_type_from(*texts: str) -> Optional[str]:
    blob = " ".join(t for t in texts if t).lower()
    for key in ("fha", "usda", "va", "conventional"):
        if re.search(rf"\b{key}\b", blob):
            return key.upper() if key != "conventional" else "Conventional"
    return None


def extract_engagement_fields(pdf_path) -> Dict[str, str]:
    """Return {canonical_field: value} extracted from the engagement letter text."""
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    text = "\n".join(doc[i].get_text("text") for i in range(min(2, len(doc))))
    doc.close()
    lines = text.splitlines()

    found: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        lbl = _line_is_label(lines[i])
        if not lbl:
            i += 1
            continue
        # which canonical field does this label map to?
        canon = next((c for c, variants in _LABELS.items() if lbl in variants), None)
        if canon is None:
            i += 1
            continue
        # Guard: a generic address/property label that actually belongs to the
        # vendor/client/appraiser block must not fill the SUBJECT property block.
        # (e.g. "Vendor Mailing" \n "Address: 12950 Race Track Rd, Ste 212, Tampa"
        #  was leaking "Tampa" into the subject city and false-failing S-1.)
        if canon == "_property_block" and _is_non_subject_address(lines, i):
            i += 1
            continue
        block, end = _collect_block(lines, i)
        value = " ".join(block).strip()
        if value and (canon not in found or canon == "_property_block"):
            if canon == "_property_block":
                # county can be a bare trailing "X County" line (Format A) — only
                # when it is NOT itself a 'Label:' line (Format B uses Property County:).
                if end + 1 < len(lines):
                    nxt = lines[end + 1].strip()
                    if ":" not in nxt:
                        cm = re.match(r"([A-Za-z][A-Za-z .'\-]+?)\s+County\b", nxt)
                        if cm and "county" not in found:
                            found["county"] = cm.group(1).strip()
                if "county" not in found:
                    cm = re.search(r"\b([A-Za-z][A-Za-z .'\-]+?)\s+County\b", value)
                    if cm:
                        found["county"] = cm.group(1).strip()
                addr = parse_address(value)
                found.update({k: v for k, v in addr.items() if k not in found})
            elif canon == "lender_name":
                # Format A client block: name, then address. Company names routinely
                # WRAP across lines ("...DBA Lendz" / "Financial" on the next line) —
                # treating every line after the first as the address truncated the
                # name and produced a garbage "corrected" address (e.g. the single
                # word "Financial") for S-10a/S-10b. The address is identified by
                # its first line looking like a street start (leads with a number);
                # every line before that is part of the (possibly wrapped) name.
                addr_start = next(
                    (k for k, ln in enumerate(block) if k > 0 and re.match(r"^\d", ln)),
                    len(block),
                )
                if "lender_name" not in found:
                    found["lender_name"] = " ".join(block[:addr_start]).strip()
                if addr_start < len(block) and "lender_address" not in found:
                    found["lender_address"] = " ".join(block[addr_start:]).strip()
            elif canon not in found:
                found[canon] = value
        i = end + 1

    # derive loan_type if not explicit
    if "loan_type" not in found:
        lt = _loan_type_from(found.get("form_type", ""))
        if lt:
            found["loan_type"] = lt
    # normalize assignment_type
    if found.get("assignment_type"):
        a = found["assignment_type"].lower()
        found["assignment_type"] = ("Purchase" if "purchase" in a else
                                    "Refinance" if "refi" in a else found["assignment_type"])
    return found


def extract_engagement(pdf_path, document_type: str = "engagement_letter") -> ExtractionResultSet:
    """Build an ExtractionResultSet of engagement fields (for QCContext)."""
    pdf_path = Path(pdf_path)
    fields = extract_engagement_fields(pdf_path)
    rs = ExtractionResultSet(
        document_path=str(pdf_path), document_type=document_type,
        ocr_method="engagement_label",
    )
    try:
        d = fitz.open(str(pdf_path)); rs.total_pages = len(d); d.close()
    except Exception:
        pass
    for name, value in fields.items():
        rs.add(ExtractionResult(
            canonical_name=name, document_type=document_type, value=str(value),
            raw_source_text=str(value), extraction_method="engagement_label",
            confidence=_CONF, source_page=1,
            normalization_applied=["engagement_label"],
        ))
    rs.finalize()
    return rs
