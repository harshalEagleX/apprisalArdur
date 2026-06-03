"""
Run the QC rule engine across every transaction folder and report aggregate results.

A transaction folder is any directory under uploads/ that contains an
`appraisal/` subfolder (with engagement/ and/or contract/ alongside). For each,
this extracts the documents, runs the full rule engine, persists the QC report
to adaptive_validation_results, and prints a per-transaction + aggregate summary.

Usage:
    cd ocr-service
    conda run -n apprisal python scripts/run_qc_corpus.py [--limit N]
"""

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.disable(logging.WARNING)

from app.qc.result import RuleStatus
from app.qc.transaction import run_transaction_qc

UPLOADS = Path(__file__).parent.parent.parent / "uploads"


def find_transactions() -> list:
    seen, txns = set(), []
    for appr in sorted(UPLOADS.rglob("appraisal")):
        if not appr.is_dir() or not list(appr.glob("*.pdf")):
            continue
        folder = appr.parent
        key = str(folder)
        if key in seen:
            continue
        seen.add(key)
        txns.append(folder)
    return txns


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    txns = find_transactions()
    if limit:
        txns = txns[:limit]

    print(f"QC CORPUS RUN — {len(txns)} transactions\n" + "=" * 78)
    agg = Counter()
    overalls = Counter()
    finding_counter = Counter()
    t0 = time.time()

    for folder in txns:
        tid = str(folder).split("uploads/")[-1]
        try:
            rep = run_transaction_qc(folder, persist=True)
        except Exception as exc:
            print(f"  ✗ {tid[:46]:46} ERROR: {str(exc)[:40]}")
            continue
        c = rep.counts()
        for k, v in c.items():
            agg[k] += v
        overalls[rep.overall.value] += 1
        for r in rep.results:
            if r.status in (RuleStatus.FAIL, RuleStatus.HOLD, RuleStatus.VERIFY):
                finding_counter[r.rule_id] += 1
        flag = {"PASS": "✓", "VERIFY": "?", "FAIL": "✗", "HOLD": "!"}.get(rep.overall.value, "·")
        print(f"  {flag} {tid[:44]:44} {rep.overall.value:7} "
              f"P{c['PASS']:>2} F{c['FAIL']:>2} V{c['VERIFY']:>2} H{c['HOLD']} "
              f"N/A{c['NOT_APPLICABLE']:>2} S{c['SKIPPED']:>2}")

    print("\n" + "=" * 78)
    print(f"AGGREGATE over {sum(overalls.values())} transactions in {time.time()-t0:.0f}s")
    print(f"  Transaction outcomes: {dict(overalls)}")
    print(f"  Rule results total:   {dict(agg)}")
    print(f"\n  Most common exceptions (rule_id: # transactions):")
    for rid, n in finding_counter.most_common(15):
        print(f"     {rid:8} {n}")


if __name__ == "__main__":
    main()
