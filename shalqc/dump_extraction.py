"""Dump EVERY extracted field (value + source + confidence + page) for one
order's appraisal and engagement to a readable txt file. No LLM.

Usage:  PYTHONPATH=. python dump_extraction.py ESTX-0007568
"""
import sys, os, glob, time, logging
logging.basicConfig(level=logging.ERROR)

from app.extraction.merge import run_extraction
from app.extraction.engagement import extract_engagement


def find_order(order_arg):
    base = f"testfiles/{order_arg}"
    if not os.path.isdir(base):
        base = next((c for c in glob.glob(f"testfiles/{order_arg}*") if os.path.isdir(c)), None)
    if not base:
        sys.exit(f"order not found: {order_arg}")
    pdf = next(iter(glob.glob(f"{base}/appraisal/*.pdf")), None)
    xml = next(iter(glob.glob(f"{base}/appraisal/*.xml")), None)
    eng = next(iter(glob.glob(f"{base}/engagement/*.pdf")), None)
    return base, pdf, xml, eng


def _rows(fieldset, only_found=True):
    fields = fieldset.found_fields() if only_found else fieldset.all_fields()
    return sorted(fields, key=lambda f: f.canonical_name)


def _write_section(fh, title, fieldset):
    found = fieldset.found_fields()
    allf = fieldset.all_fields()
    fh.write("=" * 78 + "\n")
    fh.write(f"{title}   ({len(found)} found / {len(allf)} total fields)\n")
    fh.write("=" * 78 + "\n")
    name_w = max((len(f.canonical_name) for f in found), default=20)
    for f in _rows(fieldset):
        val = (f.value or "").replace("\n", " ⏎ ")
        fh.write(f"{f.canonical_name.ljust(name_w)} = {val}\n")
        fh.write(f"{' ' * name_w}   [source={f.source} conf={f.confidence:.2f} page={f.page}]\n")
        if f.conflicts:
            for c in f.conflicts:
                fh.write(f"{' ' * name_w}   (conflict: {c.source}={c.value} conf={c.confidence:.2f})\n")
    fh.write("\n")


def main():
    order = sys.argv[1] if len(sys.argv) > 1 else "ESTX-0007568"
    base, pdf, xml, eng = find_order(order)
    name = os.path.basename(base)

    appraisal = run_extraction(appraisal_pdf=pdf, xml_path=xml, engagement_letter=None)
    engagement = extract_engagement(eng) if eng else None

    outdir = "extraction_dumps"
    os.makedirs(outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = f"{outdir}/{name}_{stamp}_extracted.txt"

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"EXTRACTED VALUES — {name}\n")
        fh.write(f"appraisal pdf: {os.path.basename(pdf) if pdf else '-'}\n")
        fh.write(f"appraisal xml: {os.path.basename(xml) if xml else '-'}\n")
        fh.write(f"engagement   : {os.path.basename(eng) if eng else '-'}\n\n")
        _write_section(fh, "APPRAISAL (XML + PDF fused)", appraisal)
        if engagement is not None:
            _write_section(fh, "ENGAGEMENT LETTER", engagement)

        # source breakdown so you can see what came from the XML specifically
        from collections import Counter
        src = Counter(f.source for f in appraisal.found_fields())
        fh.write("APPRAISAL source breakdown (found fields):\n")
        for s, n in src.most_common():
            fh.write(f"  {s}: {n}\n")

    ap_found = len(appraisal.found_fields())
    en_found = len(engagement.found_fields()) if engagement else 0
    print(f"APPRAISAL found: {ap_found}   ENGAGEMENT found: {en_found}")
    print(f"FILE: {out}")


if __name__ == "__main__":
    main()
