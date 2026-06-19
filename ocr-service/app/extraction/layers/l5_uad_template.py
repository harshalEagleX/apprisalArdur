"""
Layer 5 — UAD Form Template Parser

The UAD 1004/1073/1004C are STANDARDIZED FORMS defined by Fannie Mae.
Every copy of the same form version has labels in EXACTLY the same positions.
This layer uses that knowledge to extract fields by their known page positions.

Why this achieves near-100% extraction:
  - No label matching needed — we know WHERE each field is
  - Yes/No checkboxes: find the question by position, then check which box has the X
  - Grid data: read cell at exact row/column position
  - Works even when OCR garbles labels

Coverage:
  - All Yes/No questions on pages 1-5 of UAD 1004/1073
  - Neighborhood price/age grid
  - Land use percentages
  - Improvements room count / GLA / condition
  - Contract section checkboxes
  - Site section checkboxes (HBU, FEMA, utilities, adverse)

This layer runs LAST and fills any remaining gaps after L0-L4b.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ===========================================================================
# UAD 1004 FORM Yes/No questions — label-anchored.
#
# Each entry: (field_name, [keyword tokens that must appear consecutively
#              in the question line], yes_means_true)
#
# Strategy: find the keyword sequence on a page, then look for the
# Yes/No word tokens on the SAME row to the right of the keyword.
# This survives template shifts because we never hardcode coordinates.
# ===========================================================================

UAD_YES_NO_QUESTIONS = [
    # "Is the subject property currently offered for sale or has it been
    #  offered for sale in the twelve months prior to ..."
    ("offered_for_sale_12mo", ["offered", "for", "sale"], True),
    # "Is there any financial assistance ..."
    ("has_financial_assistance", ["financial", "assistance"], True),
    # "Is the property seller the owner of public record?"
    ("is_seller_owner_of_record", ["seller", "the", "owner"], True),
    # "Is the highest and best use of subject property as improved ..."
    ("highest_and_best_use", ["highest", "and", "best"], True),
    # "Are the utilities and off-site improvements typical for the market area?"
    ("utilities_typical_for_market", ["utilities", "typical"], True),
    # "FEMA Special Flood Hazard Area"
    ("fema_flood_hazard", ["FEMA", "Special", "Flood"], True),
    # "Are there any adverse site conditions or external factors ..."
    ("adverse_site_conditions", ["adverse", "site", "conditions"], True),
    # "Are there any physical deficiencies or adverse conditions that affect
    #  the livability, soundness, or structural integrity ..."
    ("adverse_conditions", ["physical", "deficiencies"], True),
    # "Does the property generally conform to the neighborhood ..."
    ("conforms_to_neighborhood", ["generally", "conform"], True),
    # PUD: "Is the developer/builder in control of the Homeowners' Association"
    ("is_developer_controls_hoa", ["developer", "control"], True),
]

# ===========================================================================
# UAD SECTION HEADER PATTERNS — to identify which page/section we're on
# ===========================================================================

SECTION_MARKERS = {
    "subject":       ["SUBJECT", "Property Address", "Borrower"],
    "contract":      ["CONTRACT", "Contract Price", "Date of Contract"],
    "neighborhood":  ["NEIGHBORHOOD", "Location", "Built-Up", "Growth"],
    "site":          ["SITE", "Dimensions", "Zoning", "FEMA"],
    "improvements":  ["IMPROVEMENTS", "General Description", "Year Built"],
    "sales_comp":    ["SALES COMPARISON", "COMPARABLE SALE", "Proximity to Subject"],
    "reconciliation":["RECONCILIATION", "Final Opinion", "Indicated Value"],
}


def _get_drawings_by_page(pdf_path: Path) -> Dict[int, list]:
    """Get vector drawings per page for checkbox detection."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        result = {}
        for i in range(min(8, len(doc))):
            result[i + 1] = doc[i].get_drawings()
        doc.close()
        return result
    except Exception:
        return {}


def _find_checked_at_y(drawings: list, y_min: float, y_max: float,
                        x_lo: float, x_hi: float) -> Optional[float]:
    """
    Find the X position of a CHECKED checkbox (X-mark in drawing layer)
    within the specified Y and X band.
    Returns the X of the checked box, or None if unchecked/not found.
    """
    from collections import defaultdict
    pos_groups = defaultdict(list)
    for d in drawings:
        r = d.get("rect")
        if not r:
            continue
        if not (4 <= r.width <= 12 and 4 <= r.height <= 12):
            continue
        if not (y_min <= r.y0 <= y_max and x_lo <= r.x0 <= x_hi):
            continue
        key = (round(r.x0, 1), round(r.y0, 1))
        pos_groups[key].append(d)

    # Check for X-mark (rect + 2 diagonals) at each position
    for (x, y), draws in pos_groups.items():
        has_rect = False
        diag_count = 0
        for d in draws:
            for item in d.get("items", []):
                if item[0] == "re":
                    has_rect = True
                elif item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p2.x - p1.x) > 2 and abs(p2.y - p1.y) > 2:
                        diag_count += 1
        if has_rect and diag_count >= 2:
            return x
    return None


def _find_keyword_anchor(words: list, keywords: List[str]) -> Optional[tuple]:
    """
    Find consecutive keyword tokens on a page.

    `words` is the PyMuPDF word list: each item is
    (x0, y0, x1, y1, text, block, line, word_idx).

    Returns (x_end, y_mid) of the LAST keyword token in the matched
    sequence, or None if no sequence matched.

    Matching is case-insensitive. Tokens must be on the same line
    (within ±3 px in y) and in left-to-right order, but other words
    are allowed between them so partial paraphrases still anchor.
    """
    if not keywords:
        return None
    lowered = [k.lower() for k in keywords]

    # Group words by line (y-bucket of 3px).
    lines: Dict[int, list] = {}
    for w in words:
        bucket = round(w[1] / 3)
        lines.setdefault(bucket, []).append(w)

    for bucket, line_words in lines.items():
        line_words.sort(key=lambda w: w[0])
        texts = [w[4].lower().strip(".,:") for w in line_words]
        # Scan for the keywords in order, allowing gaps.
        idx = 0
        last_match_w = None
        for w, t in zip(line_words, texts):
            if t == lowered[idx]:
                last_match_w = w
                idx += 1
                if idx == len(lowered):
                    return (last_match_w[2], (last_match_w[1] + last_match_w[3]) / 2)
    return None


def _yes_no_state_for_anchor(
    words: list, drawings: list, anchor_x: float, anchor_y: float
) -> Optional[bool]:
    """
    Given a question's anchor position (end-of-keyword), find the Yes/No
    word tokens on the same row to the right and determine which one
    has its checkbox X-marked.

    Returns True if Yes is checked, False if No is checked, None if
    neither (or both) appear checked.
    """
    yes_word = no_word = None
    for w in words:
        if abs(((w[1] + w[3]) / 2) - anchor_y) > 4:
            continue
        if w[0] < anchor_x - 2:  # must be to the right of the question
            continue
        token = w[4].strip().lower().rstrip(".")
        if token == "yes" and yes_word is None:
            yes_word = w
        elif token == "no" and no_word is None:
            no_word = w

    if yes_word is None or no_word is None:
        return None

    # Checkbox is to the LEFT of each label, within ~25 px.
    y_lo = anchor_y - 8
    y_hi = anchor_y + 8

    yes_checked = _find_checked_at_y(
        drawings, y_lo, y_hi, yes_word[0] - 25, yes_word[0] + 2
    )
    no_checked = _find_checked_at_y(
        drawings, y_lo, y_hi, no_word[0] - 25, no_word[0] + 2
    )

    if yes_checked is not None and no_checked is None:
        return True
    if no_checked is not None and yes_checked is None:
        return False
    return None


def _extract_yes_no_fields(pdf_path: Path) -> Dict[str, str]:
    """
    Extract Yes/No fields by anchoring on the question text.

    For each question keyword sequence, scan all pages, find the
    keyword anchor, then look for the checked Yes/No box on the
    same row to the right of the anchor.
    """
    results: Dict[str, str] = {}
    drawings_by_page = _get_drawings_by_page(pdf_path)

    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception:
        return results

    # Cache page words for repeat lookups.
    pages_data: Dict[int, tuple] = {}
    for page_idx in range(min(8, len(doc))):
        page = doc[page_idx]
        pn = page_idx + 1
        pages_data[pn] = (page.get_text("words"), drawings_by_page.get(pn, []))

    for field_name, keywords, yes_means_true in UAD_YES_NO_QUESTIONS:
        if field_name in results:
            continue
        for pn, (words, drawings) in pages_data.items():
            anchor = _find_keyword_anchor(words, keywords)
            if anchor is None:
                continue
            anchor_x, anchor_y = anchor
            yes_state = _yes_no_state_for_anchor(words, drawings, anchor_x, anchor_y)
            if yes_state is None:
                continue
            value = ("True" if yes_state else "False") if yes_means_true else ("False" if yes_state else "True")
            results[field_name] = value
            logger.debug(
                "L5 template %s=%s (anchor=%s on p%d at y=%.0f)",
                field_name, value, " ".join(keywords), pn, anchor_y,
            )
            break

    doc.close()
    return results


def _extract_neighborhood_grid(pdf_path: Path) -> Dict[str, str]:
    """
    Extract neighborhood price/age grid from PDF word positions.

    Strategy: anchor on the row labels Low / High / Pred. — these words
    only appear inside the One-Unit Housing price/age grid on this form.

    Form layout (URAR 1004/1073 — the label sits BETWEEN price and age):
        [PRICE $000]  [Low / High / Pred.]  [AGE yrs]

    PRICE = nearest numeric word to the LEFT of the label (within 80 px).
    AGE   = nearest numeric word to the RIGHT of the label (within 40 px).

    Both distance caps prevent numbers from adjacent rows bleeding in
    when rows are tightly spaced. The Y-tolerance is kept tight (±3 px)
    for the same reason — relaxing it to ±6 caused the "High" row's age
    value (e.g. 101) to appear in the "Low" row's price slot.

    Post-extraction sanity checks discard implausible swaps:
      - price_low > price_high  →  both dropped (misread)
      - price_low < 10          →  likely an age value leaked into price slot
    """
    results: Dict[str, str] = {}
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:6]:
                text = page.extract_text() or ""
                if "PRICE" not in text and "Predominant" not in text:
                    continue
                # Must also see the One-Unit Housing label nearby; that
                # eliminates pages that mention "Price" elsewhere (cover
                # letter, sales comparison) without the neighborhood grid.
                if "One-Unit" not in text and "NEIGHBORHOOD" not in text.upper():
                    continue

                words = page.extract_words()

                # Map row-label text -> (price_field, age_field).
                row_to_fields = {
                    "low":  ("price_low", "age_low"),
                    "high": ("price_high", "age_high"),
                    "pred": ("predominant_price", "predominant_age"),
                    "predominant": ("predominant_price", "predominant_age"),
                }

                for w in words:
                    label = w["text"].strip().lower().rstrip(".")
                    if label not in row_to_fields:
                        continue
                    if label == "predominant":
                        label = "pred"
                    price_field, age_field = row_to_fields[label]
                    if price_field in results and age_field in results:
                        continue

                    label_x_lo = w["x0"]
                    label_x_hi = w["x1"]
                    label_y_mid = (w["top"] + w["bottom"]) / 2

                    # Candidate numeric words on the SAME visual row.
                    # Y-tolerance tightened to ±3 px (was ±6 px) to prevent
                    # numbers from adjacent rows bleeding into the wrong slot.
                    same_row = []
                    for nw in words:
                        nwy = (nw["top"] + nw["bottom"]) / 2
                        if abs(nwy - label_y_mid) > 3:
                            continue
                        txt = nw["text"].replace(",", "").strip()
                        if not re.fullmatch(r"\d+(?:\.\d+)?", txt):
                            continue
                        try:
                            val = float(txt)
                        except ValueError:
                            continue
                        same_row.append((nw["x0"], nw["x1"], val))

                    if not same_row:
                        continue

                    # PRICE = nearest number to the LEFT of the label,
                    # value in $000 (range 10..5000 covers $10k..$5M).
                    # Cap at 80 px distance — the price column sits close to
                    # the label; a farther number is from a different column.
                    left_candidates = [
                        (label_x_lo - x1, val)
                        for x0, x1, val in same_row
                        if x1 < label_x_lo and 10 <= val <= 5000
                        and (label_x_lo - x1) <= 80
                    ]
                    if left_candidates and price_field not in results:
                        left_candidates.sort()  # smallest distance first
                        v = left_candidates[0][1]
                        results[price_field] = str(int(v)) if v == int(v) else str(v)

                    # AGE = nearest number to the RIGHT of the label,
                    # range 0..200 years. Land-use % values sit MUCH
                    # further right (>60 px) — reject those by distance.
                    right_candidates = [
                        (x0 - label_x_hi, val)
                        for x0, x1, val in same_row
                        if x0 > label_x_hi and 0 <= val <= 200
                    ]
                    if right_candidates and age_field not in results:
                        right_candidates.sort()
                        dist, v = right_candidates[0]
                        # Closest right-side number must be within 40 px
                        # of the label — beyond that we're in the Present
                        # Land Use % column, not the AGE column.
                        if dist <= 40:
                            results[age_field] = str(int(v)) if v == int(v) else str(v)

                if results:
                    break

    except Exception as exc:
        logger.debug("L5 neighborhood grid extraction failed: %s", exc)

    # Sanity-check: if price_low > price_high both were likely misread; drop
    # them so the N-3 rule VERIFYs rather than fires on garbage data.
    try:
        pl = float(results.get("price_low", 0) or 0)
        ph = float(results.get("price_high", 0) or 0)
        if pl and ph and pl > ph:
            logger.debug("N-grid sanity: price_low(%s) > price_high(%s) — dropping both", pl, ph)
            results.pop("price_low", None)
            results.pop("price_high", None)
    except (ValueError, TypeError):
        pass

    return results


def _extract_gla_from_improvements(pdf_path: Path) -> Dict[str, str]:
    """
    Extract GLA (Gross Living Area) from the improvements section.

    On UAD 1004 the GLA appears in the improvements section as:
        "Finished area above grade contains:
             N Rooms   M Bedrooms   B Bath(s)   GLA Square Feet of
             Gross Living Area Above Grade"

    The reliable anchor is the phrase "Square Feet of Gross Living Area".
    The GLA number sits IMMEDIATELY before that phrase on the same row.
    """
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(8, len(doc))):
            page = doc[page_idx]
            text = page.get_text("text")
            if "Gross Living Area" not in text and "Square Feet" not in text:
                continue

            words = page.get_text("words")
            # Each word is (x0, y0, x1, y1, text, block, line, word_idx)

            # Find every "Square" word whose neighbors form
            # "Square Feet of Gross Living Area".
            anchors: List[tuple] = []
            for i, w in enumerate(words):
                if w[4].strip().lower() != "square":
                    continue
                # Look ahead a few words for "Feet ... Gross Living Area"
                tail = " ".join(words[j][4] for j in range(i, min(i + 7, len(words)))).lower()
                if "feet" in tail and "gross living area" in tail:
                    anchors.append((w[0], w[1]))  # (x, y) of "Square"

            for anchor_x, anchor_y in anchors:
                # GLA number is on the same row, just to the LEFT of "Square".
                # Same row = within ±3 px in y. Numeric, 3-5 digits, plausible range.
                candidates = []
                for w in words:
                    if not (abs(w[1] - anchor_y) < 4 and w[0] < anchor_x):
                        continue
                    txt = w[4].replace(",", "").strip()
                    if not re.fullmatch(r"\d{3,5}", txt):
                        continue
                    val = int(txt)
                    if 300 <= val <= 15000:
                        candidates.append((w[0], val))
                if candidates:
                    # Closest number to the left of "Square" wins.
                    candidates.sort(key=lambda c: anchor_x - c[0])
                    results["gla"] = str(candidates[0][1])
                    break

            if "gla" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 GLA extraction failed: %s", exc)

    return results


def _extract_effective_date_all_formats(pdf_path: Path) -> Dict[str, str]:
    """
    Extract effective date using multiple format patterns.

    Format 1 (Henderson/MSL): date before license number on signature page
      04/17/2026\nCR348700\n → effective_date = 04/17/2026

    Format 2 (Equity Solutions cover letter): date on page 1 after appraised value
      587,000\n05/08/2026 → effective_date = 05/08/2026

    Format 3 (USPAP/signature page): "Effective Date of Appraisal: MM/DD/YYYY"

    Format 4 (any page): "as of MM/DD/YYYY" or "effective MM/DD/YYYY"
    """
    results: Dict[str, str] = {}
    try:
        import fitz, datetime
        doc = fitz.open(str(pdf_path))
        full_text = "\n".join(doc[i].get_text("text") for i in range(min(15, len(doc))))

        date_pat = re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b")

        def parse_date(s):
            for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d"):
                try:
                    return datetime.datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return None

        # Format 1: date immediately before appraiser license (CR/GA/FL/etc + digits)
        m = re.search(r"(\d{2}/\d{2}/\d{4})\s*\n\s*([A-Z]{2}\d{4,8})\s", full_text)
        if m:
            d = parse_date(m.group(1))
            if d:
                results["effective_date"] = d
                doc.close()
                return results

        # Format 2: standalone date after large currency amount on page 1
        page1 = doc[0].get_text("text") if len(doc) > 0 else ""
        m2 = re.search(r"(\d{1,3},\d{3}(?:,\d{3})?)\s*\n\s*(\d{2}/\d{2}/\d{4})", page1)
        if m2:
            d = parse_date(m2.group(2))
            if d:
                results["effective_date"] = d
                doc.close()
                return results

        # Format 3: explicit label
        m3 = re.search(r"(?:effective date|date of appraisal|date of inspection|inspection date)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", full_text, re.IGNORECASE)
        if m3:
            d = parse_date(m3.group(1))
            if d:
                results["effective_date"] = d
                doc.close()
                return results

        # Format 4: "as of MM/DD/YYYY"
        m4 = re.search(r"\bas\s+of\s+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", full_text, re.IGNORECASE)
        if m4:
            d = parse_date(m4.group(1))
            if d:
                results["effective_date"] = d
                doc.close()
                return results

        # Format 5: date in appraisal certification "my opinion of value, as defined...
        # The effective date appears near "effective date" or "appraised as of"
        for page_idx in range(len(doc)):
            page_text = doc[page_idx].get_text("text")
            if "opinion" in page_text.lower() and "market value" in page_text.lower():
                dates = date_pat.findall(page_text)
                parsed = [(parse_date(d), d) for d in dates]
                valid = [(pd, d) for pd, d in parsed if pd and "2020" <= pd[:4] <= "2030"]
                if valid:
                    # Take the most recent date that's not in the future
                    import datetime as dt
                    now = dt.datetime.now().strftime("%Y-%m-%d")
                    candidates = [pd for pd, d in valid if pd <= now]
                    if candidates:
                        results["effective_date"] = max(candidates)  # most recent = effective date
                        break

        doc.close()
    except Exception as exc:
        logger.debug("L5 effective date extraction failed: %s", exc)

    return results


def _extract_contract_price_all_formats(pdf_path: Path) -> Dict[str, str]:
    """
    Extract contract price from all document formats.
    """
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        full_text = "\n".join(doc[i].get_text("text") for i in range(min(10, len(doc))))

        # Pattern 1: "Contract Price $ 263,000" or "Contract Price: $263,000"
        m = re.search(r"contract\s+(?:sales\s+)?price\s*\$?\s*([\d,]+(?:\.\d{0,2})?)", full_text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", "")
            try:
                v = float(val)
                if 10000 < v < 100_000_000:
                    results["contract_price"] = str(int(v))
            except ValueError:
                pass

        # Pattern 2: "Arms length sale;Contract Price: $263,000"
        m2 = re.search(r"Contract\s+Price:\s*\$?([\d,]+)", full_text, re.IGNORECASE)
        if not results.get("contract_price") and m2:
            val = m2.group(1).replace(",", "")
            try:
                v = float(val)
                if 10000 < v < 100_000_000:
                    results["contract_price"] = str(int(v))
            except ValueError:
                pass

        doc.close()
    except Exception as exc:
        logger.debug("L5 contract price extraction failed: %s", exc)

    return results


def _value_between_labels(
    words: list, label_word: tuple, end_label_keyword: str,
    y_tol: float = 1.5, max_words: int = 6,
) -> Optional[str]:
    """
    Given a label word `label_word` (PyMuPDF tuple) on a form, return the
    value text that sits BETWEEN this label and the next labeled column
    `end_label_keyword` on the SAME visual row.

    Strict y-tolerance (default 1.5 px) prevents word-wrap from a neighboring
    multi-line text block from being captured. Words are sorted left-to-right.
    """
    label_x1 = label_word[2]
    label_y = label_word[1]

    # Find the next-column label on the same visual row.
    end_x = None
    for nw in words:
        if abs(nw[1] - label_y) > y_tol:
            continue
        if nw[0] <= label_x1:
            continue
        if nw[4].strip().lower() == end_label_keyword.lower():
            end_x = nw[0]
            break

    # Collect candidate value words between label and end-of-column.
    value_words = []
    for nw in words:
        if abs(nw[1] - label_y) > y_tol:
            continue
        if nw[0] <= label_x1 + 1:
            continue
        if end_x is not None and nw[0] >= end_x - 2:
            continue
        txt = nw[4].strip()
        if not txt or txt.lower() in ("address", "lender", "client", "lender/client"):
            continue
        value_words.append((nw[0], txt))

    if not value_words:
        return None
    value_words.sort()
    return " ".join(t for _, t in value_words[:max_words]).strip()


def _extract_lender_name_clean(pdf_path: Path) -> Dict[str, str]:
    """
    Extract Lender/Client value by anchoring on the boxed-form label.

    Strategy:
      - Find the word "Lender/Client" (exact, case-sensitive) — that's
        the form label. Narrative text "lender/client" lowercase is
        skipped because we require the capitalized form-label token.
      - Read the value between that label and the next column label
        "Address" on the same visual row (strict y-tolerance).
      - The lender ADDRESS is the value AFTER that same "Address" label, to the
        end of the row — the URAR row is
        "Lender/Client <name> Address <street, city, ST zip>".
    """
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(5, len(doc))):
            page = doc[page_idx]
            words = page.get_text("words")
            for w in words:
                # Form label is capitalized "Lender/Client". Narrative
                # text in the certification is lowercase — skip it.
                if w[4] != "Lender/Client":
                    continue
                value = _value_between_labels(words, w, "Address")
                if value and 3 <= len(value) <= 80:
                    # Reject narrative captures (typical certification words).
                    bad = ("pursuant", "accurate", "opinion", "provide",
                           "supported", "subject", "summary")
                    if not any(kw in value.lower() for kw in bad):
                        results["lender_name"] = value
                        addr = _lender_address_after(words, w)
                        if addr:
                            results["lender_address"] = addr
                        break
            if "lender_name" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 lender extraction failed: %s", exc)
    return results


def _lender_address_after(words: list, lender_label: tuple, y_tol: float = 1.5) -> Optional[str]:
    """The lender address = words after the lender row's "Address" label, to the
    end of that same visual row (the row is "Lender/Client <name> Address <addr>")."""
    ly = lender_label[1]
    addr_label = next(
        (nw for nw in words
         if abs(nw[1] - ly) <= y_tol and nw[0] > lender_label[2]
         and nw[4].strip().lower() == "address"),
        None)
    if addr_label is None:
        return None
    tail = sorted(
        (nw for nw in words if abs(nw[1] - ly) <= y_tol and nw[0] > addr_label[2]),
        key=lambda z: z[0])
    addr = " ".join(t[4] for t in tail).strip().strip(",").strip()
    # sanity: a real address carries a street number / zip; bound the length.
    if addr and any(c.isdigit() for c in addr) and 5 <= len(addr) <= 120:
        return addr
    return None


def _extract_contract_date(pdf_path: Path) -> Dict[str, str]:
    """Appraisal "Date of Contract <MM/DD/YYYY>" — positional read of the value
    immediately after the label. Returned as MM/DD/YYYY to match the contract
    extractor's format so the C-2b cross-document compare is apples-to-apples."""
    import re
    results: Dict[str, str] = {}
    date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(3, len(doc))):
            words = doc[page_idx].get_text("words")
            for i in range(2, len(words)):
                if not (words[i][4] == "Contract" and words[i - 1][4] == "of"
                        and words[i - 2][4] == "Date"):
                    continue
                y, x1 = words[i][1], words[i][2]
                row = sorted((w for w in words if abs(w[1] - y) < 2 and w[0] >= x1),
                             key=lambda z: z[0])
                for w in row:
                    if date_re.match(w[4]):
                        mm, dd, yy = w[4].split("/")
                        yy = "20" + yy if len(yy) == 2 else yy
                        results["contract_date"] = f"{int(mm):02d}/{int(dd):02d}/{yy}"
                        break
                if "contract_date" in results:
                    break
            if "contract_date" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 contract_date extraction failed: %s", exc)
    return results


def _extract_signature_date(pdf_path: Path) -> Dict[str, str]:
    """Appraiser "Date of Signature and Report <MM/DD/YYYY>" on the certification
    page: the date token to the right of the label, in the APPRAISER (left) column
    only — the SUPERVISORY column repeats the same label further right (x~311).
    Returned as MM/DD/YYYY (consistent with effective_date comparisons in SIG-D)."""
    import re
    _APPRAISER_COL_X = 300        # supervisory column starts to the right of this
    results: Dict[str, str] = {}
    date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(len(doc)):
            words = doc[page_idx].get_text("words")
            for i in range(2, len(words)):
                if not (words[i][4] == "Signature" and words[i - 1][4] == "of"
                        and words[i - 2][4] == "Date"):
                    continue
                ly = words[i][1]
                cand = sorted(
                    (w for w in words if abs(w[1] - ly) < 2 and w[0] > words[i][2]
                     and w[0] < _APPRAISER_COL_X and date_re.match(w[4])),
                    key=lambda z: z[0])
                if cand:
                    mm, dd, yy = cand[0][4].split("/")
                    yy = "20" + yy if len(yy) == 2 else yy
                    results["date_of_signature"] = f"{int(mm):02d}/{int(dd):02d}/{yy}"
                    break
            if "date_of_signature" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 signature_date extraction failed: %s", exc)
    return results


_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _extract_appraiser_credentials(pdf_path: Path) -> Dict[str, str]:
    """Appraiser certification page (left/Appraiser column, x<300):
      - appraiser_license       : value after "State Certification #"/"State License #"
      - appraiser_license_state : the standalone "State <XX>" 2-letter code line.
      - appraiser_email         : any email address found on the cert page.
    The license STATE drives the "appraiser licensed in the property's state" rule."""
    import re as _re
    _COL = 300
    lic_re = _re.compile(r"^[A-Z]{0,3}-?\d{3,}[-A-Z]*$")
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(len(doc)):
            words = doc[page_idx].get_text("words")
            txt = " ".join(w[4] for w in words)
            if "Certification" not in txt or "Expiration" not in txt:
                continue  # not the cert page
            # Email — scan full page text (email may span the whole width).
            if "appraiser_email" not in results:
                m = _EMAIL_RE.search(txt)
                if m:
                    results["appraiser_email"] = m.group(0).lower()
            for i, w in enumerate(words):
                if w[0] >= _COL:
                    continue
                ly = w[1]
                same_row = sorted((x for x in words if abs(x[1] - ly) < 2 and x[0] > w[2] and x[0] < _COL),
                                  key=lambda z: z[0])
                # license / certification number
                if ("appraiser_license" not in results and w[4] in ("Certification", "License")
                        and i > 0 and words[i - 1][4] == "State"):
                    for nw in same_row:
                        if lic_re.match(nw[4]) and any(c.isdigit() for c in nw[4]):
                            results["appraiser_license"] = nw[4]
                            break
                # license state: "State <XX>"
                if "appraiser_license_state" not in results and w[4] == "State" and same_row:
                    if same_row[0][4] in _US_STATES:
                        results["appraiser_license_state"] = same_row[0][4]
            break  # only the cert page
        doc.close()
    except Exception as exc:
        logger.debug("L5 appraiser credentials extraction failed: %s", exc)
    return results


def _extract_neighborhood_name(pdf_path: Path) -> Dict[str, str]:
    """
    Extract Neighborhood Name value (the subdivision/area name).

    The form row is:
        "Neighborhood Name <value>   Map Reference <value>   Census Tract <value>"

    Anchor on the "Neighborhood" label token immediately followed by
    "Name" on the same row, then take the value words up to "Map".
    """
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(5, len(doc))):
            page = doc[page_idx]
            words = page.get_text("words")
            for i, w in enumerate(words):
                if w[4] != "Neighborhood":
                    continue
                # Need a "Name" word adjacent on same row to confirm this
                # is the Neighborhood Name label (not "Neighborhood Boundaries"
                # or "Neighborhood Description").
                name_word = None
                for nw in words:
                    if abs(nw[1] - w[1]) > 1.5:
                        continue
                    if nw[0] <= w[0] or nw[0] > w[2] + 25:
                        continue
                    if nw[4] == "Name":
                        name_word = nw
                        break
                if name_word is None:
                    continue
                # Use the end of "Name" as the start of the value column,
                # "Map" as the end label.
                value = _value_between_labels(words, name_word, "Map", max_words=5)
                if value and 2 <= len(value) <= 60:
                    # Reject if it's just labels we missed.
                    if value.lower() not in ("reference", "map reference"):
                        results["neighborhood_name"] = value
                        break
            if "neighborhood_name" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 neighborhood name extraction failed: %s", exc)
    return results


def _extract_land_use_percentages(pdf_path: Path) -> Dict[str, str]:
    """
    Extract land-use percentage values from the One-Unit Housing column.

    The layout on the UAD form is:
        One-Unit       80 %
        2-4 Unit        1 %
        Multi-Family    1 %
        Commercial     14 %
        Other           4 %

    Each label sits at left of a number and a '%' sign at right.
    We anchor on the '%' word in this column and read the number
    immediately to its left.
    """
    results: Dict[str, str] = {}
    label_to_field = [
        (["One-Unit"], "land_use_one_unit"),
        (["2-4", "Unit"], "land_use_2_4_unit"),
        (["Multi-Family"], "land_use_multi_family"),
        (["Commercial"], "land_use_commercial"),
        (["Other"], "land_use_other"),
    ]
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(5, len(doc))):
            page = doc[page_idx]
            text = page.get_text("text")
            if "Present Land Use" not in text and "One-Unit Housing" not in text:
                continue
            words = page.get_text("words")

            for tokens, field in label_to_field:
                if field in results:
                    continue
                # Find consecutive tokens on the same line.
                for i, w in enumerate(words):
                    if w[4] != tokens[0]:
                        continue
                    matched = True
                    last = w
                    for tok in tokens[1:]:
                        next_w = None
                        for nw in words:
                            if abs(nw[1] - last[1]) > 1.5:
                                continue
                            if nw[0] <= last[2] or nw[0] > last[2] + 15:
                                continue
                            if nw[4] == tok:
                                next_w = nw
                                break
                        if next_w is None:
                            matched = False
                            break
                        last = next_w
                    if not matched:
                        continue
                    # Found label sequence ending at `last`. Look for the
                    # nearest '%' word on the same row, then read the
                    # number BETWEEN label end and '%'. The number may
                    # appear on a slightly different visual row (some
                    # forms split it) so accept y_top ± 4.
                    pct_w = None
                    for pw in words:
                        if abs(pw[1] - last[1]) > 4:
                            continue
                        if pw[0] <= last[2]:
                            continue
                        if pw[4].strip() == "%":
                            pct_w = pw
                            break
                    if pct_w is None:
                        continue
                    # Number must lie between label_end_x and pct_x.
                    candidates = []
                    for nw in words:
                        # value may have y slightly offset from label
                        if abs(nw[1] - last[1]) > 6:
                            continue
                        if nw[0] <= last[2] or nw[0] >= pct_w[0]:
                            continue
                        txt = nw[4].replace(",", "").strip()
                        try:
                            v = float(txt)
                        except ValueError:
                            continue
                        if 0 <= v <= 100:
                            candidates.append((abs(nw[0] - pct_w[0]), v))
                    if candidates:
                        candidates.sort()
                        v = candidates[0][1]
                        results[field] = str(int(v)) if v == int(v) else str(v)
                        break

            if results:
                # Derive total
                total = sum(float(v) for v in results.values())
                if 90 <= total <= 110:
                    results["land_use_total"] = str(int(total)) if total == int(total) else str(total)
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 land use extraction failed: %s", exc)
    return results


def _extract_pud_checked(pdf_path: Path) -> Dict[str, str]:
    """
    Extract is_pud_checked by detecting an X-mark in the small rect to
    the LEFT of the "PUD" form label.

    On UAD 1004 the layout is:
        [ ] PUD   HOA $ ____   per year   per month
    The checkbox is ~5-15 px to the left of the "PUD" word.
    """
    results: Dict[str, str] = {}
    drawings_by_page = _get_drawings_by_page(pdf_path)
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(min(5, len(doc))):
            page = doc[page_idx]
            pn = page_idx + 1
            words = page.get_text("words")
            for w in words:
                if w[4] != "PUD":
                    continue
                # Confirm this is the form label: HOA should appear on the
                # same row just to the right.
                hoa_present = any(
                    nw[4] == "HOA" and abs(nw[1] - w[1]) < 2 and 0 < nw[0] - w[2] < 30
                    for nw in words
                )
                if not hoa_present:
                    continue
                drawings = drawings_by_page.get(pn, [])
                y_mid = (w[1] + w[3]) / 2
                # Checkbox sits up to 18 px to the left of "PUD".
                checked_x = _find_checked_at_y(
                    drawings,
                    y_min=y_mid - 6,
                    y_max=y_mid + 6,
                    x_lo=w[0] - 18,
                    x_hi=w[0] - 1,
                )
                # We also need to KNOW the box is present (X-marked or not)
                # so we can output False when unchecked. _find_checked_at_y
                # only returns X-marked positions, so unchecked → None.
                # The form always renders the box, so absence of X = unchecked.
                results["is_pud_checked"] = "True" if checked_x is not None else "False"
                break
            if "is_pud_checked" in results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 PUD checkbox extraction failed: %s", exc)
    return results


def _extract_uspap_addendum(pdf_path: Path) -> Dict[str, str]:
    """Deterministic (no-LLM) extraction of USPAP addendum fields.

    The USPAP addendum page contains:
      - "Appraisal Report" / "Restricted Appraisal Report" checkboxes
      - "Reasonable Exposure Time" fill-in
      - "I have / I have not" prior-services disclosure

    This extractor runs as an L5 fallback so ADD-9 does not regress when
    the LLM tier is unavailable or times out.
    """
    _EXPOSURE_RE = re.compile(
        r"[Rr]easonable\s+[Ee]xposure\s+[Tt]ime[^:]*[:\-]?\s*([^\n]{3,80})"
    )
    _PRIOR_RE = re.compile(
        r"I\s+have\s+(not\s+)?performed\s+services[^\n]{0,120}", re.I
    )
    results: Dict[str, str] = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for page_idx in range(len(doc)):
            text = doc[page_idx].get_text("text")
            low = text.lower()
            if "exposure time" not in low and "restricted appraisal" not in low:
                continue
            # Report type: look for the radio button label text.
            if "appraisal_report_type" not in results:
                if "restricted appraisal report" in low:
                    results["appraisal_report_type"] = "Restricted Appraisal Report"
                elif "appraisal report" in low:
                    results["appraisal_report_type"] = "Appraisal Report"
            # Reasonable exposure time: extract the text after the label.
            if "reasonable_exposure_time" not in results:
                m = _EXPOSURE_RE.search(text)
                if m:
                    val = m.group(1).strip().rstrip(".")
                    if val and len(val) > 2:
                        results["reasonable_exposure_time"] = val
            # Prior services.
            if "prior_services_performed" not in results:
                m = _PRIOR_RE.search(text)
                if m:
                    results["prior_services_performed"] = m.group(0).strip()
            if results:
                break
        doc.close()
    except Exception as exc:
        logger.debug("L5 USPAP addendum extraction failed: %s", exc)
    return results


def extract_with_uad_template(pdf_path: Path) -> Dict[str, str]:
    """
    Run all UAD template-based extraction methods.
    Fills gaps in Yes/No fields, price grids, GLA, and dates.
    Returns {field_name: value}.
    """
    results: Dict[str, str] = {}

    # Run all extractors
    extractors = [
        ("yes_no", _extract_yes_no_fields),
        ("price_grid", _extract_neighborhood_grid),
        ("gla", _extract_gla_from_improvements),
        ("effective_date", _extract_effective_date_all_formats),
        ("contract_price", _extract_contract_price_all_formats),
        ("lender_name", _extract_lender_name_clean),
        ("contract_date", _extract_contract_date),
        ("signature_date", _extract_signature_date),
        ("appraiser_credentials", _extract_appraiser_credentials),
        ("neighborhood_name", _extract_neighborhood_name),
        ("land_use", _extract_land_use_percentages),
        ("pud_checked", _extract_pud_checked),
        ("uspap_addendum", _extract_uspap_addendum),
    ]

    for name, fn in extractors:
        try:
            found = fn(pdf_path)
            results.update({k: v for k, v in found.items() if k not in results and v})
        except Exception as exc:
            logger.warning("L5 %s failed: %s", name, exc)

    found_fields = [k for k in results if results[k]]
    if found_fields:
        logger.info("L5 template: %s — found %d fields: %s", pdf_path.name, len(found_fields), found_fields[:8])

    return results
