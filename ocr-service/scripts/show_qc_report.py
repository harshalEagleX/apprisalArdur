"""
Print the persisted QC report for a transaction as a readable document.

Usage:
    cd ocr-service
    conda run -n shal python scripts/show_qc_report.py "sort/#2321525505"
    conda run -n shal python scripts/show_qc_report.py --list
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.disable(logging.WARNING)


def _list_transactions():
    from app.database import get_db
    from app.models.db_models import ValidationResultRow
    with get_db() as session:
        rows = (session.query(ValidationResultRow.transaction_id)
                .filter(ValidationResultRow.transaction_id.isnot(None))
                .distinct().all())
    for (tid,) in sorted(r for r in rows):
        print(tid)


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        _list_transactions()
        return
    from app.qc.report import transaction_report, render_report_text
    rep = transaction_report(sys.argv[1])
    if rep["rule_count"] == 0:
        print(f"No QC results for: {sys.argv[1]}  (run scripts/run_qc_corpus.py first)")
        return
    print(render_report_text(rep))


if __name__ == "__main__":
    main()
