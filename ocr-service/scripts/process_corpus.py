"""
Process the full document corpus end-to-end and persist every stage to the DB.

For each unique PDF under uploads/ (deduped by content hash), runs the complete
pipeline — classify, extract (layered orchestrator), validate, route, persist —
via app.services.pipeline_runner.process_and_persist. This is the "full and
final" demo run: one run_id, every adaptive_* table populated, every document
accounted for.

Document type is taken from the folder layout when present
(/appraisal/, /engagement/, /contract/); otherwise the classifier decides.

Usage:
    cd ocr-service
    conda run -n apprisal python scripts/process_corpus.py [run_label] [--limit N]
"""

import sys
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.disable(logging.WARNING)  # keep stdout readable; pipeline logs are INFO

from app.services.pipeline_runner import process_and_persist

UPLOADS = Path(__file__).parent.parent.parent / "uploads"

_FOLDER_TYPE = {
    "appraisal": "appraisal_report",
    "engagement": "engagement_letter",
    "contract": "sales_contract",
}


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def _folder_type(path: Path):
    parts = {p.lower() for p in path.parts}
    for key, dtype in _FOLDER_TYPE.items():
        if key in parts:
            return dtype
    return None  # let the classifier decide


def collect() -> list:
    seen = set()
    docs = []
    for pdf in sorted(UPLOADS.rglob("*.pdf")):
        h = _hash(pdf)
        if h in seen:
            continue
        seen.add(h)
        docs.append((pdf, _folder_type(pdf)))
    return docs


def process_one(pdf: Path, dtype, run_label: str) -> dict:
    try:
        s = process_and_persist(pdf, document_type=dtype, run_id=run_label, store=True)
        return {"ok": True, **s}
    except Exception as exc:
        return {"ok": False, "document_id": pdf.name, "error": str(exc)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_label = args[0] if args else f"demo-final-{time.strftime('%Y%m%d-%H%M%S')}"
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    docs = collect()
    if limit:
        docs = docs[:limit]

    print(f"Corpus run '{run_label}': {len(docs)} unique documents\n")
    t0 = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(process_one, pdf, dt, run_label): pdf for pdf, dt in docs}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            if r["ok"]:
                v = r["validation"]
                print(f"  ✓ {r['document_id'][:48]:<48} {r['document_type']:<18} "
                      f"{r['fields_found']:>3}/{r['fields_total']} fields  "
                      f"val(✗{v['fail']}/!{v['warning']}/✓{v['pass']})  {r['elapsed_ms']:>6}ms")
            else:
                print(f"  ✗ {r['document_id'][:48]:<48} ERROR: {r['error'][:50]}")

    ok = [r for r in results if r["ok"]]
    total_found = sum(r["fields_found"] for r in ok)
    by_type = {}
    for r in ok:
        by_type.setdefault(r["document_type"], []).append(r["fields_found"])

    print("\n" + "=" * 78)
    print(f"DONE: {len(ok)}/{len(results)} ok | {total_found} field extractions | {time.time()-t0:.0f}s")
    for dt, counts in sorted(by_type.items()):
        print(f"  {dt:<20} docs={len(counts):>2}  avg_fields={sum(counts)//max(len(counts),1):>3}")
    print(f"run_id = {run_label}")


if __name__ == "__main__":
    main()
