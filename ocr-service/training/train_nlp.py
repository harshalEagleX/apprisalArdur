"""
NLP Model Training for Appraisal Commentary Analysis

Two modes:
  1. ollama-label  — use llava:13b to auto-label a CSV of commentary snippets.

  2. canned        — train (or retrain) the sklearn pipeline on an already-labelled CSV.

Usage:
    # Step 1: pull the model (one-time)
    ollama pull llava:13b

    # Step 2: auto-label your raw commentary CSV
    python train_nlp.py --task ollama-label --data raw_commentary.csv

    # Step 3: train the fast sklearn model on labelled data
    python train_nlp.py --task canned --data labelled_commentary.csv
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("../app/models/nlp")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Ollama-based auto-labelling
# ---------------------------------------------------------------------------

def auto_label_with_ollama(input_csv: str, output_csv: str = "labelled_commentary.csv"):
    """
    Use llava:13b to label raw commentary snippets as CANNED/SPECIFIC.
    Saves a new CSV with an 'is_canned' column (1=canned, 0=specific).

    Input CSV must have a 'text' column.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas required: pip install pandas")
        return

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from app.services.ollama_service import classify_commentary, is_ollama_available
    except ImportError as e:
        logger.error("Cannot import ollama_service: %s", e)
        return

    if not is_ollama_available():
        logger.error(
            "Ollama is not running or llava:13b is not loaded.\n"
            "Run:  ollama pull llava:13b\n"
            "Then: ollama serve"
        )
        return

    df = pd.read_csv(input_csv)
    if "text" not in df.columns:
        logger.error("Input CSV must have a 'text' column")
        return

    logger.info("Auto-labelling %d rows using llava:13b ...", len(df))
    labels = []
    for i, row in df.iterrows():
        text = str(row["text"])
        result = classify_commentary(text)
        label = 1 if result is True else (0 if result is False else None)
        labels.append(label)
        if (i + 1) % 10 == 0:
            logger.info("  Labelled %d/%d", i + 1, len(df))

    df["is_canned"] = labels
    # Drop rows where ollama returned None (inconclusive)
    before = len(df)
    df = df.dropna(subset=["is_canned"])
    df["is_canned"] = df["is_canned"].astype(int)
    logger.info("Labelled %d rows (%d dropped as inconclusive)", len(df), before - len(df))

    df.to_csv(output_csv, index=False)
    logger.info("Saved labelled data → %s", output_csv)
    logger.info("Next step: python train_nlp.py --task canned --data %s", output_csv)


# ---------------------------------------------------------------------------
# sklearn pipeline training
# ---------------------------------------------------------------------------

class NLPModelTrainer:
    """Train a fast TF-IDF + LogisticRegression pipeline for offline inference."""

    def __init__(self):
        try:
            from data_loader import DataLoader
            self.loader = DataLoader()
        except ImportError:
            self.loader = None

    def train_canned_detector(self, data_file: str):
        """Train from a labelled CSV with columns: text, is_canned."""
        try:
            import pandas as pd
            import joblib
            import numpy as np
            from sklearn.model_selection import train_test_split
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.pipeline import Pipeline
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import classification_report
        except ImportError as e:
            logger.error("Missing dependency: %s  — pip install scikit-learn pandas joblib", e)
            return

        logger.info("Loading data from %s ...", data_file)
        try:
            if self.loader:
                df = self.loader.load_commentary_data(data_file)
            else:
                df = pd.read_csv(data_file)
        except Exception as e:
            logger.error("Could not load data: %s", e)
            return

        if "is_canned" not in df.columns:
            logger.error("Dataset missing 'is_canned' column. Run --task ollama-label first.")
            return

        X = df["text"].astype(str)
        y = df["is_canned"].astype(int)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        logger.info("Training TF-IDF + LogisticRegression ...")
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), stop_words="english")),
            ("clf", LogisticRegression(max_iter=500, C=1.0)),
        ])
        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        logger.info("Evaluation on held-out test set:\n%s", classification_report(y_test, y_pred))

        model_path = MODEL_DIR / "canned_commentary_model.pkl"
        joblib.dump(pipeline, model_path)
        logger.info("Model saved → %s", model_path)
        logger.info(
            "This model is now loaded automatically by NLPChecker as the Tier-3 fallback "
            "when ollama is unavailable."
        )

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train NLP Models for Appraisal QC")
    parser.add_argument(
        "--data", type=str, default="commentary_data.csv",
        help="Input CSV filename (must have 'text' column)"
    )
    parser.add_argument(
        "--output", type=str, default="labelled_commentary.csv",
        help="Output CSV for auto-labelled data (used by --task ollama-label)"
    )
    parser.add_argument(
        "--task", type=str, default="canned",
        choices=["canned", "ollama-label"],
        help=(
            "canned       — train sklearn model on labelled CSV\n"
            "ollama-label — use llava:13b to auto-label raw CSV, then save for training"
        ),
    )
    args = parser.parse_args()
    trainer = NLPModelTrainer()

    if args.task == "ollama-label":
        auto_label_with_ollama(args.data, args.output)
    elif args.task == "canned":
        trainer.train_canned_detector(args.data)
