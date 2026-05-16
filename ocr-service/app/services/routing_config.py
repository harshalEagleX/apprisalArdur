"""
Day 23 — Confidence-Driven Routing Configuration

Plan (Day 23): "All threshold values must be stored in the database, not hardcoded.
They should be configurable per field and per AMC."

Architecture Guide §14: "Thresholds should be configurable per field and per AMC.
When you discover that a particular AMC's documents consistently produce lower
confidence scores for a specific field, you can lower that field's threshold
specifically for that AMC without changing the default thresholds."

This module:
1. Seeds the DB from field_schema.yaml on first run
2. Provides get_thresholds(field_name, amc_id) that reads from DB first, falls
   back to schema YAML, then to global defaults
3. Provides update_threshold() that business analysts can call without a developer

The Engineering Thinking Guide (§11) says: "When a business analyst needs to
adjust a threshold, they should be able to do that through an interface without
involving a developer." This module makes that possible.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.schema import schema_loader

logger = logging.getLogger(__name__)

_GLOBAL_DEFAULTS = {"auto_accept": 0.90, "review": 0.65, "reject": 0.30}


def seed_routing_config() -> int:
    """
    Seed adaptive_field_routing_config from field_schema.yaml.
    Called once during setup; skips fields already in DB.
    Returns number of rows inserted.
    """
    try:
        from app.database import get_db
        from app.models.db_models import FieldRoutingConfigRow

        inserted = 0
        with get_db() as session:
            for fd in schema_loader.all_fields():
                existing = session.query(FieldRoutingConfigRow).filter_by(
                    field_name=fd.canonical_name, amc_id=None
                ).first()
                if existing:
                    continue

                t = schema_loader.thresholds_for(fd.canonical_name)
                row = FieldRoutingConfigRow(
                    field_name=fd.canonical_name,
                    amc_id=None,
                    auto_accept=t.auto_accept,
                    review=t.review,
                    reject=t.reject,
                    rationale=f"Seeded from field_schema.yaml v{schema_loader.schema_version}",
                    updated_by="system_seed",
                )
                session.add(row)
                inserted += 1

        logger.info("Routing config seeded: %d fields", inserted)
        return inserted

    except Exception as exc:
        logger.warning("Routing config seed failed (non-fatal): %s", exc)
        return 0


def get_thresholds(field_name: str, amc_id: Optional[str] = None) -> dict:
    """
    Load thresholds for a field, with AMC override if available.
    Priority: DB AMC-specific → DB default → schema YAML → global default.
    """
    try:
        from app.database import get_db
        from app.models.db_models import FieldRoutingConfigRow

        with get_db() as session:
            # Try AMC-specific first
            if amc_id:
                row = session.query(FieldRoutingConfigRow).filter_by(
                    field_name=field_name, amc_id=amc_id
                ).first()
                if row:
                    return {"auto_accept": row.auto_accept, "review": row.review, "reject": row.reject}

            # Fall back to field default in DB
            row = session.query(FieldRoutingConfigRow).filter_by(
                field_name=field_name, amc_id=None
            ).first()
            if row:
                return {"auto_accept": row.auto_accept, "review": row.review, "reject": row.reject}

    except Exception:
        pass

    # Fall back to schema YAML
    t = schema_loader.thresholds_for(field_name)
    return {"auto_accept": t.auto_accept, "review": t.review, "reject": t.reject}


def update_threshold(
    field_name: str,
    auto_accept: float,
    review: float,
    reject: float,
    amc_id: Optional[str] = None,
    rationale: str = "",
    updated_by: str = "operator",
) -> bool:
    """
    Update routing thresholds for a field (and optionally a specific AMC).
    This is what a business analyst calls through the admin interface.
    No code deployment required.
    """
    try:
        from app.database import get_db
        from app.models.db_models import FieldRoutingConfigRow

        with get_db() as session:
            row = session.query(FieldRoutingConfigRow).filter_by(
                field_name=field_name, amc_id=amc_id
            ).first()

            if row:
                row.auto_accept = auto_accept
                row.review = review
                row.reject = reject
                row.rationale = rationale
                row.updated_by = updated_by
            else:
                session.add(FieldRoutingConfigRow(
                    field_name=field_name, amc_id=amc_id,
                    auto_accept=auto_accept, review=review, reject=reject,
                    rationale=rationale, updated_by=updated_by,
                ))

        logger.info(
            "Routing threshold updated: %s (AMC=%s) auto=%.2f review=%.2f reject=%.2f by=%s",
            field_name, amc_id, auto_accept, review, reject, updated_by,
        )
        return True

    except Exception as exc:
        logger.error("Routing threshold update failed: %s", exc)
        return False


def auto_adjust_from_corrections(amc_id: str, field_name: str, correction_rate: float) -> None:
    """
    Day 27 prerequisite: When a field is being corrected at high rate for a specific AMC,
    automatically reduce the auto-acceptance threshold.
    Plan (Day 27): 'When a field is being corrected at a high rate for a specific AMC,
    the system should automatically reduce the auto-acceptance threshold.'
    """
    thresholds = get_thresholds(field_name, amc_id)
    if correction_rate > 0.30:  # >30% correction rate → reduce auto-accept
        new_auto = max(0.60, thresholds["auto_accept"] - 0.10)
        update_threshold(
            field_name=field_name,
            auto_accept=new_auto,
            review=thresholds["review"],
            reject=thresholds["reject"],
            amc_id=amc_id,
            rationale=f"Auto-reduced: correction_rate={correction_rate:.0%}",
            updated_by="correction_pattern_analyzer",
        )
        logger.info(
            "Auto-adjusted threshold: %s/%s auto_accept %.2f→%.2f (correction_rate=%.0f%%)",
            field_name, amc_id, thresholds["auto_accept"], new_auto, correction_rate * 100,
        )
