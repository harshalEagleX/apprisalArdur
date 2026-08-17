"""Full end-to-end QC on one report: extraction + judge + verdicts, timed.

`run_extract.py` stops after extraction, so every timing produced from it
EXCLUDES the judge pass. This runs the whole pipeline the way an order actually
runs, and reports both halves separately — total wall clock, and the checklist
outcome (PASS / FAIL / VERIFY / NOT_APPLICABLE).

Usage:
    PYTHONPATH=. python 3.6/run_full_qc.py <pdf> [out_prefix]
"""
from __future__ import annotations

import collections
import json
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    pdf = Path(sys.argv[1] if len(sys.argv) > 1
               else "3.6/Email - AppraisalArdur - Outlook (1).pdf")
    prefix = sys.argv[2] if len(sys.argv) > 2 else "3.6/_qc"

    # run_qc takes an order FOLDER, so stage the PDF into one.
    order_dir = Path(tempfile.mkdtemp(prefix="shal_order_"))
    shutil.copy2(pdf, order_dir / "appraisal.pdf")

    from app.llm.client import get_client
    from app.pipeline.orchestrator import run_qc

    # Without a client the ENTIRE judgment tier no-ops and every item degrades
    # to REVIEW while the run still reports status OK — 134/134 REVIEW, zero
    # decided, 0 billed calls. And without the AMC code the base profile loads
    # the 2.6 bundle, so a 3.6 report is scored against 2.6 wording.
    client = get_client()
    if client is None or not getattr(client, "available", False):
        print("WARNING: no LLM client — the judge cannot run and every item "
              "will degrade to REVIEW. Check TOGETHER_API_KEY_*.")
    t0 = time.time()
    report = run_qc(order_dir, llm_client=client, persist=False,
                    amc_code="EQUITYSOLUTIONS")
    total = time.time() - t0

    with open(f"{prefix}.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)

    # ── checklist outcome ────────────────────────────────────────────────────
    findings = (report.get("findings") or report.get("items")
                or report.get("verdicts") or [])
    counts = collections.Counter(
        str((f.get("status") or f.get("verdict") or "?")).upper()
        for f in findings if isinstance(f, dict))

    print("\n" + "=" * 62)
    print(f"TOTAL WALL CLOCK        {total:8.1f}s")
    ext = ((report.get("vision") or {}).get("_runtime_s")
           or (report.get("extraction") or {}).get("_runtime_s"))
    if ext:
        print(f"  extraction            {float(ext):8.1f}s")
        print(f"  judge + rest          {total - float(ext):8.1f}s")
    print("=" * 62)
    print(f"CHECKLIST — {sum(counts.values())} items scored")
    for k in ("PASS", "FAIL", "VERIFY", "NOT_APPLICABLE", "HOLD"):
        if counts.get(k):
            print(f"  {k:<18} {counts[k]:>4}")
    for k, v in counts.items():
        if k not in ("PASS", "FAIL", "VERIFY", "NOT_APPLICABLE", "HOLD"):
            print(f"  {k:<18} {v:>4}")

    proofs = ((report.get("vision") or {}).get("proofs")
              or report.get("proofs") or [])
    if isinstance(proofs, list) and proofs:
        decided = [p for p in proofs if p.get("status") in ("PASS", "FAIL")]
        print(f"\nsettled by arithmetic (no judge call): "
              f"{len(decided)} decided of {len(proofs)}")
        for p in proofs:
            print(f"  #{p.get('checklist_number') or '(set)':<6} {p.get('status'):<8}"
                  f" {(p.get('computation') or p.get('reason') or '')[:60]}")

    print(f"\nstatus: {report.get('status')}   wrote {prefix}.json")
    shutil.rmtree(order_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
