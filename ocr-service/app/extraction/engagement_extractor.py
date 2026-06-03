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

# canonical field -> ordered list of label variants (lowercased, no trailing colon)
_LABELS: Dict[str, List[str]] = {
    "_property_block": ["property address", "property", "subject property", "address"],
    "county": ["property county", "county"],
    "borrower_name": ["borrower name", "borrower", "borrower(s)", "applicant"],
    "co_borrower_name": ["co-borrower name", "co-borrower", "coborrower"],
    "lender_name": ["lender on report", "client", "lender", "lender/client", "client name"],
    "lender_address": ["lender address", "client address"],
    "form_type": ["form", "product", "report type", "order type"],
    "loan_type": ["loan type"],
    "assignment_type": ["intended use", "transaction type", "loan purpose"],
    "file_id": ["file id", "order number", "order #", "file #"],
    "loan_number": ["loan #", "loan number", "loan no"],
    "fha_case_number": ["fha case number", "fha case #", "case number"],
    "legal_description": ["legal description"],
    "appraiser_name": ["appraiser", "vendor"],
    "amc_reg_number": ["amc reg. number", "amc reg number", "amc registration"],
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


def parse_address(raw: str) -> Dict[str, str]:
    """Parse '<street>, <city>, <state>, <zip>' or '<street>, <city> ST zip'."""
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
        # Format A: street, city, state, zip
        out["property_address"] = parts[0]
        out["city"] = parts[1]
        st = parts[2].lower()
        out["state"] = _STATE_ABBR.get(st, parts[2].upper() if parts[2].upper() in _ABBRS else "")
    else:
        # Tail "... city ST zip" / "... city Statename zip"
        m = re.search(r"(.+?)\s+([A-Za-z]{2,})\s+\d{5}", s)
        if m:
            stok = m.group(2).lower()
            out["state"] = (_STATE_ABBR.get(stok)
                            or (m.group(2).upper() if m.group(2).upper() in _ABBRS else ""))
            head = m.group(1).strip()
            if "," in head:
                # "street, city" → split on last comma
                street, city = head.rsplit(",", 1)
                out["property_address"] = street.strip()
                out["city"] = city.strip()
            else:
                # no comma — can't reliably split street/city; keep combined,
                # leave city unset so a wrong city never causes a false FAIL.
                out["property_address"] = head
        else:
            out["property_address"] = parts[0]
    if out.get("state") and out["state"] not in _ABBRS:
        out["state"] = ""
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
                # first line = name; any extra lines = address (Format A client block)
                if "lender_name" not in found:
                    found["lender_name"] = block[0].strip()
                if len(block) > 1 and "lender_address" not in found:
                    found["lender_address"] = " ".join(block[1:]).strip()
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
