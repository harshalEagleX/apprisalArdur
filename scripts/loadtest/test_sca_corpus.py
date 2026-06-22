#!/usr/bin/env python3
"""
Test (zero Groq): for 4 different appraisals report
  (A) deterministic SCA comp handling — how many comps, across how many grid pages,
      numbered sequentially (no cap on the deterministic path);
  (B) Fix 1 — form gap-fill LLM call count OFF vs ON, and how many times page-1
      (Subject+Neighborhood) text is sent (should drop 2 -> 1).
LLM is stubbed (returns {}), so the SCA *LLM* comp numbers can't be checked here
(that needs real Groq) — but the deterministic comp numbering and Fix 1 call/dedup
behaviour are fully exercised.
"""
from pathlib import Path

DOCS = [
    ("standard-1718Theon",  "uploads/sort/#2321525427/appraisal/1718 Theon St.pdf"),
    ("condo-cover-90NE32",  "uploads/sort/#2321525470/appraisal/90 NE 32nd St Unit 524.pdf"),
    ("standard-fantail",    "uploads/DEMO/fantail_batch/appraisal/28203 Fantail Dr.pdf"),
    ("standard-neeley",     "uploads/sort/#2321525499/appraisal/191 Neeley Pl.pdf"),
]


def det_comps(pdf):
    import pdfplumber
    from app.extraction.comp_grid_extractor import extract_comp_grid, _find_grid_pages
    grid, _pos = extract_comp_grid(pdf)
    comps = set()
    for k in grid:
        if k.startswith("comp_"):
            try:
                comps.add(int(k.split("_")[1]))
            except Exception:
                pass
    with pdfplumber.open(pdf) as p:
        gp = _find_grid_pages(p)
    return (max(comps) if comps else 0, sorted(comps), len(gp))


def run_count(pdf, batch):
    import app.extraction.llm_groq as g
    from app import config
    from app.qc.transaction import run_transaction_qc_paths
    config.FORM_LLM_BATCH = batch
    st = {"n": 0, "p1": 0}

    def rec(messages, **kw):
        st["n"] += 1
        blob = " ".join(m.get("content", "") for m in messages)
        if "Owner of Public Record" in blob:
            st["p1"] += 1
        return {}

    g.chat_json = rec
    g.vision_chat_json = lambda *a, **k: {}
    run_transaction_qc_paths(Path(pdf), None, None, transaction_id="t", persist=False)
    return st["n"], st["p1"]


def main():
    print(f"{'doc':22} {'det_comps':10} {'grid_pgs':8} {'calls_off':9} {'calls_on':8} {'pg1_off':7} {'pg1_on':6}")
    print("-" * 78)
    for label, pdf in DOCS:
        mx, comps, gp = det_comps(pdf)
        off_n, off_p1 = run_count(pdf, False)
        on_n, on_p1 = run_count(pdf, True)
        print(f"{label:22} {('max'+str(mx)):10} {gp:8} {off_n:9} {on_n:8} {off_p1:7} {on_p1:6}")
    print("\nReading:")
    print("  det_comps = highest comp index the DETERMINISTIC reader numbered (no cap; counts across pages)")
    print("  pg1_off=2 -> pg1_on=1 confirms Fix 1 dedup; calls_on < calls_off confirms the co-page merge")


if __name__ == "__main__":
    main()
