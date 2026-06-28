"""
Sales-contract extractor — best-effort price/date/parties.

Contracts are the hardest input in the corpus: TREC contracts are flattened
scans (no text layer), and the Michigan/Florida purchase agreements keep their
values on blank fill-in lines. So this extractor:
  * reads the embedded text where a page has it, else OCRs the rendered page
    with Tesseract (the reliable OCR path in this environment),
  * pulls the contract PRICE (the largest plausible dollar amount appearing in a
    price context) and the contract DATE (latest date = fully-executed date),
    plus seller/buyer names when clearly labelled.

It returns only what it finds with reasonable confidence. When a contract is
unreadable, it returns nothing and the C-2/C-4 rules stay at VERIFY (a reviewer
compares manually) rather than risk a false price mismatch.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import fitz

logger = logging.getLogger(__name__)

_PRICE_CTX = re.compile(r"(sales?\s*price|purchase\s*price|total|sum of|cash\s*portion|"
                        r"contract\s*price|3a|3b)", re.I)
_AMOUNT = re.compile(r"\$?\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{5,})")
_DATE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b")
_CONCESSION_CTX = re.compile(r"(concession|seller\s*(?:paid|to pay|contribution)|"
                             r"seller\s*conc)", re.I)


def _tesseract_text(page) -> str:
    """OCR a rendered page via Tesseract using a temp PNG path (reliable here)."""
    try:
        import pytesseract
        from PIL import Image
        mat = fitz.Matrix(220 / 72, 220 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            img.save(tmp)
            return pytesseract.image_to_string(tmp, config="--psm 6 --oem 3")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    except Exception as exc:
        logger.warning("Contract OCR failed: %s", exc)
        return ""


def _page_text(page) -> str:
    embedded = page.get_text("text")
    if len(embedded.split()) >= 30:
        return embedded
    return _tesseract_text(page)


def _to_amount(s: str) -> Optional[float]:
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _line_amount(line: str, lo: float = 1000.0) -> Optional[float]:
    """Largest plausible amount on a single line (>= lo)."""
    best = None
    for m in _AMOUNT.finditer(line):
        v = _to_amount(m.group(1))
        if v is not None and lo <= v <= 50_000_000:
            best = max(best or 0, v)
    return best


# A purchase-price *declaration* clause (not a prose mention of "purchase price").
# Anchored so boilerplate like "applied towards the purchase price of the Property"
# does not match: requires "to be paid"/"offers to buy ... sum of"/"(U.S. currency)"
# right after the label, or a numbered clause heading.
_PRICE_DECL = re.compile(
    r"(purchase\s*price\s*(?:of\s*property)?\s*to\s*be\s*paid|"
    r"offers?\s*to\s*buy.*for\s*the\s*sum\s*of|"
    r"(?:purchase|sales?)\s*price\b[^.]*u\.?s\.?\s*currency|"
    r"^\s*\d+\.?\s*(?:purchase|sales?)\s*price\b)", re.I)
# A line that LEADS with a dollar amount (the value line under a declaration), e.g.
# "$ 263,000.00 Closing: $ 0.00" — take the first amount as the price.
_LEAD_AMOUNT = re.compile(r"^\s*\$?\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{5,})")


def _lead_amount(line: str, lo: float = 10_000.0) -> Optional[float]:
    """Amount when the line begins with it (value line under a label)."""
    m = _LEAD_AMOUNT.match(line)
    if not m:
        return None
    v = _to_amount(m.group(1))
    return v if v is not None and lo <= v <= 50_000_000 else None


def _contract_price(text: str) -> Optional[str]:
    """Targeted contract-price extraction (no noisy 'largest amount' fallback).

    Strategy 1 (TREC): Cash portion (A) + Loan/Financing (B) = Sales Price.
    Strategy 2: an explicit 'Sales/Purchase Price (Sum...)' or 'Total ... Price'
    line carrying an amount.
    Strategy 3: a purchase-price *declaration* clause whose amount sits on the
    NEXT line (e.g. Georgia F201: label then "$ 263,000.00 Closing: $ 0.00").
    Returns None when none is confidently found → the QC rule stays VERIFY.
    """
    lines = text.splitlines()
    cash = loan = None
    explicit = None
    declared = None
    for i, ln in enumerate(lines):
        low = ln.lower()
        if "cash portion" in low and cash is None:
            cash = _line_amount(ln)
        elif re.search(r"\b(loan|financing|third party|seller financing)\b", low) and loan is None:
            loan = _line_amount(ln, lo=10_000)
        elif re.search(r"(sales?\s*price\s*\(sum|total\s*(sales?|purchase)\s*price|"
                       r"purchase\s*price.*\bsum\b)", low):
            amt = _line_amount(ln, lo=10_000)
            if amt:
                explicit = amt
        elif declared is None and _PRICE_DECL.search(ln):
            amt = _line_amount(ln, lo=10_000)            # same-line amount?
            if amt is None:                              # else look at next 2 lines
                for nxt in (l for l in lines[i + 1:i + 3] if l.strip()):
                    amt = _lead_amount(nxt)
                    break
            if amt is not None:
                declared = amt
    if cash is not None and loan is not None:
        total = cash + loan
        if 10_000 <= total <= 50_000_000:
            return str(int(total))
    if explicit:
        return str(int(explicit))
    if declared:
        return str(int(declared))
    return None


def _dates_on(text: str):
    """[(y,m,d) tuples with formatted string] for every plausible date."""
    out = []
    for mm, dd, yy in _DATE.findall(text):
        m_, d_, y_ = int(mm), int(dd), int(yy)
        if y_ < 100:
            y_ += 2000
        if 1 <= m_ <= 12 and 1 <= d_ <= 31 and 2000 <= y_ <= 2099:
            out.append(((y_, m_, d_), f"{m_:02d}/{d_:02d}/{y_}"))
    return out


# Lines whose dates are deadlines/boilerplate, not the executed date — taking
# the "latest date anywhere" used to pick the closing date over the signature.
_DATE_NOISE = re.compile(r"(closing date|option (fee|period)|trec|effective date of loan|"
                         r"expires|deadline)", re.I)
_EXECUTED_CTX = re.compile(r"(executed|effective date)", re.I)


def _contract_date(text: str) -> Optional[str]:
    """The fully-executed contract date.

    Priority 1: a date within two lines of an EXECUTED / effective-date clause
    (TREC puts this block on the signature page, ~page 9). Priority 2: the
    latest date in the document, ignoring deadline/boilerplate lines (closing
    date, option period, the TREC form-revision date)."""
    lines = text.splitlines()
    executed, fallback = None, None
    for i, ln in enumerate(lines):
        for key, formatted in _dates_on(ln):
            # the EXECUTED clause sits on the date's line, the two lines above
            # it, or one line below (e-sign stamps land just above the blank:
            # "04/27/2026" then "EXECUTED the __ day of __, 20__")
            window = " ".join(lines[max(0, i - 2):i + 2])
            if _EXECUTED_CTX.search(window):
                if executed is None or key > executed[0]:
                    executed = (key, formatted)
            elif not _DATE_NOISE.search(ln):
                if fallback is None or key > fallback[0]:
                    fallback = (key, formatted)
    best = executed or fallback
    return best[1] if best else None


def _concessions(text: str) -> Optional[str]:
    for line in text.splitlines():
        if _CONCESSION_CTX.search(line):
            for m in _AMOUNT.finditer(line):
                v = _to_amount(m.group(1))
                if v is not None and 0 < v <= 200_000:
                    return str(int(v))
    return None


# TREC One-to-Four ¶12A(1)(b): "Seller shall also pay an amount not to exceed
# $____ to be applied to Buyer's Expenses" — the seller concession on a TREC
# contract lives here, never on a labelled "concessions" line.
_TREC_SELLER_PAY = re.compile(
    r"seller shall (?:also )?pay an amount not to exceed\s*\$?\s*"
    r"([\d]{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)", re.I)
_TREC_SELLER_PCT = re.compile(
    r"seller shall (?:also )?pay[^.\n]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%\s*of the sales price", re.I)


def _trec_concessions(text: str, price: Optional[str]) -> Optional[str]:
    """Seller-paid buyer expenses from TREC ¶12 (Settlement and Other Expenses).
    A percentage form is converted to dollars when the sales price is known.
    Returns a digit string (possibly '0'), or None when ¶12 isn't found."""
    m = _TREC_SELLER_PAY.search(text)
    if m:
        v = _to_amount(m.group(1))
        if v is not None and 0 <= v <= 200_000:
            return str(int(v))
    m = _TREC_SELLER_PCT.search(text)
    if m and price:
        try:
            return str(int(float(m.group(1)) / 100.0 * float(price)))
        except ValueError:
            return None
    return None


# TREC ¶1 PARTIES: "The parties to this contract are ____ (Seller) and ____
# (Buyer)." plus generic labelled buyer lines on other state forms.
_TREC_PARTIES = re.compile(r"\(\s*seller\s*\)\s*and\s+(.{3,120}?)\s*\(\s*buyer\s*\)",
                           re.I | re.S)
_BUYER_LINE = re.compile(r"^\s*(?:buyer|purchaser)s?\s*[:\-]\s*(.{3,120})$", re.I)


def _buyer_names(text: str) -> Optional[str]:
    """The buyer/purchaser name string from the contract, or None.

    Powers the S-2 contract co-buyer advisory: the contract may list a buyer
    the order form never disclosed."""
    m = _TREC_PARTIES.search(text)
    if m:
        names = re.sub(r"\s+", " ", m.group(1)).strip(" ,;")
        if names and not names.lower().startswith(("the ", "a ")):
            return names
    for line in text.splitlines():
        lm = _BUYER_LINE.match(line)
        if lm:
            names = lm.group(1).strip(" ,;")
            # a name, not a clause ("Buyer: shall pay...")
            if names and not re.search(r"\b(shall|will|must|agrees)\b", names, re.I):
                return names
    return None


# Non-realty items a purchase contract may convey. When any appear in a
# personal-property context the appraiser must address contributory value
# (rule C-5), so they are surfaced as a pseudo-field for the rule engine.
_PERSONAL_ITEMS = re.compile(
    r"\b(refrigerator|washer|dryer|freezer|furniture|furnishings|hot tub|"
    r"spa|pool table|playset|play set|shed|trampoline|riding mower|tractor|"
    r"golf cart|boat|trailer|atv)\b", re.I)
_PERSONAL_CTX = re.compile(r"(personal property|non-?realty|chattel|items? (that )?"
                           r"(will|shall|to) (convey|remain|be included))", re.I)


def _personal_property(text: str) -> Optional[str]:
    """Comma list of personal-property items the contract conveys, or None.

    Items count only when they appear near a personal-property context line —
    a bare appliance mention in the inclusions boilerplate is normal realty
    fixture language, not chattel."""
    lines = text.splitlines()
    found = []
    for i, ln in enumerate(lines):
        if not _PERSONAL_CTX.search(ln):
            continue
        window = " ".join(lines[max(0, i - 1):i + 4])
        for m in _PERSONAL_ITEMS.finditer(window):
            item = m.group(1).lower()
            if item not in found:
                found.append(item)
    return ", ".join(found) if found else None


# Lines worth showing the LLM — price/party/signature clauses. A long condo
# developer agreement (40+ pages) would otherwise be cut off by a flat
# character cap before the relevant clauses ever appear in the prompt.
_DIGEST_CTX = re.compile(
    r"(purchase price|sales price|total.*price|executed|effective date|"
    r"buyer|purchaser|seller|concession|witness|signature|\$\s*\d|"
    # bare comma-grouped amounts: form-overlay PDFs render the filled value as
    # a detached text object with no $ or label on its line ("459,900.00")
    r"\b\d{1,3},\d{3}(?:\.\d{2})?\b)", re.I)


def _llm_digest(text: str, cap: int = 11000) -> str:
    """Relevant-line digest of the contract (with one line of context each),
    in document order, capped at `cap` characters. The head of the document is
    always kept — the parties/cover block names the buyers without any
    searchable keyword on the line itself."""
    lines = text.splitlines()
    keep = set(range(min(60, len(lines))))
    for i, ln in enumerate(lines):
        if _DIGEST_CTX.search(ln):
            keep.update((max(0, i - 1), i, min(len(lines) - 1, i + 1)))
    out, used = [], 0
    for i in sorted(keep):
        ln = lines[i].strip()
        if not ln:
            continue
        used += len(ln) + 1
        if used > cap:
            break
        out.append(ln)
    return "\n".join(out) if out else text[:cap]


def _llm_gap_fill(text: str, missing) -> Dict[str, str]:
    """Groq fallback for contract fields the regex strategies missed.

    Same trust rule as the other LLM "brain" layers: a price/concession answer
    must literally appear on the page (digit-run containment) and a date answer
    must be one of the dates already seen by the regex scan — the LLM only
    *selects* among printed values, it can never invent one. Empty dict when the
    LLM is unavailable (P-6)."""
    try:
        from app.extraction import llm_groq
        if not llm_groq.groq_extraction_available():
            return {}
        wanted = {
            "contract_price": "total purchase/sales price of the property (digits only)",
            "contract_date": "the date the contract became fully executed — the LATEST "
                             "signature date (MM/DD/YYYY)",
            "concessions_amount": "total seller-paid concessions/contributions toward "
                                  "buyer costs (digits only); omit if none",
            "buyer_names": "the buyer/purchaser name(s) VERBATIM as printed in the "
                           "parties clause",
        }
        asks = {f: wanted[f] for f in missing if f in wanted}
        if not asks:
            return {}
        lines = "\n".join(f'- "{k}": {v}' for k, v in asks.items())
        data = llm_groq.chat_json(
            [
                {"role": "system",
                 "content": "You read residential real-estate purchase contracts. "
                            "Output ONLY one valid JSON object."},
                {"role": "user",
                 "content": "Extract ONLY these fields from the contract text below. "
                            "OMIT any field not actually present — never guess.\n"
                            f"{lines}\n\nCONTRACT TEXT (relevant excerpts):\n{_llm_digest(text)}"},
            ],
            reasoning_effort="low", max_tokens=1024,
        )
        if not isinstance(data, dict):
            return {}
        out: Dict[str, str] = {}
        digit_runs = set(re.findall(r"\d+", re.sub(r"[,$]", "", text)))
        valid_dates = {f"{int(m):02d}/{int(d):02d}/{int(y) + 2000 if int(y) < 100 else int(y)}"
                       for m, d, y in _DATE.findall(text)}
        for f in ("contract_price", "concessions_amount"):
            s = re.sub(r"[,$\s]", "", str(data.get(f, "") or ""))
            try:
                v = str(int(float(s))) if s else ""
            except ValueError:
                v = ""
            if v and v in digit_runs and 0 < float(v) <= 50_000_000:
                out[f] = v
        dv = str(data.get("contract_date", "") or "").strip()
        m = _DATE.search(dv)
        if m:
            mm, dd, yy = (int(x) for x in m.groups())
            yy = yy + 2000 if yy < 100 else yy
            cand = f"{mm:02d}/{dd:02d}/{yy}"
            if cand in valid_dates:
                out["contract_date"] = cand
        # buyer names: verbatim containment in the printed text (whitespace-
        # normalized), same trust rule as every other LLM answer
        bv = re.sub(r"\s+", " ", str(data.get("buyer_names", "") or "")).strip()
        if bv and bv.lower() in re.sub(r"\s+", " ", text).lower():
            out["buyer_names"] = bv
        return out
    except Exception as exc:
        logger.warning("Contract LLM gap-fill failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Concessions description extraction
# ---------------------------------------------------------------------------

# Common concession type labels found in financing sections of purchase contracts.
_CONCESSION_TYPE_LABELS = re.compile(
    r"(closing\s*costs?|buyer['']?s?\s*(?:closing\s*)?costs?|"
    r"pre-?paid[s]?|points|origination|discount\s*points?|"
    r"interest\s*rate\s*buy[\s-]?down|buy[\s-]?down|"
    r"seller[\s-]?paid\s*(?:closing\s*)?costs?|"
    r"seller\s*contributions?|seller\s*concessions?|"
    r"buyer['']?s?\s*expenses?|repairs?|fix-?ups?)",
    re.I,
)


def _concessions_description(text: str) -> Optional[str]:
    """Extract a brief concession-type description from the financing section.

    Scans the 10 lines surrounding any concession context line and collects
    all descriptive type labels (closing costs, points, buy-down, etc.).
    Returns a comma-separated string of unique labels, or None when none found.
    """
    lines = text.splitlines()
    hits: List[str] = []
    for i, ln in enumerate(lines):
        if not _CONCESSION_CTX.search(ln):
            continue
        window = "\n".join(lines[max(0, i - 2):i + 8])
        for m in _CONCESSION_TYPE_LABELS.finditer(window):
            label = re.sub(r"\s+", " ", m.group(1)).strip().lower()
            if label not in hits:
                hits.append(label)
    return ", ".join(hits) if hits else None


# ---------------------------------------------------------------------------
# Public classification and execution-status helpers
# (used by ContractPackage.from_single_path and downstream rule checks)
# ---------------------------------------------------------------------------

_AMENDMENT_PHRASES_PUB = re.compile(
    r"(amendment|addendum\s+to\s+(purchase|contract)|change\s+in\s+terms|"
    r"revised\s+(purchase|contract)|modification\s+of\s+(purchase|agreement)|"
    r"counter\s*offer|counter-?offer|backup\s+offer)",
    re.I,
)


def classify_contract_document(text: str) -> str:
    """Return "amendment" if the text is an amendment/addendum, else "base".

    Used by ContractPackage to distinguish the controlling base contract from
    subsequent amendments so the package can resolve the final transaction state.
    """
    return "amendment" if _AMENDMENT_PHRASES_PUB.search(text) else "base"


_CHECK_UNSIGNED = re.compile(
    r"(not\s+(signed|executed)|unsigned|awaiting\s+signature|"
    r"will\s+be\s+executed|executed\s+at\s+closing)",
    re.I,
)
_CHECK_SIG_BLOCK = re.compile(
    r"(x___|_{4,}|signed[\s:]*([A-Z][a-z]+\s+[A-Z][a-z]+)|"
    r"buyer\s+signature|seller\s+signature|by:\s*/s/)",
    re.I,
)


def check_execution_status(text: str) -> bool:
    """Return True when the contract document appears to be fully executed.

    Heuristic: if any explicit unexecuted language is present the document is
    not executed. Otherwise, two or more distinct signature-block markers
    (buyer + seller) indicate it is executed.  The caller should treat the
    result as advisory — the appraiser's own contract analysis commentary
    (checked by C-EXEC) is the authoritative signal for rule purposes.
    """
    tail = text[-3000:]  # signature blocks live at the end
    if _CHECK_UNSIGNED.search(tail):
        return False
    return len(_CHECK_SIG_BLOCK.findall(tail)) >= 2


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_contract_fields(pdf_path, ocr_max_pages: int = 13) -> Dict[str, str]:
    """Return {canonical_field: value} from the sales contract (best effort).

    Embedded text is read from EVERY page (cheap — a 42-page condo developer
    agreement keeps its price schedule and signatures deep in the document);
    Tesseract OCR for image-only pages is capped at ocr_max_pages, which covers
    the whole scanned TREC One-to-Four including the EXECUTED block (~page 9).

    The returned dict always includes the private keys:
      ``_raw_text`` — full concatenated document text (used by ContractPackage)
      ``_path``     — resolved file path string (used by ContractPackage)
    These private keys are stripped by the overlay layer before persisting.
    """
    pdf_path = Path(pdf_path)
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("Cannot open contract %s: %s", pdf_path, exc)
        return {}
    texts: List[str] = []
    try:
        for i in range(len(doc)):
            embedded = doc[i].get_text("text")
            if len(embedded.split()) >= 30:
                texts.append(embedded)
            elif i < ocr_max_pages:
                texts.append(_tesseract_text(doc[i]))
    finally:
        doc.close()
    text = "\n".join(texts)
    if not text.strip():
        return {}

    out: Dict[str, str] = {}
    price = _contract_price(text)
    if price:
        out["contract_price"] = price
    date = _contract_date(text)
    if date:
        out["contract_date"] = date
    conc = _concessions(text)
    if conc is None:
        conc = _trec_concessions(text, price)
    if conc is not None:
        out["concessions_amount"] = conc
    conc_desc = _concessions_description(text)
    if conc_desc:
        out["concessions_description"] = conc_desc
    items = _personal_property(text)
    if items:
        out["personal_property_items"] = items
    buyers = _buyer_names(text)
    if buyers:
        out["buyer_names"] = buyers
    # LLM fallback for whatever the regex strategies could not find — answers
    # are validated against the printed text, so a wrong pick cannot pass.
    missing = [f for f in ("contract_price", "contract_date", "concessions_amount",
                           "buyer_names")
               if f not in out]
    if missing:
        out.update(_llm_gap_fill(text, missing))
    # Private metadata used by ContractPackage — stripped by _overlay_contract
    # before the result set is persisted (these keys start with "_" which the
    # overlay loop skips: `if not value: continue` rejects blank, and the
    # ExtractionResult canonical_name validation ignores underscore-prefixed keys).
    out["_raw_text"] = text
    out["_path"] = str(pdf_path)
    return out
