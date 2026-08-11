"""Quality report for a vision-extraction run.

**The primary metrics need NO hand-authored answers.** That is the point: a
quality signal that requires someone to type the right values for each document
does not survive contact with a new document, and every order is a new document.
So the report below is computed from the run itself and from arithmetic the
report states about itself:

    verification rate  — closed-form identities in the document that the
                         extraction must satisfy (comp net = sum of lines;
                         adjusted = sale + net; sketch items = total; room
                         summary = room totals). Needs no ground truth: the
                         document IS the oracle.
    abstention rate    — how often the model correctly emitted null instead of
                         guessing. Abstention is a FEATURE; a run with 0%
                         abstention on a form with absent sections is
                         confabulating.
    provenance rate    — share of values carrying the printed label they were
                         matched to. A value that cannot name its own label is
                         a guess by construction.
    budget / coverage  — cost actually spent, and how much of the schema filled.

An optional ground-truth file adds precision on top for GOLDEN ORDERS ONLY —
the standing rule is never to judge a QC result from fewer than 3 randomly
picked orders, and precision is the one number that cannot be computed without
a human having read the page. It is a spot check, not the gate.

**Precision and coverage are never combined into one number.** They move in
opposite directions: guess more and coverage rises while precision falls. A
blended score hides exactly the trade you need to see.

Usage:
    PYTHONPATH=. python 3.6/score.py 3.6/_run1.json [ground_truth.json]
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Optional


def norm(text: Any) -> str:
    if text is None:
        return ""
    s = re.sub(r"[\$,]", "", str(text).strip().lower())
    return re.sub(r"\s+", " ", s).strip(" .")


def matches(expected: Dict[str, Any], actual: Any) -> bool:
    a = norm(actual)
    if not a:
        return False
    for c in [expected.get("value")] + list(expected.get("_alt") or []):
        n = norm(c)
        if n and (a == n or (len(n) > 3 and (n in a or a in n))):
            return True
    return False


def report(run: Dict[str, Any], gt: Optional[Dict[str, Any]] = None) -> None:
    got: Dict[str, Any] = run.get("_fields") or {}
    budget = run.get("budget") or {}
    ver = run.get("verification") or {}

    print("=" * 70)
    print(f"UAD {run.get('uad_version')} extraction — {run.get('document_class')} document")
    print("=" * 70)
    pm = run.get("page_map") or {}
    print(f"pages            {pm.get('total_pages')} total, "
          f"{len(pm.get('extractable_pages') or [])} extractable, "
          f"{len(pm.get('skipped_pages') or [])} skipped as photo/blank")
    print(f"runtime          {run.get('_runtime_s')}s")
    print(f"cost             ${budget.get('spent_usd', 0):.4f} of "
          f"${budget.get('cap_usd', 0):.2f} cap over {budget.get('calls', 0)} calls "
          f"({budget.get('input_tokens', 0):,} in / {budget.get('output_tokens', 0):,} out)")
    if budget.get("breached_on"):
        print(f"                 !! budget bound at '{budget['breached_on']}' — "
              f"extraction stopped early")

    # ── 1. verification (no ground truth needed) ─────────────────────────────
    print("\n" + "-" * 70)
    print("1. VERIFICATION — the document checking itself (no ground truth used)")
    print("-" * 70)
    regions, verified = ver.get("regions", 0), ver.get("verified", 0)
    rate = 100.0 * verified / regions if regions else 0.0
    print(f"   {verified}/{regions} regions verified ({rate:.0f}%), "
          f"{ver.get('checks_run', 0)} identities checked, {ver.get('failed', 0)} failed")
    for region, errs in (ver.get("failures") or {}).items():
        for e in errs:
            print(f"     FAIL {region}: {e}")
    grid = run.get("grid") or {}
    if grid.get("retries"):
        print(f"   {grid['retries']} column(s) re-extracted after a failed checksum")

    # ── 2. abstention + provenance ───────────────────────────────────────────
    print("\n" + "-" * 70)
    print("2. ABSTENTION & PROVENANCE — is it guessing?")
    print("-" * 70)
    sections = run.get("sections") or {}
    attempted = len(sections.get("sections_attempted") or [])
    failed = len(sections.get("sections_failed") or {})
    print(f"   sections   {attempted} attempted, {failed} failed to return")
    print(f"   emitted    {len(got)} fields with a non-null value")
    src_counts: Dict[str, int] = {}
    for f in got.values():
        src_counts[str(f.get("source"))] = src_counts.get(str(f.get("source")), 0) + 1
    for src, n in sorted(src_counts.items(), key=lambda kv: -kv[1]):
        note = "  <- unverified: routes to a REVIEW card" if "unverified" in src else ""
        print(f"     {src:24} {n:>4}{note}")

    # ── 3. coverage ──────────────────────────────────────────────────────────
    print("\n" + "-" * 70)
    print("3. COVERAGE — of the schema, how much got filled")
    print("-" * 70)
    schema_fields = run.get("schema_fields") or 0
    cov = 100.0 * len(got) / schema_fields if schema_fields else 0.0
    print(f"   {len(got)} / {schema_fields} schema fields = {cov:.1f}%")
    print("   (reported separately from precision, never blended — guessing more")
    print("    raises this number and lowers precision)")

    # ── 4. optional precision ────────────────────────────────────────────────
    if gt:
        fields = gt.get("fields") or {}
        correct, wrong, missed = [], [], []
        for name, expected in fields.items():
            entry = got.get(name)
            if entry is None or entry.get("value") in (None, ""):
                missed.append(name)
            elif matches(expected, entry.get("value")):
                correct.append(name)
            else:
                wrong.append((name, expected.get("value"), entry.get("value")))
        checked = len(correct) + len(wrong)
        prec = 100.0 * len(correct) / checked if checked else 0.0
        print("\n" + "-" * 70)
        print("4. PRECISION — spot check against a hand-verified golden order")
        print("-" * 70)
        print(f"   {len(correct)} correct / {checked} emitted-and-checked = {prec:.1f}%")
        print(f"   {len(missed)} of {len(fields)} golden fields not emitted at all")
        if wrong:
            print("\n   WRONG VALUES (the dangerous class — a confident wrong value):")
            for name, exp, act in wrong:
                print(f"     {name:32} want {str(exp)[:24]!r:28} got {str(act)[:24]!r}")
        if missed:
            print(f"\n   NOT EMITTED: {', '.join(missed[:18])}"
                  + (" ..." if len(missed) > 18 else ""))
        print("\n   NOTE: one order proves a mechanism, never an effect. Do not")
        print("   claim a change improved anything from fewer than 3 orders.")
    else:
        print("\n   (no ground-truth file supplied — precision not computed.")
        print("    The metrics above required none and work on any document.)")

    degs = run.get("degradations") or []
    if degs:
        print("\n" + "-" * 70)
        print(f"DEGRADATIONS ({len(degs)}) — what a reviewer must be told")
        print("-" * 70)
        for d in degs:
            print(f"   - {str(d)[:160]}")


def main() -> int:
    run_path = sys.argv[1] if len(sys.argv) > 1 else "3.6/_run1.json"
    run = json.load(open(run_path, encoding="utf-8"))
    gt = None
    if len(sys.argv) > 2:
        try:
            gt = json.load(open(sys.argv[2], encoding="utf-8"))
        except FileNotFoundError:
            print(f"(ground truth {sys.argv[2]} not found — skipping precision)\n")
    report(run, gt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
