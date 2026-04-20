import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.feedback_store import feedback_store


def build_fewshot_examples_from_corrections(limit: int = 50) -> list[dict]:
    rows = feedback_store.fetch_recent_incorrect(limit=limit)
    examples = []
    for row in rows:
        predicted = row.get("predicted_value")
        corrected = row.get("corrected_value")
        if not corrected:
            continue
        examples.append(
            {
                "field": row.get("field_name"),
                "bad_extraction": predicted,
                "correct_answer": corrected,
                "pattern_learned": f"When model said '{predicted}', correct was '{corrected}'",
                "created_at": row.get("created_at"),
            }
        )
    return examples


def save_examples(examples: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(examples),
        "examples": examples,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build few-shot examples from feedback")
    parser.add_argument("--limit", type=int, default=50, help="Max corrections to include")
    parser.add_argument(
        "--output",
        type=str,
        default="training/artifacts/fewshot_examples.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    examples = build_fewshot_examples_from_corrections(limit=args.limit)
    save_examples(examples, Path(args.output))
    print(f"Saved {len(examples)} few-shot examples to {args.output}")
