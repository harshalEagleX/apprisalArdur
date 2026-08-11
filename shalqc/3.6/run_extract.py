"""Run the UAD 3.6 vision extraction end-to-end on a report and dump the result.

Usage:
    PYTHONPATH=. python 3.6/run_extract.py <pdf> [out_prefix]
"""
from __future__ import annotations

import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    pdf = sys.argv[1] if len(sys.argv) > 1 else "3.6/Email - AppraisalArdur - Outlook (1).pdf"
    prefix = sys.argv[2] if len(sys.argv) > 2 else "3.6/_run"

    from app.extraction.merge import run_extraction
    from app.extraction.schema import schema_loader

    t0 = time.time()
    report: dict = {}
    fields = run_extraction(pdf, schema=schema_loader, vision_report=report)
    report["_runtime_s"] = round(time.time() - t0, 1)
    report["_fields"] = {
        f.canonical_name: {"value": f.value, "source": str(f.source),
                           "confidence": f.confidence, "page": f.page}
        for f in fields.found_fields()
    }
    with open(f"{prefix}.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)

    print(f"\nDONE — {len(fields.found_fields())} fields in {report['_runtime_s']}s")
    budget = report.get("budget") or {}
    print(f"cost ${budget.get('spent_usd', 0):.4f} of ${budget.get('cap_usd', 0):.2f} "
          f"over {budget.get('calls', 0)} calls")
    print(f"wrote {prefix}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
