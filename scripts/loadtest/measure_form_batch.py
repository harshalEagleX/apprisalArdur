#!/usr/bin/env python3
"""
Measured A/B for FORM_LLM_BATCH (per P-8 / P-13): run each document twice — flag
OFF then ON — and report LLM calls, tokens, and the QC PASS/FAIL/VERIFY/HOLD
counts. Adopt the flag ONLY if calls/tokens drop AND the rule counts are unchanged
(no extraction regression).

The flag is toggled in-process at runtime (config.FORM_LLM_BATCH is read at call
time), so no service restart is needed. Token cost is read from the recording
proxy that must sit in front of Groq.

Run (from ocr-service/, with cache OFF so OFF and ON are measured cold):
  GROQ_BASE_URL=http://127.0.0.1:5099/openai/v1 \
  GROQ_CACHE_ENABLED=false GROQ_TPM_LIMIT=8000 \
  /opt/homebrew/Caskroom/miniconda/base/envs/apprisal/bin/python3 \
      ../scripts/loadtest/measure_form_batch.py "<appraisal.pdf>" ["<more.pdf>" ...]
"""
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

PROXY = "http://127.0.0.1:5099/stats"


def _stats():
    try:
        with urllib.request.urlopen(PROXY, timeout=5) as r:
            d = json.load(r)
        return d.get("calls", 0), d.get("total_tokens", 0)
    except Exception:
        return 0, 0


def main():
    from app import config
    from app.qc.transaction import run_transaction_qc_paths

    docs = sys.argv[1:] or [
        "uploads/OS/#2321525427/appraisal/1718 Theon St.pdf",
        "uploads/OS/#2321525470/appraisal/90 NE 32nd St Unit 524.pdf",
    ]
    hdr = f"{'document':26} {'mode':4} {'calls':>5} {'tokens':>7} {'PASS':>5} {'FAIL':>5} {'VERIFY':>6} {'HOLD':>5}"
    print(hdr)
    print("-" * len(hdr))
    rows = {"off": [], "on": []}
    regression = []

    for d in docs:
        name = Path(d).stem[:25]
        per = {}
        for mode in ("off", "on"):
            config.FORM_LLM_BATCH = mode == "on"
            c0, t0 = _stats()
            report, _ctx = run_transaction_qc_paths(
                Path(d), None, None, transaction_id=f"{name}-{mode}", persist=False
            )
            c1, t1 = _stats()
            cnt = Counter(r.status.name for r in report.results)
            calls, toks = c1 - c0, t1 - t0
            print(f"{name:26} {mode:4} {calls:5d} {toks:7d} "
                  f"{cnt.get('PASS',0):5d} {cnt.get('FAIL',0):5d} "
                  f"{cnt.get('VERIFY',0)+cnt.get('HOLD',0):6d} {cnt.get('HOLD',0):5d}")
            rows[mode].append((calls, toks))
            per[mode] = cnt
        # accuracy gate: PASS/FAIL/(VERIFY+HOLD) must match between modes
        def sig(c):
            return (c.get("PASS", 0), c.get("FAIL", 0), c.get("VERIFY", 0) + c.get("HOLD", 0))
        if sig(per["off"]) != sig(per["on"]):
            regression.append((name, sig(per["off"]), sig(per["on"])))

    print("\n=== SUMMARY ===")
    for mode in ("off", "on"):
        tc = sum(x[0] for x in rows[mode])
        tt = sum(x[1] for x in rows[mode])
        n = max(len(rows[mode]), 1)
        print(f"  {mode:3}: total calls={tc} tokens={tt}  | avg/doc calls={tc/n:.1f} tokens={tt/n:.0f}")
    oc = sum(x[0] for x in rows["off"]) or 1
    ot = sum(x[1] for x in rows["off"]) or 1
    nc = sum(x[0] for x in rows["on"])
    nt = sum(x[1] for x in rows["on"])
    print(f"  REDUCTION: calls -{(1-nc/oc)*100:.0f}%  tokens -{(1-nt/ot)*100:.0f}%")
    if regression:
        print("\n  ❌ ACCURACY REGRESSION — do NOT adopt the flag:")
        for name, off, on in regression:
            print(f"     {name}: PASS/FAIL/VERIFY off={off} on={on}")
    else:
        print("\n  ✅ No PASS/FAIL/VERIFY change — batching preserved QC outcomes.")


if __name__ == "__main__":
    main()
