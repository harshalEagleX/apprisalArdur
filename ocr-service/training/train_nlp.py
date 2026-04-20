import argparse
import joblib
import logging
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

from data_loader import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLPModelTrainer:
    """
    Class to train NLP models for appraisal commentary analysis.
    Current focus: Detect 'Canned' vs 'Specific' commentary.
    """
    
    def __init__(self, model_dir: str = "../app/models/nlp"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.loader = DataLoader()
        
    def train_canned_detector(self, data_file: str):
        """
        Train a model to detect canned commentary.
        """
        logger.info(f"Loading data from {data_file}...")
        try:
            df = self.loader.load_commentary_data(data_file)
        except Exception as e:
            logger.error(f"Could not load data: {e}")
            return

        if 'is_canned' not in df.columns:
            logger.error("Dataset missing 'is_canned' label column.")
            return

        X = df['text']
        y = df['is_canned']

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        logger.info("Training pipeline...")
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(max_features=5000, stop_words='english')),
            ('clf', LogisticRegression())
        ])

        pipeline.fit(X_train, y_train)
        
        # Evaluate
        y_pred = pipeline.predict(X_test)
        logger.info("Model Evaluation:")
        logger.info(classification_report(y_test, y_pred))

        # Save
        model_path = self.model_dir / "canned_commentary_model.pkl"
        joblib.dump(pipeline, model_path)
        logger.info(f"Model saved to {model_path}")

    def train_transformer_model(self):
        """
        Placeholder for Fine-tuning a Transformer model (e.g. DistilBERT).
        Requires significantly more compute/GPU.
        """
        logger.info("Transformer training not yet implemented for CPU environment.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train NLP Models for Appraisal QC")
    parser.add_argument("--data", type=str, default="commentary_data.csv", help="Input dataset filename")
    parser.add_argument("--task", type=str, default="canned", choices=["canned", "transformer"], help="Training task")
    
    args = parser.parse_args()
    
    trainer = NLPModelTrainer()
    
    if args.task == "canned":
        trainer.train_canned_detector(args.data)
    elif args.task == "transformer":
        trainer.train_transformer_model()
