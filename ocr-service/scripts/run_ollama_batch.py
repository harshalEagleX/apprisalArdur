#!/usr/bin/env python3
"""
run_ollama_batch.py — Ollama sensibility analysis batch runner.

Processes two batches through the QC pipeline with full Ollama enrichment:
  1. MSL     — the reference document used to build regex/rules
  2. #2321525470 — a random/unknown document for cross-format validation

For each batch:
  - POSTs all 3 PDFs (appraisal + engagement + contract) to /qc/process
  - model_provider=ollama → triggers full Ollama enrichment on every rule
  - Captures per-rule timing, verdict, and Ollama vs deterministic comparison

Outputs:
  - reports/ollama_batch_MSL.json
  - reports/ollama_batch_2321525470.json
  - reports/ollama_sensibility_report.md   ← the main comparison report

Usage:
    cd ocr-service
    python scripts/run_ollama_batch.py

Requirements:
  - uvicorn main:app running on port 5001
  - Ollama running with llava:13b loaded
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

SERVICE_URL = "http://127.0.0.1:5001"
UPLOADS_ROOT = Path(__file__).parent.parent.parent / "uploads"

BATCHES = {
    "MSL": {
        "label": "MSL (reference — used to build regex/rules)",
        "appraisal":   UPLOADS_ROOT / "EQSS" / "MSL" / "appraisal" / "96 Baell Trace Ct SE.pdf",
        "engagement":  UPLOADS_ROOT / "EQSS" / "MSL" / "engagement" / "96 Baell Tr Ct Order form.pdf",
        "contract":    UPLOADS_ROOT / "EQSS" / "MSL" / "contract"   / "96 baell Tr Ct CONTRACT.pdf",
    },
    "2321525470": {
        "label": "#2321525470 (random/unknown — cross-format validation)",
        "appraisal":   UPLOADS_ROOT / "sort" / "#2321525470" / "appraisal" / "90 NE 32nd St Unit 524.pdf",
        "engagement":  UPLOADS_ROOT / "sort" / "#2321525470" / "engagement" / "90 NE 32nd St Unit 524 Order form.pdf",
        "contract":    UPLOADS_ROOT / "sort" / "#2321525470" / "contract"   / "90 NE 32nd St Unit 524 CONTRACT.pdf",
    },
}

REPORTS_DIR = Path(__file__).parent.parent / "reports"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _post_qc(batch_key: str, batch: dict) -> dict:
    """POST all 3 PDFs to /qc/process and return the parsed JSON response."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' not installed. Run: pip install requests")
        sys.exit(1)

    url = f"{SERVICE_URL}/qc/process"
    appraisal_path = batch["appraisal"]
    engagement_path = batch.get("engagement")
    contract_path = batch.get("contract")

    if not appraisal_path.exists():
        return {"error": f"Appraisal PDF not found: {appraisal_path}"}

    files = {}
    open_handles = []
    try:
        fh = open(appraisal_path, "rb")
        open_handles.append(fh)
        files["file"] = (appraisal_path.name, fh, "application/pdf")

        if engagement_path and engagement_path.exists():
            fh2 = open(engagement_path, "rb")
            open_handles.append(fh2)
            files["engagement_letter"] = (engagement_path.name, fh2, "application/pdf")
        else:
            print(f"  [WARN] Engagement letter not found: {engagement_path}")

        if contract_path and contract_path.exists():
            fh3 = open(contract_path, "rb")
            open_handles.append(fh3)
            files["contract_file"] = (contract_path.name, fh3, "application/pdf")
        else:
            print(f"  [WARN] Contract not found: {contract_path}")

        data = {
            "model_provider": "ollama",
            "text_model": "llava:13b",
            "vision_model": "llava:13b",
        }

        # Read API key from root .env
        root_env = Path(__file__).parent.parent.parent / ".env"
        api_key = ""
        if root_env.exists():
            for line in root_env.read_text().splitlines():
                if line.startswith("INTERNAL_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
        headers = {"X-API-Key": api_key} if api_key else {}

        print(f"  → POST {url}")
        print(f"       appraisal  : {appraisal_path.name}")
        print(f"       engagement : {engagement_path.name if engagement_path and engagement_path.exists() else 'MISSING'}")
        print(f"       contract   : {contract_path.name if contract_path and contract_path.exists() else 'MISSING'}")
        print(f"       model      : ollama / llava:13b")
        print(f"       api_key    : {'set' if api_key else 'MISSING'}")

        t0 = time.monotonic()
        resp = requests.post(url, files=files, data=data, headers=headers, timeout=600)
        elapsed = time.monotonic() - t0

        print(f"  ← HTTP {resp.status_code}  ({elapsed:.1f}s)")

        if resp.status_code != 200:
            return {
                "error": f"HTTP {resp.status_code}",
                "body": resp.text[:500],
                "elapsed_s": elapsed,
            }

        result = resp.json()
        result["_batch_key"] = batch_key
        result["_elapsed_s"] = elapsed
        result["_timestamp"] = datetime.utcnow().isoformat()
        result["_files"] = {
            "appraisal": str(appraisal_path),
            "engagement": str(engagement_path) if engagement_path else None,
            "contract": str(contract_path) if contract_path else None,
        }
        return result

    finally:
        for fh in open_handles:
            fh.close()


def _rule_summary(rule: dict) -> dict:
    """Extract comparison fields from one rule result item."""
    details = rule.get("details") or {}
    return {
        "rule_id":           rule.get("rule_id"),
        "rule_name":         rule.get("rule_name"),
        "det_status":        rule.get("status"),          # deterministic
        "det_message":       (rule.get("message") or "")[:120],
        "confidence":        rule.get("confidence"),
        "source_page":       rule.get("source_page"),
        "ollama_verdict":    details.get("ollama_ollama_verdict") or details.get("ollama_verdict"),
        "ollama_finding":    details.get("ollama_ollama_finding") or details.get("ollama_finding"),
        "ollama_confidence": details.get("ollama_ollama_confidence") or details.get("ollama_confidence"),
        "ollama_ms":         details.get("ollama_ollama_ms") or details.get("ollama_ms"),
        "ollama_skipped":    details.get("ollama_ollama_skipped") or details.get("ollama_skipped"),
        "ollama_cached":     details.get("ollama_ollama_cached") or details.get("ollama_cached"),
    }


# ── Markdown report generator ──────────────────────────────────────────────────

def _generate_report(results: dict[str, dict]) -> str:
    lines = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines += [
        "# Ollama Sensibility Analysis — Batch QC Report",
        f"Generated: {now}  |  Model: llava:13b  |  Provider: Ollama (local)",
        "",
        "## Overview",
        "",
        "| Batch | Label | Total Time | Pages | Rules Run | PASS | FAIL | VERIFY | Ollama Doc Extract |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for key, label_cfg in [("MSL", BATCHES["MSL"]), ("2321525470", BATCHES["2321525470"])]:
        r = results.get(key, {})
        err = r.get("error")
        if err:
            lines.append(f"| {key} | {label_cfg['label']} | ERROR | — | — | — | — | — | {err} |")
            continue
        oda = r.get("ollama_doc_analysis") or {}
        addr = oda.get("property_address", "—")
        lines.append(
            f"| {key} | {label_cfg['label']} "
            f"| {r.get('_elapsed_s', 0):.0f}s "
            f"| {r.get('total_pages', '?')} "
            f"| {r.get('total_rules', '?')} "
            f"| {r.get('passed', '?')} "
            f"| {r.get('failed', '?')} "
            f"| {r.get('review', '?')} "
            f"| addr: `{addr}` |"
        )

    lines += [
        "",
        "---",
        "",
        "## Ollama Full-Document Extraction",
        "",
        "Ollama's independent read of each document (no regex, no rules).",
        "",
    ]

    for key in ("MSL", "2321525470"):
        r = results.get(key, {})
        if r.get("error"):
            continue
        oda = r.get("ollama_doc_analysis") or {}
        label = BATCHES[key]["label"]
        lines += [
            f"### {key} — {label}",
            "",
            f"- **Property Address:** {oda.get('property_address', 'not extracted')}",
            f"- **Borrower:** {oda.get('borrower', 'not extracted')}",
            f"- **Contract Price:** {oda.get('contract_price', 'not extracted')}",
            f"- **Appraised Value:** {oda.get('appraised_value', 'not extracted')}",
            f"- **Market Conditions Quality:** {oda.get('market_conditions_quality', 'unknown')}",
            f"- **Form Type:** {oda.get('form_type', 'unknown')}",
            f"- **Overall Issues:** {', '.join(oda.get('overall_issues') or []) or 'none identified'}",
            f"- **Commentary Issues:** {', '.join(oda.get('commentary_issues') or []) or 'none identified'}",
            f"- **Ollama Processing Time:** {oda.get('ollama_ms', 0):.0f} ms",
            "",
        ]

    lines += [
        "---",
        "",
        "## Per-Rule Comparison: Deterministic vs Ollama",
        "",
        "Legend — Ollama Verdict:  ✅ AGREE  |  ❌ DISAGREE  |  ❓ UNCERTAIN  |  ⏭ SKIPPED",
        "",
    ]

    # Collect all rule IDs from both batches
    all_rule_ids: list[str] = []
    seen: set = set()
    for key in ("MSL", "2321525470"):
        for rule in (results.get(key) or {}).get("rule_results", []):
            rid = rule.get("rule_id", "")
            if rid and rid not in seen:
                all_rule_ids.append(rid)
                seen.add(rid)

    if all_rule_ids:
        lines += [
            "| Rule | MSL Det Status | MSL Ollama | MSL Finding | #2321525470 Det Status | #2321525470 Ollama | #2321525470 Finding | Agree? |",
            "|---|---|---|---|---|---|---|---|",
        ]

        # Build lookup: rule_id → summary for each batch
        msl_by_id = {
            r.get("rule_id"): _rule_summary(r)
            for r in (results.get("MSL") or {}).get("rule_results", [])
        }
        other_by_id = {
            r.get("rule_id"): _rule_summary(r)
            for r in (results.get("2321525470") or {}).get("rule_results", [])
        }

        def _verdict_emoji(v, skipped):
            if skipped:
                return "⏭"
            if v == "AGREE":
                return "✅"
            if v == "DISAGREE":
                return "❌"
            return "❓"

        for rule_id in all_rule_ids:
            m = msl_by_id.get(rule_id, {})
            o = other_by_id.get(rule_id, {})
            m_det = m.get("det_status", "—")
            o_det = o.get("det_status", "—")
            m_v = _verdict_emoji(m.get("ollama_verdict"), m.get("ollama_skipped"))
            o_v = _verdict_emoji(o.get("ollama_verdict"), o.get("ollama_skipped"))
            m_f = (m.get("ollama_finding") or "")[:60]
            o_f = (o.get("ollama_finding") or "")[:60]
            # Cross-batch agreement: do both deterministic statuses agree?
            agree = "✅" if m_det == o_det else "⚠️"
            lines.append(
                f"| `{rule_id}` | `{m_det}` | {m_v} | {m_f} "
                f"| `{o_det}` | {o_v} | {o_f} | {agree} |"
            )

    lines += [
        "",
        "---",
        "",
        "## Timing Breakdown",
        "",
    ]

    for key in ("MSL", "2321525470"):
        r = results.get(key, {})
        if r.get("error"):
            continue
        label = BATCHES[key]["label"]
        rules = r.get("rule_results", [])
        lines += [
            f"### {key} — {label}",
            "",
            "| Rule | Det Status | Ollama Verdict | Ollama ms | Page |",
            "|---|---|---|---|---|",
        ]
        for rule in rules:
            s = _rule_summary(rule)
            ms = s.get("ollama_ms") or 0
            ms_str = f"{ms:.0f}" if ms else "cached/skip"
            verdict_str = s.get("ollama_verdict") or "SKIPPED"
            lines.append(
                f"| `{s['rule_id']}` | `{s['det_status']}` | {verdict_str} | {ms_str} | {s.get('source_page') or '—'} |"
            )

        total_ollama_ms = sum(
            (_rule_summary(r).get("ollama_ms") or 0) for r in rules
        )
        lines += [
            "",
            f"Total Ollama enrichment time: **{total_ollama_ms/1000:.1f}s**  |  "
            f"Total pipeline time: **{r.get('_elapsed_s', 0):.0f}s**",
            "",
        ]

    lines += [
        "---",
        "",
        "## Sensibility Summary",
        "",
        "### What Ollama Agreed With (deterministic rules it confirmed)",
        "",
    ]

    agreed = {}
    disagreed = {}
    for key in ("MSL", "2321525470"):
        for rule in (results.get(key) or {}).get("rule_results", []):
            s = _rule_summary(rule)
            rid = s["rule_id"]
            v = s.get("ollama_verdict")
            if s.get("ollama_skipped"):
                continue
            if v == "AGREE":
                agreed.setdefault(rid, []).append(key)
            elif v == "DISAGREE":
                disagreed.setdefault(rid, []).append(key)

    if agreed:
        lines.append("Rules where Ollama agreed with the deterministic engine:")
        lines.append("")
        for rid, batches in agreed.items():
            lines.append(f"- `{rid}` — agreed in: {', '.join(batches)}")
        lines.append("")

    lines += [
        "### Where Ollama Disagreed",
        "",
    ]
    if disagreed:
        for rid, batches in disagreed.items():
            lines.append(f"- `{rid}` — disagreed in: {', '.join(batches)}")
            for key in batches:
                for rule in (results.get(key) or {}).get("rule_results", []):
                    if rule.get("rule_id") == rid:
                        s = _rule_summary(rule)
                        lines.append(f"  - [{key}] Det: `{s['det_status']}` | Ollama says: {s.get('ollama_finding') or '—'}")
        lines.append("")
    else:
        lines.append("No disagreements recorded.")
        lines.append("")

    lines += [
        "### Cross-Format Consistency (MSL vs #2321525470)",
        "",
        "Rules where the deterministic engine gave DIFFERENT results on the two documents "
        "(expected for a different property — this is a sanity check, not a bug):",
        "",
    ]
    msl_by_id = {
        r.get("rule_id"): r.get("status")
        for r in (results.get("MSL") or {}).get("rule_results", [])
    }
    other_by_id = {
        r.get("rule_id"): r.get("status")
        for r in (results.get("2321525470") or {}).get("rule_results", [])
    }
    diffs = [
        rid for rid in set(msl_by_id) | set(other_by_id)
        if msl_by_id.get(rid) != other_by_id.get(rid)
    ]
    if diffs:
        for rid in sorted(diffs):
            lines.append(f"- `{rid}`: MSL=`{msl_by_id.get(rid, '—')}` vs #2321525470=`{other_by_id.get(rid, '—')}`")
    else:
        lines.append("All rules produced identical statuses on both documents.")
    lines.append("")

    lines += [
        "---",
        "",
        f"*Report generated by scripts/run_ollama_batch.py at {now}*",
        "",
    ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("  Ollama Sensibility Analysis — Batch QC Runner")
    print(f"  Service: {SERVICE_URL}")
    print(f"  Model:   llava:13b (via Ollama)")
    print("=" * 72)
    print()

    # Verify service is up
    try:
        import requests as _req
        health = _req.get(f"{SERVICE_URL}/health", timeout=5)
        if health.status_code != 200:
            print(f"ERROR: Service health check failed (HTTP {health.status_code})")
            sys.exit(1)
        ollama_ok = health.json().get("ollama", {}).get("model_available", False)
        if not ollama_ok:
            print("ERROR: Ollama model not available according to /health")
            sys.exit(1)
        print(f"✓ Service healthy  |  Ollama model available: llava:13b")
    except Exception as e:
        print(f"ERROR: Cannot reach service at {SERVICE_URL}: {e}")
        sys.exit(1)

    print()

    all_results: dict[str, dict] = {}

    for key, batch_cfg in BATCHES.items():
        label = batch_cfg["label"]
        print(f"{'─' * 60}")
        print(f"  Batch: {key}")
        print(f"  {label}")
        print(f"{'─' * 60}")

        t0 = time.monotonic()
        result = _post_qc(key, batch_cfg)
        elapsed = time.monotonic() - t0

        all_results[key] = result

        # Save raw JSON
        json_path = REPORTS_DIR / f"ollama_batch_{key}.json"
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  ✓ Raw JSON saved → {json_path}")

        if result.get("error"):
            print(f"  ✗ Batch failed: {result['error']}")
        else:
            total_rules = result.get("total_rules", 0)
            passed = result.get("passed", 0)
            failed = result.get("failed", 0)
            review = result.get("review", 0)
            rules = result.get("rule_results", [])
            ollama_enriched = sum(
                1 for r in rules
                if not (_rule_summary(r).get("ollama_skipped"))
            )
            oda = result.get("ollama_doc_analysis") or {}
            print(f"  ✓ Pipeline complete in {elapsed:.1f}s")
            print(f"     Pages:   {result.get('total_pages')}")
            print(f"     Rules:   {total_rules}  (PASS={passed}, FAIL={failed}, VERIFY/REVIEW={review})")
            print(f"     Ollama enriched rules: {ollama_enriched}/{total_rules}")
            print(f"     Ollama doc address: {oda.get('property_address', '—')}")
            print(f"     Ollama market quality: {oda.get('market_conditions_quality', '—')}")

        print()

    # Generate and save Markdown report
    md = _generate_report(all_results)
    md_path = REPORTS_DIR / "ollama_sensibility_report.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"{'=' * 72}")
    print(f"  Report saved → {md_path}")
    print(f"{'=' * 72}")
    print()

    # Print quick summary to console
    for key in ("MSL", "2321525470"):
        r = all_results.get(key, {})
        if r.get("error"):
            print(f"  {key}: ERROR — {r['error']}")
            continue
        rules = r.get("rule_results", [])
        agree_count = sum(
            1 for rule in rules
            if _rule_summary(rule).get("ollama_verdict") == "AGREE"
        )
        disagree_count = sum(
            1 for rule in rules
            if _rule_summary(rule).get("ollama_verdict") == "DISAGREE"
        )
        uncertain_count = sum(
            1 for rule in rules
            if _rule_summary(rule).get("ollama_verdict") == "UNCERTAIN"
        )
        skipped_count = sum(
            1 for rule in rules
            if _rule_summary(rule).get("ollama_skipped")
        )
        print(
            f"  {key}: AGREE={agree_count} DISAGREE={disagree_count} "
            f"UNCERTAIN={uncertain_count} SKIPPED={skipped_count}"
        )
    print()
    print(f"Open the report at:  {md_path}")


if __name__ == "__main__":
    main()
