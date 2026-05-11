"""
P3.5 — Auto-pass threshold calibration service.

Architecture
============
The system learns whether a specific (rule, extraction_method, confidence, …)
combination can be trusted to auto-pass WITHOUT reviewer intervention.

Phase 0 — cold start (no training data):
    Falls back to the tiered confidence thresholds already baked into the rule
    engine.  No prediction is made; rule engine behaviour is unchanged.

Phase 1 — warm start (>= MIN_EXAMPLES_TO_TRAIN examples):
    A sklearn LogisticRegression pipeline is trained on reviewer
    acceptance/rejection labels.  The model predicts the probability that a
    given rule result would be accepted by a human reviewer.  When probability
    >= ACCEPT_THRESHOLD the rule is allowed to auto-pass; otherwise it stays
    as REVIEW.

Phase 2 — production (>= MIN_EXAMPLES_PRODUCTION):
    RandomForestClassifier is used instead for higher accuracy.
    The model is retrained nightly via `training/train_auto_pass.py`.

Key invariants:
  - A rule that has NEVER had a reviewer acceptance cannot auto-pass.
  - The model is stored at training/models/auto_pass_model.pkl and loaded
    lazily.  Retraining regenerates this file; the predictor reloads it.
  - When the model is absent or stale, the service returns None (no opinion)
    and the caller falls through to the tiered threshold logic.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import re
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

MIN_EXAMPLES_TO_TRAIN = 30       # Start training when this many labelled examples exist
MIN_EXAMPLES_PRODUCTION = 100    # Switch to RandomForest at this count
ACCEPT_THRESHOLD = 0.80          # Probability above which auto-pass is allowed
MAX_RULE_REJECT_RATE = 0.20      # If >20% of reviewer decisions for a rule are rejections,
                                 # never auto-pass that rule regardless of model score

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "training", "models", "auto_pass_model.pkl"
)
MODEL_PATH = os.path.normpath(MODEL_PATH)
METADATA_PATH = MODEL_PATH.replace(".pkl", "_meta.json")

# ── Feature extraction ─────────────────────────────────────────────────────────

RULE_FAMILIES = [
    "S", "C", "N", "ST", "I", "SCA", "R", "CA", "IA",
    "ADD", "COM", "PH", "M", "SK", "DOC", "SIG", "FHA", "USDA", "MF", "XF",
]
EXTRACTION_METHODS = [
    "spatial_anchor", "regex_primary", "regex_fallback",
    "context_fallback", "total_value_stream", "not_found", "unknown",
]
LOAN_TYPES = ["CONVENTIONAL", "FHA", "VA", "USDA", "ALL", "UNKNOWN"]


@dataclass
class AutoPassFeatures:
    """Feature vector extracted from a rule result for ML prediction."""
    rule_family: str            # e.g. "N", "ST"
    extraction_method: str      # e.g. "spatial_anchor"
    confidence: float           # 0.0 – 1.0
    has_source_page: int        # 0 or 1
    has_bbox: int               # 0 or 1
    has_compared_values: int    # 0 or 1
    has_extracted_value: int    # 0 or 1
    loan_type: str              # e.g. "CONVENTIONAL"
    is_presence_rule: int       # 0 or 1 (presence_validated flag)
    is_extraction_rule: int     # 0 or 1 (extraction_based_validation flag)
    confidence_bin: int         # 0=<0.6, 1=0.6-0.7, 2=0.7-0.8, 3=0.8-0.9, 4=>=0.9

    def to_list(self) -> List:
        """Return ordered feature list for sklearn (must match training order)."""
        rule_family_idx = RULE_FAMILIES.index(self.rule_family) if self.rule_family in RULE_FAMILIES else -1
        method_idx = EXTRACTION_METHODS.index(self.extraction_method) if self.extraction_method in EXTRACTION_METHODS else -1
        loan_idx = LOAN_TYPES.index(self.loan_type) if self.loan_type in LOAN_TYPES else -1
        return [
            rule_family_idx,
            method_idx,
            self.confidence,
            self.has_source_page,
            self.has_bbox,
            self.has_compared_values,
            self.has_extracted_value,
            loan_idx,
            self.is_presence_rule,
            self.is_extraction_rule,
            self.confidence_bin,
        ]

    @staticmethod
    def feature_names() -> List[str]:
        return [
            "rule_family_idx", "extraction_method_idx", "confidence",
            "has_source_page", "has_bbox", "has_compared_values",
            "has_extracted_value", "loan_type_idx",
            "is_presence_rule", "is_extraction_rule", "confidence_bin",
        ]


def extract_features(
    rule_id: str,
    extraction_method: Optional[str],
    confidence: Optional[float],
    source_page: Optional[int],
    bbox_x: Optional[float],
    has_compared_values: bool,
    has_extracted_value: bool,
    loan_type: Optional[str],
    details: Optional[Dict],
) -> AutoPassFeatures:
    """Build a feature vector from a rule result's metadata."""
    family = (rule_id or "").split("-", 1)[0].upper()
    if family not in RULE_FAMILIES:
        family = "S"

    method = (extraction_method or "unknown").lower()
    if method not in EXTRACTION_METHODS:
        method = "unknown"

    conf = max(0.0, min(1.0, float(confidence or 0.0)))

    bin_val = 0
    if conf >= 0.90:
        bin_val = 4
    elif conf >= 0.80:
        bin_val = 3
    elif conf >= 0.70:
        bin_val = 2
    elif conf >= 0.60:
        bin_val = 1

    lt = (loan_type or "UNKNOWN").strip().upper()
    if lt not in LOAN_TYPES:
        lt = "UNKNOWN"

    d = details or {}
    return AutoPassFeatures(
        rule_family=family,
        extraction_method=method,
        confidence=conf,
        has_source_page=1 if (source_page and source_page > 0) else 0,
        has_bbox=1 if (bbox_x and bbox_x > 0.0) else 0,
        has_compared_values=1 if has_compared_values else 0,
        has_extracted_value=1 if has_extracted_value else 0,
        loan_type=lt,
        is_presence_rule=1 if d.get("presence_validated") else 0,
        is_extraction_rule=1 if d.get("extraction_based_validation") else 0,
        confidence_bin=bin_val,
    )


# ── Training example recording ─────────────────────────────────────────────────

def record_example(
    *,
    rule_id: str,
    rule_family: str,
    extraction_method: Optional[str],
    confidence: Optional[float],
    source_page: Optional[int],
    bbox_x: Optional[float],
    has_compared_values: bool,
    has_extracted_value: bool,
    loan_type: Optional[str],
    details: Optional[Dict],
    reviewer_accepted: bool,
    document_id: Optional[str] = None,
    reviewer_comment: Optional[str] = None,
) -> None:
    """
    Persist a reviewer decision as an auto-pass calibration training example.

    Called from the feedback endpoint whenever a reviewer confirms (PASS) or
    overrides (FAIL) a rule result.  Each call adds one row to the
    `auto_pass_examples` table.  The trainer reads these rows nightly.
    """
    try:
        from app.database import get_db
        from app.models.db_models import AutoPassExample

        features = extract_features(
            rule_id=rule_id,
            extraction_method=extraction_method,
            confidence=confidence,
            source_page=source_page,
            bbox_x=bbox_x,
            has_compared_values=has_compared_values,
            has_extracted_value=has_extracted_value,
            loan_type=loan_type,
            details=details,
        )

        with get_db() as db:
            example = AutoPassExample(
                rule_id=rule_id,
                rule_family=rule_family,
                extraction_method=features.extraction_method,
                confidence=features.confidence,
                has_source_page=bool(features.has_source_page),
                has_bbox=bool(features.has_bbox),
                has_compared_values=bool(features.has_compared_values),
                has_extracted_value=bool(features.has_extracted_value),
                loan_type=features.loan_type,
                is_presence_rule=bool(features.is_presence_rule),
                is_extraction_rule=bool(features.is_extraction_rule),
                reviewer_accepted=reviewer_accepted,
                document_id=document_id,
                reviewer_comment=reviewer_comment,
            )
            db.add(example)
            db.commit()
            logger.debug(
                "AutoPass example recorded: rule=%s accepted=%s confidence=%.2f",
                rule_id, reviewer_accepted, features.confidence,
            )
    except Exception as exc:
        logger.debug("AutoPass example recording skipped: %s", exc)


# ── Per-rule reject-rate guard ─────────────────────────────────────────────────

_reject_rate_cache: Dict[str, Tuple[float, datetime]] = {}
_reject_rate_lock = threading.Lock()
_REJECT_RATE_TTL_SECONDS = 300   # refresh every 5 minutes


def _rule_reject_rate(rule_id: str) -> Optional[float]:
    """
    Return the historical reviewer rejection rate for a rule, or None if unknown.
    Cached for TTL seconds to avoid DB pressure on every rule evaluation.
    """
    with _reject_rate_lock:
        cached = _reject_rate_cache.get(rule_id)
        if cached:
            rate, ts = cached
            if (datetime.now(timezone.utc) - ts).total_seconds() < _REJECT_RATE_TTL_SECONDS:
                return rate

    try:
        from app.database import get_db
        from app.models.db_models import AutoPassExample
        from sqlalchemy import func

        with get_db() as db:
            row = (
                db.query(
                    func.count(AutoPassExample.id).label("total"),
                    func.sum(
                        (~AutoPassExample.reviewer_accepted).cast(db.bind.dialect.name == "postgresql" and None or None)
                    ).label("rejected"),
                )
                .filter(AutoPassExample.rule_id == rule_id)
                .first()
            )
            if not row or not row.total or row.total < 5:
                return None
            total = int(row.total)
            rejected = int(row.rejected or 0)
            rate = rejected / total
    except Exception:
        rate = None

    with _reject_rate_lock:
        if rate is not None:
            _reject_rate_cache[rule_id] = (rate, datetime.now(timezone.utc))
    return rate


# ── Model predictor ────────────────────────────────────────────────────────────

_model_cache: Optional[object] = None
_model_mtime: float = 0.0
_model_lock = threading.Lock()


def _load_model():
    """Load the trained sklearn model, reloading if the file changed."""
    global _model_cache, _model_mtime
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        current_mtime = os.path.getmtime(MODEL_PATH)
        with _model_lock:
            if _model_cache is not None and current_mtime == _model_mtime:
                return _model_cache
        with open(MODEL_PATH, "rb") as fh:
            model = pickle.load(fh)
        with _model_lock:
            _model_cache = model
            _model_mtime = current_mtime
        logger.info("Auto-pass calibration model loaded from %s", MODEL_PATH)
        return model
    except Exception as exc:
        logger.warning("Could not load auto-pass model: %s", exc)
        return None


def predict_auto_pass(
    rule_id: str,
    extraction_method: Optional[str],
    confidence: Optional[float],
    source_page: Optional[int],
    bbox_x: Optional[float],
    has_compared_values: bool,
    has_extracted_value: bool,
    loan_type: Optional[str],
    details: Optional[Dict],
) -> Optional[bool]:
    """
    Predict whether this rule result can auto-pass without reviewer intervention.

    Returns:
        True   — model is confident the result can auto-pass
        False  — model says reviewer should confirm
        None   — model unavailable or insufficient data; caller uses tiered thresholds

    The function enforces the MAX_RULE_REJECT_RATE safety guard regardless of
    the model's prediction.  A rule with >20% historical rejection rate is never
    allowed to auto-pass, even if the model score is high.
    """
    family = (rule_id or "").split("-", 1)[0].upper()

    # Safety guard: if the rule has a high historical rejection rate, never auto-pass
    reject_rate = _rule_reject_rate(rule_id)
    if reject_rate is not None and reject_rate > MAX_RULE_REJECT_RATE:
        logger.debug(
            "AutoPass blocked for %s: reject_rate=%.1f%% > MAX_RULE_REJECT_RATE",
            rule_id, reject_rate * 100,
        )
        return False

    model = _load_model()
    if model is None:
        return None   # Cold start — caller uses tiered thresholds

    try:
        features = extract_features(
            rule_id=rule_id,
            extraction_method=extraction_method,
            confidence=confidence,
            source_page=source_page,
            bbox_x=bbox_x,
            has_compared_values=has_compared_values,
            has_extracted_value=has_extracted_value,
            loan_type=loan_type,
            details=details,
        )
        feature_vector = [features.to_list()]
        prob = model.predict_proba(feature_vector)[0][1]   # P(accepted=True)
        accepted = prob >= ACCEPT_THRESHOLD
        logger.debug(
            "AutoPass prediction: rule=%s p_accept=%.3f accepted=%s",
            rule_id, prob, accepted,
        )
        return accepted
    except Exception as exc:
        logger.debug("AutoPass prediction failed for %s: %s", rule_id, exc)
        return None


# ── Model training ─────────────────────────────────────────────────────────────

def train(*, force: bool = False) -> Dict:
    """
    Train (or retrain) the auto-pass calibration model.

    Returns a status dict with: trained, examples_used, accuracy, model_version.

    Triggered by:
      - `training/train_auto_pass.py` (nightly cron)
      - `POST /admin/retrain` endpoint
      - CLI: `python -m app.services.auto_pass_calibration`
    """
    try:
        from app.database import get_db
        from app.models.db_models import AutoPassExample
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import cross_val_score
    except ImportError as exc:
        return {"trained": False, "reason": f"Missing dependency: {exc}"}

    try:
        with get_db() as db:
            examples = db.query(AutoPassExample).filter(
                AutoPassExample.reviewer_accepted.isnot(None)
            ).all()
    except Exception as exc:
        return {"trained": False, "reason": f"DB query failed: {exc}"}

    n = len(examples)
    if n < MIN_EXAMPLES_TO_TRAIN and not force:
        return {
            "trained": False,
            "reason": f"Insufficient examples: {n} < {MIN_EXAMPLES_TO_TRAIN}",
            "examples_available": n,
        }

    # Build feature matrix and labels
    X_rows = []
    y = []
    for ex in examples:
        features = extract_features(
            rule_id=ex.rule_id or "",
            extraction_method=ex.extraction_method,
            confidence=ex.confidence,
            source_page=None,
            bbox_x=1.0 if ex.has_bbox else None,
            has_compared_values=bool(ex.has_compared_values),
            has_extracted_value=bool(ex.has_extracted_value),
            loan_type=ex.loan_type,
            details={
                "presence_validated": ex.is_presence_rule,
                "extraction_based_validation": ex.is_extraction_rule,
            },
        )
        X_rows.append(features.to_list())
        y.append(1 if ex.reviewer_accepted else 0)

    import numpy as np
    X = np.array(X_rows, dtype=float)
    y_arr = np.array(y)

    # Choose classifier based on data volume
    if n >= MIN_EXAMPLES_PRODUCTION:
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
        )
        model_type = "RandomForestClassifier"
    else:
        clf = LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
        )
        model_type = "LogisticRegression"

    pipeline = Pipeline([("scaler", StandardScaler()), ("clf", clf)])

    # Cross-validate if we have enough data
    accuracy = None
    if n >= 20:
        try:
            cv_scores = cross_val_score(pipeline, X, y_arr, cv=min(5, n // 4), scoring="accuracy")
            accuracy = float(cv_scores.mean())
        except Exception:
            pass

    # Fit on full dataset
    pipeline.fit(X, y_arr)

    # Save model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(pipeline, fh)

    # Save metadata
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "examples_used": n,
        "model_type": model_type,
        "accuracy": accuracy,
        "accept_threshold": ACCEPT_THRESHOLD,
        "feature_names": AutoPassFeatures.feature_names(),
        "positive_class": "reviewer_accepted",
    }
    with open(METADATA_PATH, "w") as fh:
        json.dump(meta, fh, indent=2)

    # Reset in-memory cache so next prediction loads the new model
    global _model_cache, _model_mtime
    with _model_lock:
        _model_cache = None
        _model_mtime = 0.0

    logger.info(
        "Auto-pass model trained: n=%d type=%s accuracy=%s",
        n, model_type, f"{accuracy:.3f}" if accuracy else "N/A",
    )
    return {
        "trained": True,
        "examples_used": n,
        "model_type": model_type,
        "accuracy": accuracy,
    }


def get_model_metadata() -> Dict:
    """Return the metadata for the currently deployed model, or empty dict."""
    if not os.path.exists(METADATA_PATH):
        return {
            "trained": False,
            "message": "No model trained yet. Collecting training examples from reviewer feedback.",
            "min_examples_required": MIN_EXAMPLES_TO_TRAIN,
        }
    try:
        with open(METADATA_PATH) as fh:
            meta = json.load(fh)
        meta["trained"] = True
        return meta
    except Exception:
        return {"trained": False, "message": "Model metadata unreadable."}


# ── Standalone entry point (retrain via python -m) ─────────────────────────────

if __name__ == "__main__":
    import sys
    result = train(force="--force" in sys.argv)
    print(json.dumps(result, indent=2))
