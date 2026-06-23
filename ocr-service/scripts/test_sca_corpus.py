"""Full transaction QC over a set of folders, with SCA results prioritized.

Runs the SAME entry point production uses (run_transaction_qc -> run_qc), so this
proves SCA fires inside the integrated pipeline (not a standalone module). For each
folder it prints the overall counts, then EVERY Sales-Comparison (SCA) rule result,
plus the comparable-photo vision fields.

Usage:
    cd ocr-service
    conda run -n shal python scripts/test_sca_corpus.py ../uploads/sort
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.disable(logging.WARNING)

from app.qc.transaction import run_transaction_qc  # noqa: E402

_VISION_FIELDS = ("comp_photo_pages", "vision_enabled", "comp_photo_building",
                  "comp_photo_distress", "comp_photo_mls_text", "comp_photo_condition")


def _folders(root: Path):
    return sorted([d for d in root.iterdir() if d.is_dir()])


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "../uploads/sort")
    folders = _folders(root)
    print(f"=== Full QC over {len(folders)} transactions in {root} (SCA prioritized) ===\n")
    grand = {}
    for folder in folders:
        t = time.time()
        try:
            rep = run_transaction_qc(folder, persist=False)
        except Exception as exc:
            print(f"### {folder.name}: ERROR {exc}\n")
            continue
        ctx = getattr(rep, "_ctx", None)
        sca = [r for r in rep.results if r.section == "sales_comparison"]
        sca_counts = {}
        for r in sca:
            sca_counts[r.status.name] = sca_counts.get(r.status.name, 0) + 1
        print(f"### {folder.name}  ({time.time()-t:.0f}s)")
        print(f"    overall: {rep.overall.name} | {rep.counts()}")
        print(f"    SCA: {len(sca)} results -> {sca_counts}")
        # SCA detail, non-PASS first so issues are visible
        order = {"FAIL": 0, "HOLD": 1, "VERIFY": 2, "SKIPPED": 3, "NOT_APPLICABLE": 4, "PASS": 5}
        for r in sorted(sca, key=lambda r: (order.get(r.status.name, 9), r.rule_id)):
            msg = (r.message or "").strip().replace("\n", " ")
            print(f"      {r.rule_id:10} {r.status.name:14} {msg[:80]}")
        print()
        for k, v in rep.counts().items():
            grand[k] = grand.get(k, 0) + v
    print(f"=== GRAND TOTAL across {len(folders)} transactions: {grand} ===")


if __name__ == "__main__":
    main()
