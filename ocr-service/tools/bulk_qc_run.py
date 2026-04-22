import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import httpx


def list_pdfs(root: Path) -> List[Path]:
    return sorted([p for p in root.rglob("*.pdf") if p.is_file()])

def _normalize_name(name: str) -> str:
    n = name.lower()
    n = n.replace(".pdf", "")
    n = re.sub(r"\b(order\s*form|order|engagement|appraisal|report)\b", " ", n)
    # remove common street suffixes / directionals to make pairing robust
    n = re.sub(
        r"\b(st|street|rd|road|dr|drive|ln|lane|ave|avenue|blvd|boulevard|cir|circle|ct|court|trl|trail|tr|way|hwy|se|sw|ne|nw|n|s|e|w)\b",
        " ",
        n,
    )
    n = re.sub(r"[_\-]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _key_from_filename(filename: str) -> str:
    """
    Build a fuzzy join key from a file name.
    Good enough for current uploads structure:
    - appraisal: "2307 Merrily Cir N.pdf"
    - engagement/order: "2307 Merrily order form.pdf"
    """
    n = _normalize_name(filename)
    parts = n.split()
    # Prefer "number + next 1-2 words" as stable join key.
    if parts and parts[0].isdigit():
        return " ".join(parts[:3]) if len(parts) >= 3 else " ".join(parts[:2])
    return " ".join(parts[:3]) if len(parts) >= 3 else n


def build_pair_map(pdfs: List[Path]) -> Dict[str, Dict[str, List[Path]]]:
    """
    Returns:
      { key: { "appraisal": [...], "engagement": [...] } }
    """
    grouped: Dict[str, Dict[str, List[Path]]] = {}
    for p in pdfs:
        key = _key_from_filename(p.name)
        bucket = grouped.setdefault(key, {"appraisal": [], "engagement": []})
        lower_path = str(p).lower()
        if "/engagement/" in lower_path:
            bucket["engagement"].append(p)
        else:
            bucket["appraisal"].append(p)
    return grouped


def run_qc(base_url: str, pdf_path: Path, timeout_s: int) -> Dict[str, Any]:
    with httpx.Client(timeout=timeout_s) as client:
        with pdf_path.open("rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            resp = client.post(f"{base_url.rstrip('/')}/qc/process", files=files)
            resp.raise_for_status()
            return resp.json()

def run_qc_paired(base_url: str, appraisal_pdf: Path, engagement_pdf: Path, timeout_s: int) -> Dict[str, Any]:
    with httpx.Client(timeout=timeout_s) as client:
        with appraisal_pdf.open("rb") as f_app, engagement_pdf.open("rb") as f_eng:
            files = {
                "file": (appraisal_pdf.name, f_app, "application/pdf"),
                "engagement_letter": (engagement_pdf.name, f_eng, "application/pdf"),
            }
            resp = client.post(f"{base_url.rstrip('/')}/qc/process", files=files)
            resp.raise_for_status()
            return resp.json()


def summarize_one(result: Dict[str, Any]) -> Dict[str, Any]:
    rules = result.get("rule_results") or []
    failed = [r for r in rules if r.get("status") == "FAIL"]
    verify = [r for r in rules if r.get("status") in {"VERIFY", "WARNING"}]
    return {
        "success": result.get("success"),
        "processing_time_ms": result.get("processing_time_ms"),
        "total_rules": result.get("total_rules"),
        "passed": result.get("passed"),
        "failed": result.get("failed"),
        "verify": result.get("verify"),
        "failed_rules": [{"id": r.get("rule_id"), "msg": r.get("message")} for r in failed],
        "verify_rules": [{"id": r.get("rule_id"), "msg": r.get("message")} for r in verify],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk run /qc/process across all PDFs")
    parser.add_argument("--uploads", type=str, default="../uploads", help="Uploads root directory")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:5001", help="OCR service base URL")
    parser.add_argument("--timeout", type=int, default=240, help="Per-document timeout (seconds)")
    parser.add_argument("--output", type=str, default="tools/artifacts/bulk_qc_report.json", help="Output JSON")
    args = parser.parse_args()

    uploads_root = Path(args.uploads).resolve()
    pdfs = list_pdfs(uploads_root)
    pairs = build_pair_map(pdfs)
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "uploads_root": str(uploads_root),
        "base_url": args.base_url,
        "total_pdfs": len(pdfs),
        "pair_keys": len(pairs),
        "files": [],
        "errors": [],
    }

    # Only run QC for appraisal PDFs. For each appraisal, attach the best matching engagement/order PDF.
    appraisal_items: List[Dict[str, Any]] = []
    for key, bucket in pairs.items():
        for a in bucket["appraisal"]:
            appraisal_items.append(
                {
                    "key": key,
                    "appraisal": a,
                    "engagement": bucket["engagement"][0] if bucket["engagement"] else None,
                    "engagement_candidates": [str(x) for x in bucket["engagement"]],
                }
            )

    for idx, item in enumerate(appraisal_items, start=1):
        a: Path = item["appraisal"]
        e: Path | None = item["engagement"]
        print(f"[{idx}/{len(appraisal_items)}] QC appraisal: {a.name}", flush=True)
        if e:
            print(f"  pairing key='{item['key']}' engagement='{e.name}'", flush=True)
        else:
            print(f"  pairing key='{item['key']}' engagement=MISSING", flush=True)

        try:
            if e:
                result = run_qc_paired(args.base_url, a, e, args.timeout)
            else:
                result = run_qc(args.base_url, a, args.timeout)
            report["files"].append(
                {
                    "pair_key": item["key"],
                    "appraisal_file": str(a),
                    "engagement_file": str(e) if e else None,
                    "engagement_candidates": item["engagement_candidates"],
                    "summary": summarize_one(result),
                }
            )
            s = report["files"][-1]["summary"]
            print(
                f"  -> ok success={s.get('success')} failed={s.get('failed')} verify={s.get('verify')} time_ms={s.get('processing_time_ms')}",
                flush=True,
            )
        except Exception as ex:
            report["errors"].append(
                {
                    "pair_key": item["key"],
                    "appraisal_file": str(a),
                    "engagement_file": str(e) if e else None,
                    "error": str(ex),
                }
            )
            print(f"  -> error {ex}", flush=True)

    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote report to {out_path}")
    print(
        f"Total PDFs discovered: {len(pdfs)} | Appraisals processed: {len(report['files'])} | Errors: {len(report['errors'])}"
    )


if __name__ == "__main__":
    main()

