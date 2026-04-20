import argparse
import joblib
import logging
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_squared_error, classification_report

from data_loader import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AssessmentModelTrainer:
    """
    Class to train ML models for property assessment validation and risk scoring.
    """
    
    def __init__(self, model_dir: str = "../app/models/ml"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.loader = DataLoader()
        
    def train_value_validation_model(self, data_file: str):
        """
        Train a regression model to validate Appraised Value based on property features.
        Features: GLA, Bed, Bath, YearBuilt, ZipCode(Encoded), SiteArea...
        Target: AppraisedValue / SalePrice
        """
        logger.info(f"Loading assessment data from {data_file}...")
        try:
            df = self.loader.load_dataset(data_file)
        except Exception as e:
            logger.error(f"Could not load data: {e}")
            return

        target_col = 'appraised_value'
        feature_cols = ['gla', 'bedrooms', 'bathrooms', 'year_built', 'site_area', 'garage_cars']
        
        # Check columns
        missing_cols = [c for c in feature_cols + [target_col] if c not in df.columns]
        if missing_cols:
            logger.error(f"Dataset missing columns: {missing_cols}")
            return

        X = df[feature_cols]
        y = df[target_col]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        logger.info("Training Value Validation Model (Random Forest)...")
        pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler()),
            ('regressor', RandomForestRegressor(n_estimators=100, random_state=42))
        ])

        pipeline.fit(X_train, y_train)
        
        # Evaluate
        y_pred = pipeline.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)
        rmse = mse ** 0.5
        logger.info(f"Model RMSE: ${rmse:,.2f}")

        # Save
        model_path = self.model_dir / "value_validation_model.pkl"
        joblib.dump(pipeline, model_path)
        logger.info(f"Model saved to {model_path}")

    def train_risk_classifier(self, data_file: str):
        """
        Train a classifier to predict 'Review Risk' (High/Low).
        Target: HighRisk (bool)
        """
        logger.info(f"Loading risk data from {data_file}...")
        try:
            df = self.loader.load_dataset(data_file)
        except Exception as e:
            logger.error(f"Could not load data: {e}")
            return

        target_col = 'is_high_risk'
        # Feature engineering would be key here (e.g., condition diffs, value variance)
        feature_cols = ['gla', 'age', 'condition_rating_encoded', 'quality_rating_encoded', 'comp_variance_pct']
        
        if target_col not in df.columns:
            logger.error(f"Dataset missing target: {target_col}")
            return
            
        # Mock feature check/handling
        useful_cols = [c for c in feature_cols if c in df.columns]
        if not useful_cols:
            logger.error("No valid feature columns found.")
            return

        X = df[useful_cols]
        y = df[target_col]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='mean')),
            ('classifier', RandomForestClassifier(n_estimators=100))
        ])
        
        pipeline.fit(X_train, y_train)
        
        logger.info("Risk Model Evaluation:")
        y_pred = pipeline.predict(X_test)
        logger.info(classification_report(y_test, y_pred))
        
        model_path = self.model_dir / "risk_classifier_model.pkl"
        joblib.dump(pipeline, model_path)
        logger.info(f"Model saved to {model_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ML Models for Assessment QC")
    parser.add_argument("--data", type=str, default="appraisal_data.csv", help="Input dataset filename")
    parser.add_argument("--task", type=str, default="value", choices=["value", "risk"], help="Training task")
    
    args = parser.parse_args()
    
    trainer = AssessmentModelTrainer()
    
    if args.task == "value":
        trainer.train_value_validation_model(args.data)
    elif args.task == "risk":
        trainer.train_risk_classifier(args.data)
