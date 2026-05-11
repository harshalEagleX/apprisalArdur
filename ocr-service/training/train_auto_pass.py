"""
P3.5 — Auto-pass calibration model training script.

Run this script to train or retrain the auto-pass ML model:

    python training/train_auto_pass.py            # normal run
    python training/train_auto_pass.py --force    # train even with < MIN_EXAMPLES

The script:
  1. Reads all labelled rows from `auto_pass_examples`.
  2. Trains a LogisticRegression (< 100 examples) or RandomForest (>= 100).
  3. Cross-validates to measure accuracy.
  4. Writes the model to training/models/auto_pass_model.pkl.
  5. Writes metadata to training/models/auto_pass_model_meta.json.
  6. Marks the used rows as `used_in_training = True`.

Schedule: run nightly via cron or the /admin/retrain endpoint.
"""

import os
import sys
import json
import logging

# Ensure the project root is on the Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_auto_pass")


def main():
    force = "--force" in sys.argv

    from app.services.auto_pass_calibration import (
        train,
        get_model_metadata,
        MIN_EXAMPLES_TO_TRAIN,
    )

    logger.info("Auto-pass calibration training started (force=%s)", force)

    result = train(force=force)

    if result.get("trained"):
        logger.info(
            "Training complete: %d examples, model=%s, accuracy=%s",
            result.get("examples_used", 0),
            result.get("model_type", "?"),
            f"{result['accuracy']:.4f}" if result.get("accuracy") else "N/A",
        )
    else:
        logger.info("Training skipped: %s", result.get("reason", "unknown"))
        if not force:
            meta = get_model_metadata()
            avail = result.get("examples_available", 0)
            logger.info(
                "Currently %d / %d examples available. "
                "Reviewer feedback is being collected — model will train automatically "
                "once the threshold is reached.",
                avail, MIN_EXAMPLES_TO_TRAIN,
            )

    print(json.dumps(result, indent=2))
    return 0 if result.get("trained") or not force else 1


if __name__ == "__main__":
    sys.exit(main())
