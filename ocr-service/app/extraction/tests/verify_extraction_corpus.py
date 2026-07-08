"""
Full-pipeline extraction harness (manual / on-demand, not a pytest test).

Runs the three document extractors over every case in ocr-service/exttestfile and
writes a JSON report of exactly what each produced — the measurement artifact
called for by P-8. Unlike test_extraction_regression.py (which pins the fast,
dependency-free XML + engagement paths), this also drives the heavy PDF
orchestrator (Camelot/pdfplumber/spatial), so it needs the full extraction deps
installed and is meant to be run by hand when validating a change end-to-end.

The contract file is deliberately never read.

Usage:
    cd ocr-service && PYTHONPATH=. python app/extraction/tests/verify_extraction_corpus.py
"""
import json
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve()
_OCR_SERVICE = _HERE.parents[3]
_TESTFILES = _OCR_SERVICE / "exttestfile"
sys.path.insert(0, str(_OCR_SERVICE))


def _rs_to_dict(rs) -> dict:
    out = {}
    for canonical, result in rs:
        if getattr(result, "found", False):
            out[canonical] = {
                "value": result.value,
                "method": str(result.extraction_method),
                "conf": round(getattr(result, "effective_confidence", result.confidence), 3),
                "page": result.source_page,
            }
    return out


def _run_one(label, fn) -> dict:
    try:
        d = _rs_to_dict(fn())
        print(f"    {label}: {len(d)} fields")
        return {"ok": True, "count": len(d), "fields": d}
    except Exception as exc:  # each extractor isolated — one failure never blocks others (P-6)
        print(f"    {label}: ERROR {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _appraisal_pdf(case: Path):
    d = case / "apprisal"
    pdfs = sorted(d.glob("*.pdf")) if d.exists() else []
    return pdfs[0] if pdfs else None


def _appraisal_xml(case: Path):
    d = case / "apprisal"
    xmls = sorted(list(d.glob("*.xml")) + list(d.glob("*.XML"))) if d.exists() else []
    return xmls[0] if xmls else None


def _engagement_pdf(case: Path):
    d = case / "engagement"
    pdfs = [p for p in sorted(d.glob("*.pdf")) if "engagement" in p.name.lower()] if d.exists() else []
    return pdfs[0] if pdfs else None


def main() -> int:
    if not _TESTFILES.exists():
        print(f"No corpus at {_TESTFILES} — nothing to verify.")
        return 1
    from app.extraction.layers.orchestrator import run_full_extraction
    from app.extraction.xml_extractor import extract_xml
    from app.extraction.engagement_extractor import extract_engagement

    report = {}
    for case in sorted(d for d in _TESTFILES.iterdir() if d.is_dir()):
        print(f"\n=== {case.name} ===")
        pdf, xml, eng = _appraisal_pdf(case), _appraisal_xml(case), _engagement_pdf(case)
        entry = {}
        if pdf:
            entry["pdf"] = _run_one(f"PDF  {pdf.name}",
                                    lambda p=pdf: run_full_extraction(p, "appraisal_report", use_paddle=False))
        if xml:
            entry["xml"] = _run_one(f"XML  {xml.name}", lambda p=xml: extract_xml(p))
        if eng:
            entry["engagement"] = _run_one(f"ENG  {eng.name}",
                                           lambda p=eng: extract_engagement(p, "engagement_letter"))
        report[case.name] = entry

    out = _HERE.parent / "extraction_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
