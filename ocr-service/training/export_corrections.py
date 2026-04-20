import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.feedback_store import feedback_store


def export_jsonl(output_path: Path, limit: int = 1000) -> int:
    rows = feedback_store.fetch_recent_incorrect(limit=limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            record = {
                "field_name": row.get("field_name"),
                "predicted_value": row.get("predicted_value"),
                "corrected_value": row.get("corrected_value"),
                "created_at": row.get("created_at"),
            }
            f.write(json.dumps(record) + "\n")
            count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export feedback corrections to JSONL")
    parser.add_argument(
        "--output",
        type=str,
        default="training/artifacts/field_corrections.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Max records to export")
    args = parser.parse_args()

    total = export_jsonl(Path(args.output), limit=args.limit)
    print(f"Exported {total} correction rows to {args.output}")
