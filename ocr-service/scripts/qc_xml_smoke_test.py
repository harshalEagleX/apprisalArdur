"""
QC XML smoke-test — runs the full Python QC pipeline against 5 real appraisal
packages (dirs 1, 2, 3, 5, 6) and prints per-file rule results.

Reports per file:
  • Summary counts: PASS / FAIL / VERIFY / HOLD / NOT_APPLICABLE / SKIPPED
  • Section-level breakdown
  • All FAIL rules with their messages
  • All VERIFY rules with evidence values (to identify false positives)
  • Potential false positives: VERIFY rules where appraisal confidence ≥ 0.85

Usage:
  cd ocr-service && python scripts/qc_xml_smoke_test.py
"""

import logging
import os
import sys
from pathlib import Path

# ── project root on sys.path ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress noisy loggers so output is readable
logging.basicConfig(level=logging.WARNING)
for noisy in ("app.extraction", "app.qc.engine", "app.qc.transaction",
              "app.extraction.layers", "pdfminer", "PIL", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

BASE = Path("/Users/eaglex/Documents/indevelopment/eaglex/SHAL/uploads/xml1")
TEST_DIRS = [1, 2, 3, 5, 6]

# Status display order + colors (ANSI)
_CLR = {
    "PASS": "\033[32m",          # green
    "FAIL": "\033[31m",          # red
    "VERIFY": "\033[33m",        # yellow
    "HOLD": "\033[35m",          # magenta
    "NOT_APPLICABLE": "\033[90m",# grey
    "SKIPPED": "\033[90m",       # grey
}
_RST = "\033[0m"
_BOLD = "\033[1m"


def _col(status: str, text: str) -> str:
    return f"{_CLR.get(status, '')}{text}{_RST}"


def _find_files(d: Path):
    """Return (appraisal_pdf, xml_path, engagement_pdf, contract_pdf) for a directory."""
    pdfs = sorted(d.glob("*.pdf")) + sorted(d.glob("*.PDF"))
    xmls = sorted(d.glob("*.xml")) + sorted(d.glob("*.XML"))

    xml_path = xmls[0] if xmls else None

    appraisal_pdf = None
    engagement_pdf = None
    contract_pdf = None

    for p in pdfs:
        n = p.name.lower()
        if any(k in n for k in ("engagement", "letter", "engagementletter")):
            engagement_pdf = p
        elif any(k in n for k in ("contract", "purchase", "agreement", "residential")):
            contract_pdf = p
        else:
            # Assume the non-engagement non-contract PDF is the appraisal
            if appraisal_pdf is None:
                appraisal_pdf = p

    # If we misidentified, fall back: appraisal name usually matches the XML stem
    if xml_path and appraisal_pdf is None:
        stem = xml_path.stem.lower()
        for p in pdfs:
            if p.stem.lower() == stem:
                appraisal_pdf = p
                break

    return appraisal_pdf, xml_path, engagement_pdf, contract_pdf


def run_case(case_dir: int):
    d = BASE / str(case_dir)
    appraisal_pdf, xml_path, engagement_pdf, contract_pdf = _find_files(d)

    print(f"\n{'═'*72}")
    print(f"{_BOLD}CASE {case_dir}{_RST}  —  {d.name}")
    print(f"  Appraisal PDF : {appraisal_pdf.name if appraisal_pdf else '⚠ NOT FOUND'}")
    print(f"  XML           : {xml_path.name if xml_path else '⚠ NOT FOUND'}")
    print(f"  Engagement    : {engagement_pdf.name if engagement_pdf else '⚠ NOT FOUND'}")
    print(f"  Contract      : {contract_pdf.name if contract_pdf else '— none'}")
    print(f"{'═'*72}")

    if not appraisal_pdf:
        print("  ✗ Cannot run QC — appraisal PDF not found.")
        return None

    from app.qc.transaction import run_transaction_qc_paths

    try:
        report, ctx = run_transaction_qc_paths(
            appraisal_path=str(appraisal_pdf),
            xml_path=str(xml_path) if xml_path else None,
            engagement_path=str(engagement_pdf) if engagement_pdf else None,
            contract_path=str(contract_pdf) if contract_pdf else None,
            transaction_id=f"smoke-{case_dir}",
            persist=False,
        )
    except Exception as exc:
        print(f"  ✗ QC pipeline error: {exc}")
        import traceback; traceback.print_exc()
        return None

    results = report.results
    counts = report.counts()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*68}")
    print(f"  {'RULE COUNTS':30s}", end="")
    for st in ("PASS", "FAIL", "VERIFY", "HOLD", "NOT_APPLICABLE", "SKIPPED"):
        n = counts.get(st, 0)
        if n:
            print(f"  {_col(st, st)}: {_col(st, str(n))}", end="")
    print()
    total = len(results)
    auto_decided = counts.get("PASS", 0) + counts.get("FAIL", 0)
    pct = 100 * auto_decided / total if total else 0
    print(f"  Total rules: {total}  |  Auto-decided: {auto_decided} ({pct:.0f}%)  |  "
          f"Human-queue: {counts.get('VERIFY', 0) + counts.get('HOLD', 0)}")
    print(f"  {'─'*68}")

    # ── Section breakdown ─────────────────────────────────────────────────────
    from collections import defaultdict
    by_section = defaultdict(lambda: defaultdict(list))
    for r in results:
        by_section[r.section][r.status.value].append(r)

    print(f"\n  {'SECTION':<22} {'PASS':>5} {'FAIL':>5} {'VERIFY':>6} {'HOLD':>5} {'N/A':>5}")
    print(f"  {'─'*55}")
    for sec in sorted(by_section):
        sec_d = by_section[sec]
        p = len(sec_d.get("PASS", []))
        f = len(sec_d.get("FAIL", []))
        v = len(sec_d.get("VERIFY", []))
        h = len(sec_d.get("HOLD", []))
        na = len(sec_d.get("NOT_APPLICABLE", []))
        flag = " ⚠" if (f + v + h) > 0 else ""
        print(f"  {sec:<22} "
              f"{_col('PASS', str(p)):>12} "
              f"{_col('FAIL', str(f)) if f else '—':>12} "
              f"{_col('VERIFY', str(v)) if v else '—':>13} "
              f"{_col('HOLD', str(h)) if h else '—':>12} "
              f"{str(na):>5}{flag}")

    # ── FAIL rules ────────────────────────────────────────────────────────────
    fails = [r for r in results if r.status.value == "FAIL"]
    if fails:
        print(f"\n  {_col('FAIL', '── FAILURES ──')}")
        for r in fails:
            ev_str = _evidence_str(r)
            print(f"    {_col('FAIL', r.rule_id):<22}  {r.message or '(no message)'}")
            if ev_str:
                print(f"    {'':20}  evidence: {ev_str}")

    # ── VERIFY rules ──────────────────────────────────────────────────────────
    verifies = [r for r in results if r.status.value == "VERIFY"]
    if verifies:
        print(f"\n  {_col('VERIFY', '── VERIFY (human queue) ──')}")
        false_pos_candidates = []
        for r in verifies:
            ev_str = _evidence_str(r)
            # False-positive candidate: VERIFY but appraisal has high-confidence data
            fp_flag = ""
            if r.fields_involved:
                max_conf = max(
                    (ctx.appraisal.confidence(f) for f in r.fields_involved),
                    default=0.0,
                )
                if max_conf >= 0.85:
                    conf_str = f"{max_conf:.2f}"
                    fp_flag = f"  {_col('HOLD', chr(9873) + ' possible false-positive (conf=' + conf_str + ')')}"
                    false_pos_candidates.append((r, max_conf))

            print(f"    {_col('VERIFY', r.rule_id):<22}  {r.message or '(no message)'}{fp_flag}")
            if ev_str:
                print(f"    {'':20}  evidence: {ev_str}")

        if false_pos_candidates:
            print(f"\n  {_bold('⚑ POTENTIAL FALSE POSITIVES')} — VERIFY rules with conf ≥ 0.85:")
            for r, conf in sorted(false_pos_candidates, key=lambda x: -x[1]):
                print(f"    {r.rule_id:<12}  conf={conf:.2f}  {r.message[:80]}")

    return counts


def _evidence_str(r) -> str:
    parts = []
    for e in r.evidence:
        if e.value:
            parts.append(f"[{e.document}:{e.field or '?'}={repr(e.value)[:40]} conf={e.confidence:.2f}]")
    return "  ".join(parts) if parts else ""


def _bold(s: str) -> str:
    return f"{_BOLD}{s}{_RST}"


def main():
    print(f"\n{_BOLD}SHAL QC XML SMOKE TEST{_RST}")
    print(f"Testing {len(TEST_DIRS)} appraisal packages: dirs {TEST_DIRS}")

    all_counts = {}
    for case in TEST_DIRS:
        counts = run_case(case)
        if counts:
            all_counts[case] = counts

    # ── Aggregate summary ─────────────────────────────────────────────────────
    if len(all_counts) > 1:
        print(f"\n\n{'═'*72}")
        print(f"{_BOLD}AGGREGATE — ALL {len(all_counts)} CASES{_RST}")
        print(f"{'─'*72}")
        totals = {}
        for counts in all_counts.values():
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
        for st in ("PASS", "FAIL", "VERIFY", "HOLD", "NOT_APPLICABLE", "SKIPPED"):
            n = totals.get(st, 0)
            if n:
                pct = 100 * n / sum(totals.values())
                print(f"  {_col(st, f'{st:<16}')}: {n:>4}  ({pct:4.1f}%)")
        grand = sum(totals.values())
        auto = totals.get("PASS", 0) + totals.get("FAIL", 0)
        print(f"\n  Total rules evaluated: {grand}")
        print(f"  Auto-decided (PASS+FAIL):   {auto} ({100*auto/grand:.1f}%)")
        print(f"  Human queue (VERIFY+HOLD):  "
              f"{totals.get('VERIFY',0)+totals.get('HOLD',0)} "
              f"({100*(totals.get('VERIFY',0)+totals.get('HOLD',0))/grand:.1f}%)")
        print(f"{'═'*72}\n")


if __name__ == "__main__":
    main()
