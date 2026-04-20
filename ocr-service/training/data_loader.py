import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Union, Optional
import logging

logger = logging.getLogger(__name__)

class DataLoader:
    """
    Utility class to load and preprocess training data for appraisal QC models.
    Supports CSV, JSON, and Parquet formats.
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def load_dataset(self, filename: str) -> pd.DataFrame:
        """
        Load a dataset from file. Auto-detects format based on extension.
        """
        file_path = self.data_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset not found: {file_path}")
            
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.csv':
                return pd.read_csv(file_path)
            elif ext == '.json':
                return pd.read_json(file_path)
            elif ext == '.parquet':
                return pd.read_parquet(file_path)
            else:
                raise ValueError(f"Unsupported file format: {ext}")
        except Exception as e:
            logger.error(f"Failed to load dataset {filename}: {e}")
            raise

    def load_commentary_data(self, filename: str = "commentary_corpus.csv") -> pd.DataFrame:
        """
        Load commentary data specifically. 
        Expected columns: ['text', 'label', 'is_canned', 'reasoning_score']
        """
        df = self.load_dataset(filename)
        required_cols = ['text']
        
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Dataset missing required columns: {required_cols}")
            
        # Basic preprocessing
        df.dropna(subset=['text'], inplace=True)
        return df

    def save_dataset(self, df: pd.DataFrame, filename: str):
        """Save dataframe to data dir."""
        file_path = self.data_dir / filename
        ext = file_path.suffix.lower()
        
        if ext == '.csv':
            df.to_csv(file_path, index=False)
        elif ext == '.json':
            df.to_json(file_path, orient='records')
        elif ext == '.parquet':
            df.to_parquet(file_path)
        else:
            raise ValueError(f"Unsupported save format: {ext}")
            
if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    loader = DataLoader()
    logger.info("DataLoader initialized. Place datasets in 'data' directory.")
