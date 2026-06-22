#!/usr/bin/env python3
"""
Measure how often the DETERMINISTIC SCA currency reader (Camelot lattice) succeeds
across the appraisal corpus. ZERO Groq calls — Camelot is local.

For each unique appraisal PDF: run extract_sca_grid (Camelot) and report parsing
accuracy + how many comp currency fields it produced. Classify whether the doc
would SKIP the SCA-LLM under confidence-gating (clean lattice) or still NEED it.

Run (project root): PYTHONPATH=ocr-service python3 scripts/loadtest/measure_camelot_success.py
"""
import glob
import hashlib
import sys
from pathlib import Path


def _sha(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def analyze(pdf):
    from app.extraction.sca_grid_matrix import extract_sca_grid
    try:
        cam = extract_sca_grid(pdf)
    except Exception as e:
        return ("RAISED", 0.0, 0, 0, type(e).__name__)
    acc = cam.pop("_sca_grid_accuracy", None)
    try:
        acc = float(acc) if acc is not None else 0.0
    except Exception:
        acc = 0.0
    if not cam:
        return ("EMPTY", acc, 0, 0, "no cells / not lattice")
    sp = sum(1 for k in cam if k.startswith("comp_") and k.endswith("_sale_price"))
    adj = sum(1 for k in cam if k.startswith("comp_") and k.endswith("_adjustment"))
    return ("OK", acc, sp, adj, "")


def main():
    pats = sys.argv[1:] or glob.glob("uploads/**/appraisal/*.pdf", recursive=True)
    # de-dup identical PDFs by content hash
    uniq = {}
    for p in sorted(pats):
        try:
            uniq.setdefault(_sha(p), p)
        except Exception:
            pass
    docs = list(uniq.values())
    print(f"Unique appraisal PDFs: {len(docs)} (from {len(pats)} files)\n")
    hdr = f"{'doc':40} {'status':7} {'acc':>5} {'sale_px':>7} {'adj':>4} {'verdict':>10}"
    print(hdr); print("-" * len(hdr))
    clean = 0
    for p in docs:
        status, acc, sp, adj, note = analyze(p)
        # "clean" = Camelot read the lattice well AND got the comp sale prices
        is_clean = status == "OK" and acc >= 90 and sp >= 3
        clean += is_clean
        verdict = "SKIP-LLM" if is_clean else "NEEDS-LLM"
        name = Path(p).name[:39]
        print(f"{name:40} {status:7} {acc:5.0f} {sp:7} {adj:4} {verdict:>10}  {note}")
    n = len(docs) or 1
    print("\n=== SUMMARY ===")
    print(f"  clean lattice (would SKIP the SCA-LLM): {clean}/{n} = {clean/n*100:.0f}%")
    print(f"  needs LLM (Camelot failed/low/partial) : {n-clean}/{n} = {(n-clean)/n*100:.0f}%")
    print("\n  Reading: 'SKIP-LLM %' ≈ the docs where confidence-gating would avoid the SCA-LLM")
    print("  call entirely (accuracy-safe). The rest genuinely need the LLM repair today.")


if __name__ == "__main__":
    main()
