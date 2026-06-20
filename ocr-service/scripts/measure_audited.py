"""Fast per-field extraction-accuracy measurement for the audited documents.

The DB-backed `run_baseline` is the system of record, but it extracts every test
doc and writes to Postgres — too heavy to iterate after each of the 9 fixes. This
script measures only the audited batches, in-process, with NO database: it runs the
real `run_full_extraction` (the same extractor the pipeline uses) and compares to
`config/ground_truth.yaml` with the same `_values_match` the baseline uses — so the
numbers are faithful, just scoped and fast (P-8: measure before/after every fix).

Usage:
    python scripts/measure_audited.py                # all audited batches
    python scripts/measure_audited.py "#2321525499"  # one batch
    python scripts/measure_audited.py --label after-val1   # tag the run in output
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extraction.layers.orchestrator import run_full_extraction
from app.services.baseline_service import _values_match, GROUND_TRUTH_PATH, UPLOADS_ROOT

# The batches added/used for the 9-fix audit measurement.
AUDITED = ["#2321525499", "#2321525470", "#2321525427", "#2321525505"]


def _load_batches() -> dict:
    raw = yaml.safe_load(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    return raw.get("batches", {})


def _measure_doc(pdf_path: Path, fields: dict) -> list[tuple[str, str, str, bool, bool]]:
    """Return [(field, expected, extracted, correct, is_absent), ...]."""
    rs = run_full_extraction(pdf_path, document_type="appraisal_report",
                             use_paddle=False, use_llm=False, use_embeddings=False)
    # sketch_living_area is produced by a QC overlay (transaction.py), not the
    # orchestrator — fold it in so the measurement reflects the real combined output.
    if "sketch_living_area" in fields:
        from app.extraction.sketch_extractor import extract_sketch_gla
        sk = extract_sketch_gla(pdf_path).get("sketch_living_area")
        if sk:
            r = rs.get("sketch_living_area")
            if r is not None:
                r.value = sk
    rows = []
    for fname, spec in fields.items():
        is_absent = bool(spec.get("absent", False))
        expected = spec.get("value")
        res = rs.get(fname)
        extracted = res.value if (res and res.found) else None
        if is_absent:
            correct = extracted is None
        else:
            correct = _values_match(extracted, expected)
        rows.append((fname, "<absent>" if is_absent else expected, extracted, correct, is_absent))
    return rows


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    label = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--label=")), "")
    wanted = args or AUDITED
    batches = _load_batches()

    grand_correct = grand_total = 0
    for bkey in wanted:
        batch = batches.get(bkey)
        if not batch:
            print(f"!! {bkey}: not in ground_truth.yaml")
            continue
        appr = batch.get("documents", {}).get("appraisal")
        if not appr:
            continue
        pdf = UPLOADS_ROOT / appr["path"]
        if not pdf.exists():
            print(f"!! {bkey}: PDF missing at {pdf}")
            continue
        print(f"\n=== {bkey}  ({pdf.name})  label={label or '-'} ===")
        rows = _measure_doc(pdf, appr.get("fields", {}))
        testable = [r for r in rows if not r[4]]
        correct = sum(1 for r in testable if r[3])
        for fname, exp, ext, ok, absent in rows:
            mark = "OK " if ok else "XX "
            print(f"  {mark} {fname:28} expected={str(exp)[:24]:24} got={str(ext)[:32]}")
        print(f"  -- {bkey}: {correct}/{len(testable)} = {100*correct/max(1,len(testable)):.0f}%")
        grand_correct += correct
        grand_total += len(testable)

    print(f"\n==== TOTAL: {grand_correct}/{grand_total} = "
          f"{100*grand_correct/max(1,grand_total):.1f}% ====")


if __name__ == "__main__":
    main()
