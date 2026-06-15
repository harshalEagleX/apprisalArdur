#!/usr/bin/env python3
"""
Scaling Phase 6 (readme/SCALABILITY_PLAN.md) — processing throughput soak (T-3).

Proves the platform sustains 250+ documents/day: submits a corpus of real PDFs to the
Python durable queue (POST /qc/submit), polls each job to a terminal state
(GET /qc/job/{id}), and reports throughput (docs/min, docs/day projection), latency
percentiles, and that ZERO jobs were lost.

Prereqs: Redis up, a Celery worker running (the durable queue), GROQ key configured,
and a directory of real appraisal PDFs.

  OCR_URL=http://127.0.0.1:5001 \
  INTERNAL_API_KEY=... \
  python scripts/loadtest/process_soak.py --corpus uploads/ --count 250 --inflight 6

`--inflight` caps how many jobs are queued at once (mirrors worker concurrency, so the
queue is fed but not unboundedly flooded). docs/day = docs/min × 1440.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

OCR_URL = os.getenv("OCR_URL", "http://127.0.0.1:5001")
API_KEY = os.getenv("INTERNAL_API_KEY", "")
TERMINAL = {"SUCCESS", "FAILURE"}


def _headers() -> dict:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def submit(pdf: Path) -> str:
    with open(pdf, "rb") as fh:
        files = {"file": (pdf.name, fh, "application/pdf")}
        data = {"model_provider": "groq", "document_id": pdf.name}
        r = requests.post(f"{OCR_URL}/qc/submit", files=files, data=data,
                          headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()["job_id"]


def wait(job_id: str, timeout_s: int = 1800) -> tuple[str, float]:
    start = time.time()
    while time.time() - start < timeout_s:
        r = requests.get(f"{OCR_URL}/qc/job/{job_id}", headers=_headers(), timeout=15)
        if r.ok:
            state = r.json().get("status")
            if state in TERMINAL:
                return state, time.time() - start
        time.sleep(3)
    return "TIMEOUT", time.time() - start


def run_one(pdf: Path) -> dict:
    t0 = time.time()
    try:
        job_id = submit(pdf)
    except Exception as exc:
        return {"pdf": pdf.name, "state": "SUBMIT_ERROR", "error": str(exc), "secs": time.time() - t0}
    state, secs = wait(job_id)
    return {"pdf": pdf.name, "job_id": job_id, "state": state, "secs": secs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="directory of *.pdf to submit")
    ap.add_argument("--count", type=int, default=250)
    ap.add_argument("--inflight", type=int, default=6, help="max concurrent in-flight jobs")
    args = ap.parse_args()

    pdfs = sorted(Path(args.corpus).rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs under {args.corpus}", file=sys.stderr)
        return 2
    # Repeat the corpus to reach --count (idempotent dedup is bypassed here: no
    # idempotency_key is sent, so each submission is a distinct job — true throughput).
    work = [pdfs[i % len(pdfs)] for i in range(args.count)]

    print(f"[soak] {len(work)} docs → {OCR_URL}  (inflight={args.inflight}, corpus={len(pdfs)} unique)")
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.inflight) as pool:
        futures = [pool.submit(run_one, p) for p in work]
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            if i % 10 == 0 or i == len(work):
                done = sum(1 for r in results if r["state"] in TERMINAL)
                print(f"[soak] {i}/{len(work)} returned ({done} terminal)")

    elapsed_min = (time.time() - started) / 60.0
    ok = [r for r in results if r["state"] == "SUCCESS"]
    failed = [r for r in results if r["state"] == "FAILURE"]
    lost = [r for r in results if r["state"] in ("TIMEOUT", "SUBMIT_ERROR")]
    secs = sorted(r["secs"] for r in results if r.get("secs"))

    def pct(p): return secs[min(len(secs) - 1, int(len(secs) * p))] if secs else 0.0
    rate = len(results) / elapsed_min if elapsed_min else 0.0

    print("\n========== SOAK RESULT ==========")
    print(f" submitted        : {len(results)}")
    print(f" SUCCESS          : {len(ok)}")
    print(f" FAILURE          : {len(failed)}")
    print(f" LOST (timeout/err): {len(lost)}   <-- must be 0 (T-3: no lost jobs)")
    print(f" wall time        : {elapsed_min:.1f} min")
    print(f" throughput       : {rate:.1f} docs/min  ->  ~{rate * 1440:.0f} docs/day")
    print(f" per-doc p50/p95  : {pct(0.5):.1f}s / {pct(0.95):.1f}s")
    print("=================================")
    # Exit non-zero if any job was lost — makes this usable as a CI/soak gate.
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
