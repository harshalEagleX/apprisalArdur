"""
extractor.engagement (eng-1.0.0) — engagement-letter (order form) extractor.

SHALqc.md §3.2 step 6: label regex over the order-form text is explicitly
sanctioned here — "Regex is fine HERE — it's locating labeled values, not
judging rules" (SHALqc.md P6/§5 T1 distinction). Engagement letters are clean
digital text but free-form layout (not a URAR form), so this extractor anchors
on the order form's own labels rather than reusing the URAR-tuned spatial
reader. Confidence fixed at 0.92.

Ported from ocr-service/app/extraction/engagement_extractor.py, re-pointed at
the ExtractedField contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.extraction.result import ExtractedField, ExtractedFieldSet, Source

__version__ = "eng-1.0.0"

_CONF = 0.92

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

# SHALqc-CORE §12: per-AMC label variance moves into the profile's
# `engagement_hints`, merged over this `_base` default set. Kept here as the
# default set until the profile layer (SHALqc.md §6, out of scope this build)
# is wired to override it.
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

_LABEL_LOOKUP = sorted({lbl for variants in _LABELS.values() for lbl in variants}, key=len, reverse=True)
_LABEL_LOOKUP_SET = set(_LABEL_LOOKUP)

_NON_SUBJECT_OWNER_RE = re.compile(
    r"\b(vendor|appraiser|client|lender|mortgagee|company|mailing|"
    r"borrower|applicant|contact|amc|escrow|title|billing|remit)\b",
    re.I,
)
_UNIT_RE = re.compile(
    r"^(?:#\s*\w+"
    r"|(?:ste|suite|unit|apt|apartment|bldg|building|floor|fl|rm|room|dept|department)\b"
    r"\.?\s*#?\s*\w*)$",
    re.I,
)


def _label_of(line: str) -> Optional[str]:
    m = re.match(r"\s*([A-Za-z][A-Za-z /#'\.\-\(\)]{1,34}?)\s*:", line)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1).strip().lower())


def _prev_nonblank(lines: List[str], idx: int) -> str:
    j = idx - 1
    while j >= 0:
        if lines[j].strip():
            return lines[j].strip()
        j -= 1
    return ""


def _is_non_subject_address(lines: List[str], idx: int) -> bool:
    here = lines[idx]
    if _NON_SUBJECT_OWNER_RE.search(here):
        return True
    prev = _prev_nonblank(lines, idx)
    return bool(prev) and ":" not in prev and _NON_SUBJECT_OWNER_RE.search(prev) is not None


def _line_is_label(line: str, lookup_set: Optional[set] = None) -> Optional[str]:
    lbl = _label_of(line)
    lookup = lookup_set if lookup_set is not None else _LABEL_LOOKUP_SET
    return lbl if (lbl and lbl in lookup) else None


def _merge_hints(hints: Optional[Dict[str, List[str]]]):
    """SHALqc-CORE §12: merge an AMC's `engagement_hints` (canonical → extra
    label variants) OVER the _base label set. Returns (labels, lookup_set).
    A new AMC's differently-labelled order form is a profile edit, not code."""
    if not hints:
        return _LABELS, _LABEL_LOOKUP_SET
    labels = {k: list(v) for k, v in _LABELS.items()}
    for canon, extra in hints.items():
        variants = [str(x).strip().lower() for x in (extra or []) if str(x).strip()]
        labels.setdefault(canon, [])
        for v in variants:
            if v not in labels[canon]:
                labels[canon].append(v)
    lookup = {lbl for vs in labels.values() for lbl in vs}
    return labels, lookup


def _is_boundary(line: str) -> bool:
    return _label_of(line) is not None


def _collect_block(lines: List[str], start: int) -> Tuple[List[str], int]:
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
        if _is_boundary(nxt):
            break
        out.append(nxt)
        j += 1
        if len(out) >= 3:
            break
    return out, j - 1


def _looks_like_unit(token: str) -> bool:
    t = (token or "").strip()
    return bool(t) and _UNIT_RE.match(t) is not None


def _split_street_city(head: str) -> Dict[str, str]:
    """Split a comma-less "street … city" blob into street + city using the
    USPS street-suffix as the boundary (the user's option 1: the suffix is the
    natural delimiter a comma-less address lacks).

    "7243 Foxtail Mdw Ct Humble" → street "7243 Foxtail Mdw Ct", city "Humble"
    "6901 Camp Fire Rd Las Vegas" → street "6901 Camp Fire Rd", city "Las Vegas"

    Returns {"street": ...} (always) and {"city": ...} ONLY when a suffix was
    found and something follows it — otherwise city is left UNSET so S-1b routes
    to VERIFY rather than the parser guessing (probabilistic parse must never
    silently "fix" and hide a genuine order-vs-report mismatch)."""
    tokens = head.split()
    if not tokens:
        return {"street": head}
    try:
        from app.normalize.normalizer import normalizer
        suffixes = normalizer.street_suffixes()
    except Exception:
        suffixes = {"st", "street", "ave", "avenue", "rd", "road", "dr", "drive",
                    "ct", "court", "ln", "lane", "blvd", "boulevard", "cir", "circle",
                    "pl", "place", "way", "ter", "terrace", "trl", "trail"}
    # last token that is a street suffix marks the street/city boundary
    last_suffix = -1
    for i, tok in enumerate(tokens):
        if tok.lower().strip(".") in suffixes:
            last_suffix = i
    if last_suffix < 0 or last_suffix >= len(tokens) - 1:
        return {"street": head}          # no suffix, or nothing after it → city unknown (VERIFY)
    # skip any secondary-unit tokens right after the suffix (they are street)
    j = last_suffix + 1
    while j < len(tokens) - 0 and _looks_like_unit(tokens[j]):
        j += 1
    street = " ".join(tokens[:j])
    city = " ".join(tokens[j:]).strip()
    out = {"street": street}
    # a real city has no digits and isn't a unit token
    if city and not any(c.isdigit() for c in city) and not _looks_like_unit(city):
        out["city"] = city
    return out


def _usaddress_parse(s: str) -> Dict[str, str]:
    """Parse a US address blob with the usaddress CRF tagger (option 3): it
    labels AddressNumber/StreetName/…/PlaceName(city)/StateName/ZipCode even
    with no delimiters ('731 Monticello Ave Pontiac MI 48340'). Returns only
    the components we trust; the caller still routes to VERIFY on any cross-doc
    mismatch — the tagger is probabilistic, so it never silently 'fixes' an
    address and hides a genuine order-vs-report discrepancy (P4)."""
    try:
        import usaddress
        tagged, kind = usaddress.tag(s)
    except Exception:
        return {}
    if kind != "Street Address":
        return {}
    out: Dict[str, str] = {}
    street_parts = [tagged.get(k) for k in (
        "AddressNumber", "StreetNamePreDirectional", "StreetName",
        "StreetNamePostType", "StreetNamePostDirectional",
        "OccupancyType", "OccupancyIdentifier") if tagged.get(k)]
    if street_parts:
        out["property_address"] = " ".join(street_parts)
    city = tagged.get("PlaceName")
    if city and not any(ch.isdigit() for ch in city):
        out["city"] = city.strip()
    st = (tagged.get("StateName") or "").strip()
    if st:
        out["state"] = _STATE_ABBR.get(st.lower(), st.upper() if st.upper() in _ABBRS else "")
    zc = tagged.get("ZipCode")
    if zc:
        m = re.search(r"\d{5}", zc)
        if m:
            out["zip_code"] = m.group(0)
    return {k: v for k, v in out.items() if v}


def parse_address(raw: str) -> Dict[str, str]:
    """Parse '<street>, <city>, <state>, <zip>' or '<street>, <city> ST zip'."""
    out: Dict[str, str] = {}
    s = re.sub(r"\bMap Link\b", "", raw, flags=re.I)
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\s+", " ", s).strip().strip(",")
    if not s:
        return out

    # usaddress CRF tagger first — best at comma-less blobs. Only accept it when
    # it yields BOTH a city and a state (a partial tag is not trustworthy); the
    # regex/suffix logic below stays as the deterministic fallback.
    ua = _usaddress_parse(s)
    if ua.get("city") and ua.get("state"):
        return ua
    zips = re.findall(r"\b(\d{5})(?:-\d{4})?\b", s)
    if zips:
        out["zip_code"] = zips[-1]
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 4:
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
        m = re.search(r"(.+?)\s+([A-Za-z]{2,})\s+\d{5}", s)
        if m:
            stok = m.group(2).lower()
            out["state"] = (_STATE_ABBR.get(stok)
                            or (m.group(2).upper() if m.group(2).upper() in _ABBRS else ""))
            head = m.group(1).strip().strip(",").strip()
            if "," in head:
                street, city = head.rsplit(",", 1)
                out["property_address"] = street.strip()
                if city.strip():
                    out["city"] = city.strip()
            else:
                # no comma — split street/city at the USPS street suffix. City is
                # only set when the boundary is unambiguous; otherwise it stays
                # unset (S-1b → VERIFY), never a guessed value (P4).
                split = _split_street_city(head)
                out["property_address"] = split.get("street", head)
                if split.get("city"):
                    out["city"] = split["city"]
        else:
            out["property_address"] = parts[0]
    if out.get("state") and out["state"] not in _ABBRS:
        out["state"] = ""
    if out.get("city") and (_looks_like_unit(out["city"]) or any(ch.isdigit() for ch in out["city"])):
        out.pop("city", None)
    return {k: v for k, v in out.items() if v}


def _loan_type_from(*texts: str) -> Optional[str]:
    blob = " ".join(t for t in texts if t).lower()
    for key in ("fha", "usda", "va", "conventional"):
        if re.search(rf"\b{key}\b", blob):
            return key.upper() if key != "conventional" else "Conventional"
    return None


def extract_engagement_fields(pdf_path, hints: Optional[Dict[str, List[str]]] = None) -> Dict[str, str]:
    """Return {canonical_field: value} extracted from the engagement letter text.
    `hints` = the active AMC profile's engagement_hints (SHALqc-CORE §12)."""
    import fitz

    labels, lookup_set = _merge_hints(hints)
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    text = "\n".join(doc[i].get_text("text") for i in range(min(2, len(doc))))
    doc.close()
    lines = text.splitlines()

    found: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        lbl = _line_is_label(lines[i], lookup_set)
        if not lbl:
            i += 1
            continue
        canon = next((c for c, variants in labels.items() if lbl in variants), None)
        if canon is None:
            i += 1
            continue
        if canon == "_property_block" and _is_non_subject_address(lines, i):
            i += 1
            continue
        block, end = _collect_block(lines, i)
        value = " ".join(block).strip()
        if value and (canon not in found or canon in ("_property_block", "form_type")):
            if canon == "_property_block":
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
                addr_start = next(
                    (k for k, ln in enumerate(block) if k > 0 and re.match(r"^\d", ln)),
                    len(block),
                )
                if "lender_name" not in found:
                    found["lender_name"] = " ".join(block[:addr_start]).strip()
                if addr_start < len(block) and "lender_address" not in found:
                    found["lender_address"] = " ".join(block[addr_start:]).strip()
            elif canon == "form_type":
                # prefer a value that carries a form NUMBER ("1004 FHA") over a
                # generic one ("Residential Appraisal") so the form family is
                # comparable to the report's XML form_type (ORD-FORM-MATCH).
                has_num = bool(re.search(r"\b(1004|1073|1025|1007|2055|216)\b", value))
                cur = found.get("form_type", "")
                cur_has_num = bool(re.search(r"\b(1004|1073|1025|1007|2055|216)\b", cur))
                if "form_type" not in found or (has_num and not cur_has_num):
                    found["form_type"] = value
            elif canon not in found:
                found[canon] = value
        i = end + 1

    if "loan_type" not in found:
        lt = _loan_type_from(found.get("form_type", ""))
        if lt:
            found["loan_type"] = lt
    if found.get("assignment_type"):
        a = found["assignment_type"].lower()
        found["assignment_type"] = ("Purchase" if "purchase" in a else
                                    "Refinance" if "refi" in a else found["assignment_type"])
    return found


def extract_engagement(pdf_path, hints: Optional[Dict[str, List[str]]] = None) -> ExtractedFieldSet:
    """Build an ExtractedFieldSet of engagement-letter fields.

    Canonical names are NOT namespaced (e.g. "property_address", not
    "engagement.property_address") — SHALqc.md §3.2 merges engagement values
    into the same field bag as XML/PDF, with XML winning ties (step 9) and a
    materially-disagreeing engagement value retained as a conflict witness.
    Splitting engagement into a separately-namespaced packet is a rules-layer
    concern (SHALqc-CORE §4.1 fact packets), out of scope for this build.
    """
    fields = extract_engagement_fields(pdf_path, hints=hints)
    fs = ExtractedFieldSet()
    for name, value in fields.items():
        fs.add(ExtractedField(
            canonical_name=name,
            value=str(value),
            raw_value=str(value),
            source=Source.ENGAGEMENT,
            confidence=_CONF,
            page=1,
        ))
    return fs
