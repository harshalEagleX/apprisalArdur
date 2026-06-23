"""
Per-document, per-field explanation of why critical fields were not extracted.

For each PDF in the test corpus and each critical field, this script reports
either ``OK`` with the extracted value, or a structured reason for the miss:

  * SCANNED_NO_TEXT        — page has no embedded text and PaddleOCR output
                             is not wired into the field extractors (the
                             scanned-doc gap identified in the impl-plan
                             reconciliation, item 2).
  * ANCHOR_NOT_FOUND <kw>  — the keyword(s) the L5 extractor anchors on did
                             not appear on any page.
  * VALUE_OUT_OF_RANGE     — an anchor was found, candidate words exist, but
                             every candidate failed the field's sanity range.
  * EMPTY_VALUE_AFTER_LABEL — the form label is present but the column to its
                             right is blank or contains only labels.
  * NO_PDF_TEXT            — extract_text() returned nothing on every page.
  * CRASHED <repr>         — the extractor raised; bug to fix.

Run from ocr-service/:
    conda run -n shal python scripts/explain_misses.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))


UPLOADS = Path("/Users/eaglexmac/Documents/functionalProject/shal/shal/SHAL/uploads")

# Same 23 PDFs as run_full_appraisal_test.py
TEST_DOCS: List[str] = [
    "AERS/MSL/appraisal/96 Baell Trace Ct SE.pdf",
    "AERS/#2321525427/appraisal/1718 Theon St.pdf",
    "AERS/#2321525505/appraisal/28203 Fantail Dr.pdf",
    "EQSS/8234X 2/appraisal/8234 E Pearson.pdf",
    "sort/#2321525530/appraisal/1218 E Alpine Dr.pdf",
    "sort/#2321525470/appraisal/90 NE 32nd St Unit 524.pdf",
    "Orders/ESCA-0018896/2026050137.pdf",
    "Orders/ESFL-0026229/5425172A.pdf",
    "EQSS/TestX121/appraisal/2307 Merrily Cir N.pdf",
    "Orders/ESCA-0018495/8527 Elaine Dr.pdf",
    "Orders/ESFL-0026435/117 Washington Ave.pdf",
    "Orders/ESFL-0026323/1640 Peninsula Dr.pdf",
    "Orders/ESFL-0026493/05018713.pdf",
    "Orders/ESFL-0026537/106 Lantern Ln(1).pdf",
    "Orders/ESFL-0026548/2195 SW 15th Pl.pdf",
    "Orders/ESIA-0000604/10-E-13th (1).pdf",
    "Orders/ESMI-0044877/7433 S M 43 Hwy.pdf",
    "Orders/ESMI-0045719/3090 Lafayette Dr.pdf",
    "Orders/ESMN-0001616/26135.pdf",
    "Orders/ESMO-0001188/O051201.pdf",
    "Orders/ESMI-0045238/802 Munson Ave.pdf",
    "Orders/ESMI-0045495/3022 Academy St.pdf",
    "Orders/ESMS-0001111/1574 Church Rd W.pdf",
]


# ----------------------------------------------------------------------------
# Per-field probes — each returns (value_or_None, reason_str)
# ----------------------------------------------------------------------------

def _has_any_embedded_text(pdf_path: Path) -> bool:
    """Quick check: does any of the first 8 pages have non-trivial text?"""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        try:
            for i in range(min(8, len(doc))):
                if len((doc[i].get_text("text") or "").strip()) > 50:
                    return True
            return False
        finally:
            doc.close()
    except Exception:
        return False


def _find_keyword_on_any_page(pdf_path: Path, keywords: List[str], max_pages: int = 8) -> bool:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        try:
            for i in range(min(max_pages, len(doc))):
                text = doc[i].get_text("text") or ""
                if all(kw.lower() in text.lower() for kw in keywords):
                    return True
            return False
        finally:
            doc.close()
    except Exception:
        return False


def probe_price_grid(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_neighborhood_grid
    try:
        r = _extract_neighborhood_grid(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "price_low" in r:
        return r["price_low"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["Low"]) and not _find_keyword_on_any_page(pdf_path, ["High"]):
        return None, "ANCHOR_NOT_FOUND Low/High/Pred."
    return None, "EMPTY_VALUE_AFTER_LABEL (anchor found but no plausible number to its left)"


def probe_lender(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_lender_name_clean
    try:
        r = _extract_lender_name_clean(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "lender_name" in r:
        return r["lender_name"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["Lender/Client"]):
        return None, "ANCHOR_NOT_FOUND 'Lender/Client'"
    return None, "EMPTY_VALUE_AFTER_LABEL (label present, value column blank or only narrative)"


def probe_neighborhood_name(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_neighborhood_name
    try:
        r = _extract_neighborhood_name(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "neighborhood_name" in r:
        return r["neighborhood_name"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["Neighborhood", "Name"]):
        return None, "ANCHOR_NOT_FOUND 'Neighborhood Name'"
    return None, "EMPTY_VALUE_AFTER_LABEL"


def probe_gla(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_gla_from_improvements
    try:
        r = _extract_gla_from_improvements(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "gla" in r:
        return r["gla"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["Gross Living Area"]):
        return None, "ANCHOR_NOT_FOUND 'Gross Living Area'"
    return None, "VALUE_OUT_OF_RANGE or no numeric word adjacent to label"


def probe_pud(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_pud_checked
    try:
        r = _extract_pud_checked(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "is_pud_checked" in r:
        return r["is_pud_checked"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["PUD"]):
        return None, "ANCHOR_NOT_FOUND 'PUD' (form may not have PUD row, or label garbled by OCR)"
    return None, "ANCHOR_FOUND_BUT_NO_HOA_NEIGHBOR (PUD found but HOA not on same row — mismatched template)"


def probe_land_use_one_unit(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_land_use_percentages
    try:
        r = _extract_land_use_percentages(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "land_use_one_unit" in r:
        return r["land_use_one_unit"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["One-Unit"]):
        return None, "ANCHOR_NOT_FOUND 'One-Unit'"
    return None, "EMPTY_VALUE_AFTER_LABEL"


def probe_effective_date(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_effective_date_all_formats
    try:
        r = _extract_effective_date_all_formats(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "effective_date" in r:
        return r["effective_date"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    return None, "NO_DATE_PATTERN_MATCHED (none of the 5 date-extraction formats hit)"


def probe_contract_price(pdf_path: Path) -> Tuple[Optional[str], str]:
    from app.extraction.layers.l5_uad_template import _extract_contract_price_all_formats
    try:
        r = _extract_contract_price_all_formats(pdf_path)
    except Exception as exc:
        return None, f"CRASHED {exc!r}"
    if "contract_price" in r:
        return r["contract_price"], "OK"
    if not _has_any_embedded_text(pdf_path):
        return None, "SCANNED_NO_TEXT"
    if not _find_keyword_on_any_page(pdf_path, ["Contract", "Price"]):
        return None, "ANCHOR_NOT_FOUND 'Contract Price' (likely a refinance, no contract price field)"
    return None, "VALUE_OUT_OF_RANGE (no $X amount between $10k and $100M near label)"


CRITICAL_FIELDS: List[Tuple[str, Callable[[Path], Tuple[Optional[str], str]]]] = [
    ("price_low/high/pred", probe_price_grid),
    ("lender_name",         probe_lender),
    ("neighborhood_name",   probe_neighborhood_name),
    ("gla",                 probe_gla),
    ("is_pud_checked",      probe_pud),
    ("land_use_one_unit",   probe_land_use_one_unit),
    ("effective_date",      probe_effective_date),
    ("contract_price",      probe_contract_price),
]


def main() -> int:
    miss_counts: Dict[str, Dict[str, int]] = {f: {} for f, _ in CRITICAL_FIELDS}
    total_misses_per_doc: Dict[str, int] = {}

    print("=" * 100)
    print("WHY-MISSED REPORT — per document, per critical field")
    print("=" * 100)

    for rel in TEST_DOCS:
        p = UPLOADS / rel
        if not p.exists():
            print(f"MISSING: {rel}")
            continue
        scanned = not _has_any_embedded_text(p)
        marker = " [SCANNED]" if scanned else ""
        print(f"\n-- {rel}{marker} --")
        misses = 0
        for field, probe in CRITICAL_FIELDS:
            value, reason = probe(p)
            if reason == "OK":
                print(f"  {field:24s} OK  {value!s:.60s}")
            else:
                print(f"  {field:24s} MISS {reason}")
                miss_counts[field][reason] = miss_counts[field].get(reason, 0) + 1
                misses += 1
        total_misses_per_doc[rel] = misses

    print("\n" + "=" * 100)
    print("MISS REASON SUMMARY (across 23 docs)")
    print("=" * 100)
    for field, reasons in miss_counts.items():
        if not reasons:
            print(f"  {field:24s}  all 23 docs OK")
            continue
        ranked = sorted(reasons.items(), key=lambda kv: -kv[1])
        print(f"  {field:24s}")
        for reason, count in ranked:
            print(f"      {count:3d} x  {reason}")

    print("\n" + "=" * 100)
    print("DOCS WITH MOST MISSES")
    print("=" * 100)
    for rel, count in sorted(total_misses_per_doc.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {count} misses : {rel}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
