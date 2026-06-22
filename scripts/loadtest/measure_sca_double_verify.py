#!/usr/bin/env python3
"""
Measure SCA_DOUBLE_VERIFY (Problem 4) end-to-end with real Groq: per doc, run the
pipeline OFF then ON and report
  • QC PASS/FAIL/VERIFY (does compare-and-flag raise VERIFYs?)
  • how many SCA currency cells AGREED (camelot==llm) vs CONFLICTED (disagree)
  • tokens (via the recording proxy)
Adopt only if conflicts are REAL extraction errors (correct VERIFYs), not noise.

Run (project root, proxy on 5099):
  GROQ_BASE_URL=http://127.0.0.1:5099/openai/v1 GROQ_CACHE_ENABLED=false GROQ_TPM_LIMIT=8000 \
  PYTHONPATH=ocr-service python3 scripts/loadtest/measure_sca_double_verify.py <appraisal> [...]
"""
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path


def _stats():
    try:
        with urllib.request.urlopen("http://127.0.0.1:5099/stats", timeout=5) as r:
            d = json.load(r)
        return d.get("calls", 0), d.get("total_tokens", 0)
    except Exception:
        return 0, 0


def _sca_methods(ctx):
    """Count SCA agree/conflict cells from the appraisal extraction set, if reachable."""
    c = Counter()
    try:
        rs = getattr(ctx, "appraisal", None)
        if rs is None:
            return c
        for _name, r in rs:
            m = getattr(r, "extraction_method", "") or ""
            if "llm_agree" in m:
                c["agree"] += 1
            elif "sca_conflict" in m:
                c["conflict"] += 1
    except Exception:
        pass
    return c


def main():
    from app import config
    from app.qc.transaction import run_transaction_qc_paths

    docs = sys.argv[1:] or ["uploads/DEMO/fantail_batch/appraisal/28203 Fantail Dr.pdf"]
    print(f"{'doc':24} {'mode':4} {'PASS':>5} {'FAIL':>5} {'VERIFY':>6} {'agree':>6} {'conflict':>8} {'tokens':>7}")
    print("-" * 74)
    for d in docs:
        name = Path(d).stem[:23]
        sig = {}
        for mode in ("off", "on"):
            config.SCA_DOUBLE_VERIFY = mode == "on"
            c0, t0 = _stats()
            report, ctx = run_transaction_qc_paths(Path(d), None, None,
                                                   transaction_id=f"{name}-{mode}", persist=False)
            c1, t1 = _stats()
            cnt = Counter(r.status.name for r in report.results)
            meth = _sca_methods(ctx)
            verify = cnt.get("VERIFY", 0) + cnt.get("HOLD", 0)
            print(f"{name:24} {mode:4} {cnt.get('PASS',0):5} {cnt.get('FAIL',0):5} {verify:6} "
                  f"{meth.get('agree',0):6} {meth.get('conflict',0):8} {t1-t0:7}")
            sig[mode] = (cnt.get("PASS", 0), cnt.get("FAIL", 0), verify)
        delta = "SAME" if sig["off"] == sig["on"] else f"CHANGED off={sig['off']} on={sig['on']}"
        print(f"  -> PASS/FAIL/VERIFY: {delta}\n")


if __name__ == "__main__":
    main()
