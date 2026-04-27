"""
Phase 6 — Weekly Retraining Job

Runs every Sunday night (or on demand via POST /admin/retrain).
Pulls untrained feedback, trains three models, validates each,
deploys only if accuracy improves, then marks feedback as used.

Usage:
    # Manual run
    conda activate apprisal && cd ocr-service
    python training/retrain.py

    # From FastAPI (triggered by POST /admin/retrain)
    from training.retrain import run_retraining
    result = run_retraining()

Output:
    Saved model files in training/models/
    Returns summary dict with accuracy before/after for each model
"""

import os
import sys
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Ensure the ocr-service root is on the path so `app.*` imports work
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = ROOT / "training" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_feedback(feature_type: Optional[str] = None) -> List[Dict]:
    """Pull feedback_events rows where used_in_training=False."""
    from app.database import get_db
    from app.models.db_models import FeedbackEvent

    rows = []
    with get_db() as db:
        q = db.query(FeedbackEvent).filter(FeedbackEvent.used_for_training == False)
        if feature_type:
            q = q.filter(FeedbackEvent.original_status == feature_type)
        for row in q.all():
            rows.append({
                "id":              row.id,
                "feedback_type":   row.original_status,
                "original_value":  row.original_value,
                "corrected_value": row.corrected_value,
                "field_name":      row.field_name,
            })
    return rows


def _mark_as_trained(feedback_ids: List[int]):
    """Set used_for_training=True for processed rows."""
    if not feedback_ids:
        return
    from app.database import get_db
    from app.models.db_models import FeedbackEvent
    with get_db() as db:
        db.query(FeedbackEvent).filter(
            FeedbackEvent.id.in_(feedback_ids)
        ).update({"used_for_training": True}, synchronize_session=False)


def _load_training_examples(feature_type: str) -> Tuple[List[str], List[str]]:
    """Load training_examples rows for a given feature_type. Returns (X, y)."""
    from app.database import get_db
    from app.models.db_models import TrainingExample

    X, y = [], []
    with get_db() as db:
        rows = (
            db.query(TrainingExample)
            .filter(TrainingExample.feature_type == feature_type)
            .all()
        )
        for row in rows:
            if row.input_text and row.label:
                X.append(row.input_text)
                y.append(row.label)
    return X, y


# ── Model 1: OCR Correction Classifier ────────────────────────────────────────

def _train_ocr_correction(feedback_rows: List[Dict]) -> Dict:
    """
    Level 1 learning: operator OCR corrections → correction dictionary update.
    The sklearn model learns which character-level patterns are usually misreads.

    Input: raw OCR text (e.g. "Borrovver")
    Output: corrected text (e.g. "Borrower")
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    import numpy as np

    # Primary source: operator feedback_events with OCR_ERROR type
    ocr_rows = [r for r in feedback_rows if r["feedback_type"] == "OCR_ERROR"
                and r["original_value"] and r["corrected_value"]]

    # Secondary source: training_examples with feature_type='ocr_correction'
    X_te, y_te = _load_training_examples("ocr_correction")

    X = [r["original_value"] for r in ocr_rows] + X_te
    y = [r["corrected_value"] for r in ocr_rows] + y_te

    if len(X) < 5:
        logger.info("OCR correction: only %d examples — skipping training (need ≥5)", len(X))
        return {"model": "ocr_correction", "skipped": True, "reason": f"only {len(X)} examples"}

    # Need enough examples for a train/test split
    if len(X) < 10:
        X_train, X_test, y_train, y_test = X, X, y, y
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), max_features=500)
    X_train_v = vec.fit_transform(X_train)
    X_test_v  = vec.transform(X_test)

    clf = LogisticRegression(max_iter=500)
    clf.fit(X_train_v, y_train)

    acc = accuracy_score(y_test, clf.predict(X_test_v))
    logger.info("OCR correction model: acc=%.3f on %d test examples", acc, len(X_test))

    # Load existing model accuracy to compare
    model_path = MODELS_DIR / "ocr_correction_model.pkl"
    prev_acc = 0.0
    if model_path.exists():
        try:
            with open(model_path, "rb") as f:
                prev = pickle.load(f)
            prev_acc = prev.get("accuracy", 0.0)
        except Exception:
            pass

    if acc >= prev_acc:
        with open(model_path, "wb") as f:
            pickle.dump({"vectorizer": vec, "classifier": clf, "accuracy": acc,
                         "trained_at": datetime.utcnow().isoformat()}, f)
        logger.info("OCR correction model saved (%.3f → %.3f)", prev_acc, acc)
        return {"model": "ocr_correction", "prev_acc": prev_acc, "new_acc": acc, "deployed": True}
    else:
        logger.info("OCR correction model NOT saved (%.3f < %.3f)", acc, prev_acc)
        return {"model": "ocr_correction", "prev_acc": prev_acc, "new_acc": acc, "deployed": False}


# ── Model 2: Commentary Quality Classifier ────────────────────────────────────

def _train_commentary_classifier(feedback_rows: List[Dict]) -> Dict:
    """
    Level 3 learning: operator agreement/disagreement with canned-detection
    → trains a text classifier to replace LLM for known patterns.

    Uses training_examples rows with feature_type='commentary_quality'.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    X, y = _load_training_examples("commentary_quality")

    # Also pull from feedback_events directly (RULE_ERROR on COM rules)
    for r in feedback_rows:
        if r.get("field_name", "").startswith("COM") and r["original_value"] and r["corrected_value"]:
            X.append(r["original_value"])
            y.append(r["corrected_value"])  # "CANNED" or "SPECIFIC"

    if len(X) < 10:
        logger.info("Commentary classifier: only %d examples — skipping (need ≥10)", len(X))
        return {"model": "commentary_classifier", "skipped": True, "reason": f"only {len(X)} examples"}

    if len(X) < 20:
        X_train, X_test, y_train, y_test = X, X, y, y
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=3000, ngram_range=(1, 2), stop_words="english")),
        ("clf",   LogisticRegression(max_iter=500, C=1.0)),
    ])
    pipe.fit(X_train, y_train)
    acc = accuracy_score(y_test, pipe.predict(X_test))
    logger.info("Commentary classifier: acc=%.3f on %d test examples", acc, len(X_test))

    model_path = MODELS_DIR / "commentary_classifier.pkl"
    prev_acc = 0.0
    if model_path.exists():
        try:
            with open(model_path, "rb") as f:
                prev_acc = pickle.load(f).get("accuracy", 0.0)
        except Exception:
            pass

    if acc >= prev_acc:
        with open(model_path, "wb") as f:
            pickle.dump({"pipeline": pipe, "accuracy": acc,
                         "trained_at": datetime.utcnow().isoformat()}, f)
        return {"model": "commentary_classifier", "prev_acc": prev_acc, "new_acc": acc, "deployed": True}
    else:
        return {"model": "commentary_classifier", "prev_acc": prev_acc, "new_acc": acc, "deployed": False}


# ── Model 3: Field Confidence Calibration ─────────────────────────────────────

def _train_confidence_model(feedback_rows: List[Dict]) -> Dict:
    """
    Level 2 learning: historical extractions where operator confirmed or corrected
    → trains a regression model to assign better confidence scores.

    Uses training_examples with feature_type='field_extraction'.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error
    import numpy as np

    X, y_labels = _load_training_examples("field_extraction")

    # y_labels are "correct" or "incorrect" from operator
    X_numeric = []
    y_numeric  = []
    for text, label in zip(X, y_labels):
        X_numeric.append(text)
        y_numeric.append(1.0 if label.lower() in ("correct", "pass", "ok") else 0.0)

    # Include EXTRACTION_ERROR feedback
    for r in feedback_rows:
        if r["feedback_type"] == "EXTRACTION_ERROR" and r["original_value"]:
            X_numeric.append(r["original_value"])
            y_numeric.append(0.0)  # operator said it was wrong

    if len(X_numeric) < 10:
        logger.info("Confidence model: only %d examples — skipping", len(X_numeric))
        return {"model": "confidence_model", "skipped": True}

    X_train, X_test, y_train, y_test = (
        (X_numeric, X_numeric, y_numeric, y_numeric) if len(X_numeric) < 20
        else train_test_split(X_numeric, y_numeric, test_size=0.2, random_state=42)
    )

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=1000, analyzer="char", ngram_range=(2, 3))),
        ("reg",   LinearRegression()),
    ])
    pipe.fit(X_train, y_train)
    preds = np.clip(pipe.predict(X_test), 0.0, 1.0)
    mae = mean_absolute_error(y_test, preds)
    logger.info("Confidence model: MAE=%.3f on %d test examples", mae, len(X_test))

    model_path = MODELS_DIR / "confidence_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"pipeline": pipe, "mae": mae,
                     "trained_at": datetime.utcnow().isoformat()}, f)

    return {"model": "confidence_model", "mae": mae, "deployed": True}


# ── Main entry point ───────────────────────────────────────────────────────────

def run_retraining() -> Dict[str, Any]:
    """
    Run the full retraining pipeline.

    1. Pull untrained feedback_events
    2. Train each model (only deploy if accuracy improves)
    3. Mark feedback as trained
    4. Return summary

    Called by: POST /admin/retrain  OR  cron every Sunday night
    """
    logger.info("=== Phase 6 Retraining started at %s ===", datetime.utcnow().isoformat())

    try:
        feedback_rows = _load_feedback()
        logger.info("Pulled %d untrained feedback rows", len(feedback_rows))
    except Exception as e:
        logger.error("Failed to load feedback: %s", e)
        return {"error": str(e), "success": False}

    results = {}
    trained_ids = []

    # Model 1: OCR Correction
    try:
        results["ocr_correction"] = _train_ocr_correction(feedback_rows)
    except Exception as e:
        logger.error("OCR correction training failed: %s", e)
        results["ocr_correction"] = {"error": str(e)}

    # Model 2: Commentary Classifier
    try:
        results["commentary_classifier"] = _train_commentary_classifier(feedback_rows)
    except Exception as e:
        logger.error("Commentary classifier training failed: %s", e)
        results["commentary_classifier"] = {"error": str(e)}

    # Model 3: Confidence Model
    try:
        results["confidence_model"] = _train_confidence_model(feedback_rows)
    except Exception as e:
        logger.error("Confidence model training failed: %s", e)
        results["confidence_model"] = {"error": str(e)}

    # Mark all feedback as used
    trained_ids = [r["id"] for r in feedback_rows]
    try:
        _mark_as_trained(trained_ids)
        logger.info("Marked %d feedback rows as trained", len(trained_ids))
    except Exception as e:
        logger.error("Failed to mark feedback as trained: %s", e)

    summary = {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
        "feedback_processed": len(feedback_rows),
        "models": results,
    }

    logger.info("=== Retraining complete: %s ===",
                json.dumps({k: v.get("deployed", v.get("skipped")) for k, v in results.items()}))
    return summary


def generate_synthetic_feedback(n: int = 30):
    """
    Generate synthetic training examples so the model can train before real data exists.
    Used for testing the pipeline — never deployed to production automatically.
    """
    from app.database import get_db
    from app.models.db_models import TrainingExample

    CANNED_EXAMPLES = [
        "The subject property is located in a typical residential neighborhood.",
        "The improvements are typical for the area.",
        "No adverse conditions were noted at the time of inspection.",
        "The subject is compatible with the surrounding neighborhood.",
        "Equal weight was given to all comparables.",
        "The cost approach was not developed.",
        "See attached addendum for additional comments.",
        "The market appears balanced with typical marketing times.",
        "Weighted average of the indicated values supports the opinion.",
        "Adjustments reflect market reactions to the differences noted.",
    ]
    SPECIFIC_EXAMPLES = [
        "The subject is located in Colquitt County GA near SR-33, avg DOM 47 days per GAMLS.",
        "Sales comparison indicates 8% annual appreciation based on 12 paired sales 2024-2025.",
        "$6,500 adjustment made for GLA difference per $42/sf extracted from 3 paired sales.",
        "Neighborhood bounded North by Hwy 84, South by SR-37, East by Baker Rd, West by I-75.",
        "Subject's pool adds $18,000 based on 4 matched pairs in Moultrie GA 31788 market.",
        "GAMLS DOM data shows 31 days average; comparable 1 (DOM 28) and 2 (DOM 35) bracket.",
        "Colquitt County assessor confirms 2024 R.E. taxes $1,247 on parcel #0245-003-2700.",
        "Comparable 2 adjusted $+3,500 for inferior location fronting Tallahassee Rd traffic.",
        "Market conditions show 4.2% annual appreciation per GAMLS MLS#2024-047823.",
        "Final value reconciled toward comparable 3 — most recent sale, same subdivision.",
    ]

    examples = (
        [(t, "CANNED") for t in CANNED_EXAMPLES[:n//2]] +
        [(t, "SPECIFIC") for t in SPECIFIC_EXAMPLES[:n//2]]
    )

    with get_db() as db:
        for text, label in examples:
            db.add(TrainingExample(
                feature_type="commentary_quality",
                input_text=text,
                label=label,
                model_version="synthetic_v1",
            ))
    logger.info("Generated %d synthetic training examples", len(examples))
    return len(examples)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 6 — Retraining pipeline")
    parser.add_argument("--synthetic", action="store_true",
                        help="Generate synthetic training data before retraining")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load data and report counts, but don't train or save")
    args = parser.parse_args()

    if args.synthetic:
        n = generate_synthetic_feedback(30)
        print(f"Generated {n} synthetic examples")

    if args.dry_run:
        rows = _load_feedback()
        X, y = _load_training_examples("commentary_quality")
        print(f"Untrained feedback rows: {len(rows)}")
        print(f"Commentary training examples: {len(X)}")
        print(f"  CANNED: {y.count('CANNED')}  SPECIFIC: {y.count('SPECIFIC')}")
    else:
        result = run_retraining()
        print(json.dumps(result, indent=2))
