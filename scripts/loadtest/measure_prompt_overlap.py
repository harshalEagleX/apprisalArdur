#!/usr/bin/env python3
"""
FREE cache-ceiling probe: how much of a document's LLM input is a REPEATED exact
prefix (the only thing Groq prompt caching can exempt from rate limits)?

Patches llm_groq.chat_json to RECORD each prompt and return {} — so the whole QC
pipeline runs with ZERO Groq calls and zero quota. Then it measures, across all
text-model calls for one document, the exact-prefix sharing.

Groq caches the longest EXACT PREFIX shared with an earlier request, only if that
prefix ≥ the model minimum (128–1024 tokens). We report the cacheable fraction at
both thresholds so the real opportunity is bracketed.

Run (project root):
  PYTHONPATH=ocr-service python3 scripts/loadtest/measure_prompt_overlap.py "<appraisal.pdf>"
"""
import sys
from pathlib import Path


def approx_tokens(s: str) -> int:
    return max(0, len(s) // 4)  # ~4 chars/token (rough, fine for a ceiling estimate)


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def main():
    import app.extraction.llm_groq as g

    calls = []

    def _record(messages, **kw):
        txt = "\n".join(f"{m.get('role')}:{m.get('content','')}" for m in messages)
        calls.append(txt)
        return {}  # no network, no quota — pipeline degrades gracefully

    g.chat_json = _record

    from app.qc.transaction import run_transaction_qc_paths

    doc = sys.argv[1] if len(sys.argv) > 1 else "uploads/OS/#2321525427/appraisal/1718 Theon St.pdf"
    print(f"Running pipeline (LLM stubbed) on: {doc}")
    run_transaction_qc_paths(Path(doc), None, None, transaction_id="overlap", persist=False)

    n = len(calls)
    if n == 0:
        print("No LLM calls were made for this document.")
        return
    total_tok = sum(approx_tokens(c) for c in calls)

    # For each call, the longest exact prefix it shares with ANY earlier call.
    shared = []
    for i, c in enumerate(calls):
        best = max((common_prefix_len(c, calls[j]) for j in range(i)), default=0)
        shared.append(approx_tokens(c[:best]))

    def cacheable_at(min_tok):
        return sum(sp for sp in shared if sp >= min_tok)

    # Common prefix across ALL calls (what every call shares — usually the system text).
    allp = calls[0]
    for c in calls[1:]:
        allp = allp[:common_prefix_len(allp, c)]

    print(f"\nLLM text-model calls: {n}")
    print(f"Total input (approx): {total_tok} tokens")
    print(f"Common prefix across ALL calls: ~{approx_tokens(allp)} tokens")
    print(f"\nCacheable (repeated exact-prefix) ceiling:")
    for mn in (128, 256, 1024):
        c = cacheable_at(mn)
        print(f"  if model min = {mn:4} tok -> {c:6} tok cacheable = {c/total_tok*100:4.0f}% of input")
    print(f"\nPer-call input vs its shared-prefix (tokens):")
    print(f"  {'call':4} {'input':>7} {'shared_prefix':>14}")
    for i, c in enumerate(calls):
        print(f"  {i+1:4} {approx_tokens(c):7} {shared[i]:14}")

    print("\nReading: 'cacheable %' is the MOST of your per-doc input that Groq could "
          "exempt from the 8K/min limit as-is. High → restructure to exploit it. "
          "Low → the calls read genuinely different text; caching can't rescue the free tier.")


if __name__ == "__main__":
    main()
