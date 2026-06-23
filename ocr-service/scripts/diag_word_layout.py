"""Diagnostic — dump word neighborhood for price/age + lender + PUD fields.

Run from ocr-service/ root. Prints word lists for the regions of interest
on a single PDF so we can see exactly what the layout produces.
"""

from __future__ import annotations

import sys
from pathlib import Path


def dump_neighborhood_words(pdf: Path, max_pages: int = 4) -> None:
    import fitz
    doc = fitz.open(str(pdf))
    print(f"== {pdf.name} == {len(doc)} pages")
    for pi in range(min(max_pages, len(doc))):
        page = doc[pi]
        text = page.get_text("text")
        if "PRICE" not in text and "Predominant" not in text and "Neighborhood" not in text:
            continue
        print(f"\n-- page {pi+1} (has neighborhood section) --")
        words = page.get_text("words")
        # find y-band that contains 'PRICE' or 'AGE' or 'Predominant'
        anchors_y = []
        for w in words:
            t = w[4].strip()
            if t.upper() in ("PRICE", "AGE", "PREDOMINANT", "PRED.", "LOW", "HIGH"):
                anchors_y.append((w[1], t, w[0], w[2]))
        if not anchors_y:
            continue
        ymin = min(y for y, *_ in anchors_y) - 5
        ymax = max(y for y, *_ in anchors_y) + 50
        print(f"   y range: {ymin:.0f} .. {ymax:.0f}")
        band = [w for w in words if ymin <= w[1] <= ymax]
        band.sort(key=lambda w: (round(w[1]/3)*3, w[0]))
        # group by row (y bucket of 3 px)
        current_row = None
        line_buf = []
        for w in band:
            row_id = round(w[1] / 3) * 3
            if row_id != current_row:
                if line_buf:
                    print(f"   y={current_row:>5.0f}: {line_buf}")
                line_buf = []
                current_row = row_id
            line_buf.append(f"({w[0]:.0f}){w[4]}")
        if line_buf:
            print(f"   y={current_row:>5.0f}: {line_buf}")
        break
    doc.close()


def dump_lender_words(pdf: Path) -> None:
    import fitz
    doc = fitz.open(str(pdf))
    print(f"\n== LENDER context in {pdf.name} ==")
    for pi in range(min(3, len(doc))):
        page = doc[pi]
        words = page.get_text("words")
        for w in words:
            if "lender" in w[4].lower() or "client" in w[4].lower():
                # dump the y-band ±15 px
                ymin, ymax = w[1] - 5, w[1] + 30
                band = [bw for bw in words if ymin <= bw[1] <= ymax]
                band.sort(key=lambda bw: (round(bw[1]/3)*3, bw[0]))
                print(f"  p{pi+1} anchor '{w[4]}' at y={w[1]:.0f}:")
                current_row = None
                line_buf = []
                for bw in band:
                    row_id = round(bw[1] / 3) * 3
                    if row_id != current_row:
                        if line_buf:
                            print(f"     y={current_row:>5.0f}: {line_buf}")
                        line_buf = []
                        current_row = row_id
                    line_buf.append(f"({bw[0]:.0f}){bw[4]}")
                if line_buf:
                    print(f"     y={current_row:>5.0f}: {line_buf}")
                print()
                break
    doc.close()


def dump_pud_words(pdf: Path) -> None:
    import fitz
    doc = fitz.open(str(pdf))
    print(f"\n== PUD context in {pdf.name} ==")
    found = False
    for pi in range(len(doc)):
        page = doc[pi]
        words = page.get_text("words")
        for w in words:
            if w[4].strip().upper() in ("PUD", "HOA", "PUD)"):
                found = True
                ymin, ymax = w[1] - 5, w[1] + 25
                band = [bw for bw in words if ymin <= bw[1] <= ymax]
                band.sort(key=lambda bw: (round(bw[1]/3)*3, bw[0]))
                print(f"  p{pi+1} anchor '{w[4]}' at y={w[1]:.0f}:")
                line_buf = []
                current_row = None
                for bw in band:
                    row_id = round(bw[1] / 3) * 3
                    if row_id != current_row:
                        if line_buf:
                            print(f"     y={current_row:>5.0f}: {line_buf}")
                        line_buf = []
                        current_row = row_id
                    line_buf.append(f"({bw[0]:.0f}){bw[4]}")
                if line_buf:
                    print(f"     y={current_row:>5.0f}: {line_buf}")
                break
        if found:
            break
    doc.close()


if __name__ == "__main__":
    pdfs = [
        Path("/Users/eaglexmac/Documents/functionalProject/shal/shal/SHAL/uploads/EQSS/8234X 2/appraisal/8234 E Pearson.pdf"),
        Path("/Users/eaglexmac/Documents/functionalProject/shal/shal/SHAL/uploads/AERS/MSL/appraisal/96 Baell Trace Ct SE.pdf"),
    ]
    for p in pdfs:
        if not p.exists():
            print(f"MISSING: {p}")
            continue
        dump_neighborhood_words(p)
        dump_lender_words(p)
        dump_pud_words(p)
        print("\n" + "=" * 80)
