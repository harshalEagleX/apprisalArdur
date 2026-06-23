"""
Day 4 — Seed test set and run baseline measurement.

Run:
    conda run -n shal python scripts/seed_and_baseline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.baseline_service import (
    print_baseline_report,
    run_baseline,
    seed_test_set,
)

if __name__ == "__main__":
    print("Seeding test set from ground_truth.yaml...")
    seeded = seed_test_set(force=False)
    print(f"  {seeded} new documents added to test set")

    print("\nRunning baseline measurement...")
    report = run_baseline(label="Week1-Day4-Baseline")
    print_baseline_report(report)
