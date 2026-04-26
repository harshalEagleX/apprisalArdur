"""
DB-driven rule configuration — Phase 3.

Loads is_active / severity / execution_order from the rules_config table.
Falls back to defaults if DB is unavailable (rules always run).

Seed rules:  call seed_rules_config() once at startup if table is empty.
Toggle:      UPDATE rules_config SET is_active=false WHERE rule_id='S-5';
             Rule engine picks this up on next request (no restart needed).
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Default config for every rule ─────────────────────────────────────────────
# (rule_id, category, severity, execution_order, loan_types)
RULE_DEFAULTS = [
    # ── Structural rules (S/C) — run first ────────────────────────────────────
    ("S-1",   "Subject",       "BLOCKING",  10, "ALL"),
    ("S-2",   "Subject",       "BLOCKING",  20, "ALL"),
    ("S-3",   "Subject",       "STANDARD",  30, "ALL"),
    ("S-4",   "Subject",       "STANDARD",  40, "ALL"),
    ("S-5",   "Subject",       "STANDARD",  50, "ALL"),
    ("S-6",   "Subject",       "STANDARD",  60, "ALL"),
    ("C-1",   "Contract",      "BLOCKING",  70, "Purchase"),
    ("C-2",   "Contract",      "BLOCKING",  80, "Purchase"),
    ("C-3",   "Contract",      "STANDARD",  90, "Purchase"),
    # ── Logic rules ────────────────────────────────────────────────────────────
    ("S-7",   "Subject",       "STANDARD", 110, "ALL"),
    ("S-8",   "Subject",       "STANDARD", 120, "ALL"),
    ("S-9",   "Subject",       "STANDARD", 130, "ALL"),
    ("S-10",  "Subject",       "STANDARD", 140, "ALL"),
    ("S-11",  "Subject",       "STANDARD", 150, "ALL"),
    ("S-12",  "Subject",       "ADVISORY", 160, "ALL"),
    ("C-4",   "Contract",      "STANDARD", 170, "Purchase"),
    ("C-5",   "Contract",      "ADVISORY", 180, "Purchase"),
    # ── Neighborhood structural checks ─────────────────────────────────────────
    ("N-1",   "Neighborhood",  "STANDARD", 190, "ALL"),
    ("N-2",   "Neighborhood",  "STANDARD", 192, "ALL"),
    ("N-3",   "Neighborhood",  "ADVISORY", 194, "ALL"),
    ("N-4",   "Neighborhood",  "ADVISORY", 196, "ALL"),
    ("N-5",   "Neighborhood",  "STANDARD", 198, "ALL"),
    ("N-6",   "Neighborhood",  "STANDARD", 200, "ALL"),
    ("N-7",   "Neighborhood",  "STANDARD", 202, "ALL"),
    # ── Commentary/LLM rules — run last ─────────────────────────────────────
    ("COM-1", "Commentary",    "ADVISORY", 210, "ALL"),
    ("COM-2", "Commentary",    "STANDARD", 220, "ALL"),
    ("COM-3", "Commentary",    "ADVISORY", 230, "ALL"),
    ("COM-4", "Commentary",    "ADVISORY", 240, "ALL"),
    ("COM-5", "Commentary",    "STANDARD", 250, "ALL"),
    ("COM-6", "Commentary",    "ADVISORY", 260, "ALL"),
    ("COM-7", "Commentary",    "STANDARD", 270, "ALL"),
]

RULE_NAMES = {
    "S-1": "Address Match",           "S-2": "Borrower Match",
    "S-3": "Owner of Public Record",  "S-4": "Legal / APN / Taxes",
    "S-5": "Neighborhood Name",       "S-6": "Map & Census Tract",
    "S-7": "Occupant Status",         "S-8": "Special Assessments",
    "S-9": "PUD / HOA",               "S-10": "Lender Match",
    "S-11": "Property Rights",        "S-12": "Prior Listing History",
    "C-1": "Contract Analysis",       "C-2": "Contract Price & Date",
    "C-3": "Owner of Record Source",  "C-4": "Financial Assistance",
    "C-5": "Personal Property",
    "N-1": "Neighborhood Characteristics",  "N-2": "Housing Trends",
    "N-3": "One-Unit Housing Price Range",  "N-4": "Present Land Use Total",
    "N-5": "Neighborhood Boundaries",      "N-6": "Neighborhood Description Present",
    "N-7": "Market Conditions Present",
    "COM-1": "Neighborhood Description Specificity",
    "COM-2": "Market Conditions Quality",
    "COM-3": "Comparable Selection Rationale",
    "COM-4": "Adjustments Explanation",
    "COM-5": "Reconciliation Sufficiency",
    "COM-6": "Addenda Consistency",
    "COM-7": "Prior Sales Disclosure",
}


@dataclass
class RuleConfigEntry:
    rule_id: str
    severity: str
    execution_order: int
    is_active: bool
    applicable_loan_types: str


def seed_rules_config():
    """Insert default rule config rows if the table is empty. Idempotent."""
    try:
        from app.database import get_db
        from app.models.db_models import RuleConfig

        with get_db() as db:
            if db.query(RuleConfig).count() > 0:
                return  # already seeded

            for rule_id, category, severity, order, loan_types in RULE_DEFAULTS:
                db.add(RuleConfig(
                    rule_id=rule_id,
                    rule_name=RULE_NAMES.get(rule_id, rule_id),
                    rule_category=category,
                    is_active=True,
                    severity_level=severity,
                    execution_order=order,
                    applicable_loan_types=loan_types,
                ))
        logger.info("Seeded rules_config table with %d rules", len(RULE_DEFAULTS))
    except Exception as e:
        logger.warning("rules_config seed failed (DB may be unavailable): %s", e)


def load_rule_configs() -> Dict[str, RuleConfigEntry]:
    """
    Load active rule configurations from DB.
    Returns dict of rule_id → RuleConfigEntry.
    Falls back to built-in defaults if DB unavailable.
    """
    # Build defaults first
    defaults = {
        rule_id: RuleConfigEntry(
            rule_id=rule_id,
            severity=severity,
            execution_order=order,
            is_active=True,
            applicable_loan_types=loan_types,
        )
        for rule_id, _, severity, order, loan_types in RULE_DEFAULTS
    }

    try:
        from app.database import get_db, is_db_available
        if not is_db_available():
            return defaults

        from app.models.db_models import RuleConfig
        with get_db() as db:
            rows = db.query(RuleConfig).all()
            if not rows:
                return defaults

            configs = {}
            for row in rows:
                configs[row.rule_id] = RuleConfigEntry(
                    rule_id=row.rule_id,
                    severity=row.severity_level or "STANDARD",
                    execution_order=row.execution_order or 100,
                    is_active=row.is_active,
                    applicable_loan_types=row.applicable_loan_types or "ALL",
                )
            return configs

    except Exception as e:
        logger.warning("Failed to load rules from DB, using defaults: %s", e)
        return defaults
