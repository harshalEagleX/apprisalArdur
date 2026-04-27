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
    # ── Subject: BLOCKING structural — run first ──────────────────────────────
    ("S-1",    "Subject",        "BLOCKING",  10, "ALL"),
    ("S-2",    "Subject",        "BLOCKING",  20, "ALL"),
    ("S-3",    "Subject",        "STANDARD",  30, "ALL"),
    ("S-4",    "Subject",        "STANDARD",  40, "ALL"),
    ("S-5",    "Subject",        "STANDARD",  50, "ALL"),
    ("S-6",    "Subject",        "STANDARD",  60, "ALL"),
    # ── Contract: BLOCKING ────────────────────────────────────────────────────
    ("C-1",    "Contract",       "BLOCKING",  70, "Purchase"),
    ("C-2",    "Contract",       "BLOCKING",  80, "Purchase"),
    ("C-3",    "Contract",       "STANDARD",  90, "Purchase"),
    # ── Subject: logic rules ──────────────────────────────────────────────────
    ("S-7",    "Subject",        "STANDARD", 110, "ALL"),
    ("S-8",    "Subject",        "STANDARD", 120, "ALL"),
    ("S-9",    "Subject",        "STANDARD", 130, "ALL"),
    ("S-10",   "Subject",        "STANDARD", 140, "ALL"),
    ("S-11",   "Subject",        "STANDARD", 150, "ALL"),
    ("S-12",   "Subject",        "ADVISORY", 160, "ALL"),
    # ── Contract: logic rules ─────────────────────────────────────────────────
    ("C-4",    "Contract",       "STANDARD", 170, "Purchase"),
    ("C-5",    "Contract",       "ADVISORY", 180, "Purchase"),
    # ── Neighborhood structural ───────────────────────────────────────────────
    ("N-1",    "Neighborhood",   "STANDARD", 190, "ALL"),
    ("N-2",    "Neighborhood",   "STANDARD", 192, "ALL"),
    ("N-3",    "Neighborhood",   "ADVISORY", 194, "ALL"),
    ("N-4",    "Neighborhood",   "ADVISORY", 196, "ALL"),
    ("N-5",    "Neighborhood",   "STANDARD", 198, "ALL"),
    ("N-6",    "Neighborhood",   "STANDARD", 200, "ALL"),
    ("N-7",    "Neighborhood",   "STANDARD", 202, "ALL"),
    # ── Site section ─────────────────────────────────────────────────────────
    ("ST-1",   "Site",           "STANDARD", 300, "ALL"),
    ("ST-2",   "Site",           "STANDARD", 310, "ALL"),
    ("ST-3",   "Site",           "STANDARD", 320, "ALL"),
    ("ST-4",   "Site",           "ADVISORY", 330, "ALL"),
    ("ST-5",   "Site",           "STANDARD", 340, "ALL"),
    ("ST-6",   "Site",           "BLOCKING", 350, "ALL"),
    ("ST-7",   "Site",           "STANDARD", 360, "ALL"),
    ("ST-8",   "Site",           "STANDARD", 370, "ALL"),
    ("ST-9",   "Site",           "STANDARD", 380, "ALL"),
    ("ST-10",  "Site",           "STANDARD", 390, "ALL"),
    # ── Improvement section ───────────────────────────────────────────────────
    ("I-1",    "Improvements",   "STANDARD", 400, "ALL"),
    ("I-2",    "Improvements",   "STANDARD", 410, "ALL"),
    ("I-3",    "Improvements",   "STANDARD", 420, "ALL"),
    ("I-4",    "Improvements",   "STANDARD", 430, "ALL"),
    ("I-5",    "Improvements",   "STANDARD", 440, "ALL"),
    ("I-6",    "Improvements",   "STANDARD", 450, "FHA"),
    ("I-7",    "Improvements",   "STANDARD", 460, "ALL"),
    ("I-8",    "Improvements",   "ADVISORY", 470, "ALL"),
    ("I-9",    "Improvements",   "STANDARD", 480, "ALL"),
    ("I-10",   "Improvements",   "ADVISORY", 490, "ALL"),
    ("I-11",   "Improvements",   "STANDARD", 500, "ALL"),
    ("I-12",   "Improvements",   "STANDARD", 510, "ALL"),
    ("I-13",   "Improvements",   "STANDARD", 520, "ALL"),
    # ── Sales Comparison Approach ─────────────────────────────────────────────
    ("SCA-1",  "SalesComp",      "STANDARD", 600, "ALL"),
    ("SCA-2",  "SalesComp",      "BLOCKING", 610, "ALL"),
    ("SCA-3",  "SalesComp",      "BLOCKING", 620, "ALL"),
    ("SCA-4",  "SalesComp",      "STANDARD", 630, "ALL"),
    ("SCA-5",  "SalesComp",      "STANDARD", 640, "ALL"),
    ("SCA-6",  "SalesComp",      "STANDARD", 650, "ALL"),
    ("SCA-7",  "SalesComp",      "STANDARD", 660, "ALL"),
    ("SCA-8",  "SalesComp",      "STANDARD", 670, "ALL"),
    ("SCA-9",  "SalesComp",      "ADVISORY", 680, "ALL"),
    ("SCA-10", "SalesComp",      "STANDARD", 690, "ALL"),
    ("SCA-11", "SalesComp",      "STANDARD", 700, "ALL"),
    ("SCA-12", "SalesComp",      "ADVISORY", 710, "ALL"),
    ("SCA-13", "SalesComp",      "ADVISORY", 720, "ALL"),
    ("SCA-14", "SalesComp",      "STANDARD", 730, "ALL"),
    ("SCA-15", "SalesComp",      "STANDARD", 740, "ALL"),
    ("SCA-16", "SalesComp",      "STANDARD", 750, "ALL"),
    ("SCA-17", "SalesComp",      "STANDARD", 760, "ALL"),
    ("SCA-18", "SalesComp",      "STANDARD", 770, "ALL"),
    ("SCA-19", "SalesComp",      "ADVISORY", 780, "ALL"),
    ("SCA-20", "SalesComp",      "STANDARD", 790, "ALL"),
    ("SCA-21", "SalesComp",      "STANDARD", 800, "ALL"),
    ("SCA-22", "SalesComp",      "ADVISORY", 810, "ALL"),
    ("SCA-23", "SalesComp",      "ADVISORY", 820, "ALL"),
    ("SCA-24", "SalesComp",      "ADVISORY", 830, "ALL"),
    ("SCA-25", "SalesComp",      "ADVISORY", 840, "ALL"),
    ("SCA-26", "SalesComp",      "ADVISORY", 850, "ALL"),
    ("SCA-27", "SalesComp",      "STANDARD", 860, "FHA"),
    # ── Reconciliation + Cost + Income ────────────────────────────────────────
    ("R-1",    "Reconciliation", "STANDARD", 900, "ALL"),
    ("R-2",    "Reconciliation", "STANDARD", 910, "ALL"),
    ("CA-1",   "CostApproach",   "STANDARD", 950, "USDA"),
    ("CA-2",   "CostApproach",   "STANDARD", 960, "USDA"),
    ("IA-1",   "IncomeApproach", "STANDARD", 970, "ALL"),
    ("IA-2",   "IncomeApproach", "STANDARD", 980, "ALL"),
    # ── Addendum + Documentation ──────────────────────────────────────────────
    ("ADD-1",  "Addendum",       "STANDARD",1000, "ALL"),
    ("ADD-2",  "Addendum",       "STANDARD",1010, "ALL"),
    ("ADD-3",  "Addendum",       "ADVISORY",1020, "ALL"),
    ("ADD-4",  "Addendum",       "STANDARD",1030, "FHA,USDA"),
    ("ADD-5",  "Addendum",       "STANDARD",1040, "FHA,USDA"),
    ("ADD-6",  "Addendum",       "STANDARD",1050, "FHA,USDA"),
    ("ADD-7",  "Addendum",       "STANDARD",1060, "ALL"),
    ("ADD-8",  "Addendum",       "STANDARD",1070, "ALL"),
    ("ADD-9",  "Addendum",       "STANDARD",1080, "ALL"),
    ("DOC-1",  "Docs",           "STANDARD",1100, "ALL"),
    ("DOC-2",  "Docs",           "ADVISORY",1110, "ALL"),
    ("DOC-3",  "Docs",           "ADVISORY",1120, "ALL"),
    ("DOC-4",  "Docs",           "STANDARD",1130, "ALL"),
    ("SIG-1",  "Signature",      "STANDARD",1200, "ALL"),
    ("SIG-2",  "Signature",      "STANDARD",1210, "ALL"),
    ("SIG-3",  "Signature",      "ADVISORY",1220, "ALL"),
    ("SIG-4",  "Signature",      "ADVISORY",1230, "ALL"),
    # ── Physical evidence ─────────────────────────────────────────────────────
    ("PH-1",   "Photos",         "STANDARD",1300, "ALL"),
    ("PH-2",   "Photos",         "STANDARD",1310, "ALL"),
    ("PH-3",   "Photos",         "STANDARD",1320, "ALL"),
    ("PH-4",   "Photos",         "STANDARD",1330, "FHA"),
    ("PH-5",   "Photos",         "STANDARD",1340, "ALL"),
    ("PH-6",   "Photos",         "ADVISORY",1350, "ALL"),
    ("M-1",    "Maps",           "STANDARD",1400, "ALL"),
    ("M-2",    "Maps",           "ADVISORY",1410, "ALL"),
    ("M-3",    "Maps",           "STANDARD",1420, "ALL"),
    ("M-4",    "Maps",           "STANDARD",1430, "ALL"),
    ("SK-1",   "Sketch",         "STANDARD",1500, "ALL"),
    ("SK-2",   "Sketch",         "STANDARD",1510, "ALL"),
    ("SK-3",   "Sketch",         "STANDARD",1520, "ALL"),
    ("SK-4",   "Sketch",         "STANDARD",1530, "ALL"),
    ("SK-5",   "Sketch",         "STANDARD",1540, "ALL"),
    # ── FHA-specific ──────────────────────────────────────────────────────────
    ("FHA-1",  "FHA",            "BLOCKING",1600, "FHA"),
    ("FHA-2",  "FHA",            "BLOCKING",1610, "FHA"),
    ("FHA-3",  "FHA",            "BLOCKING",1620, "FHA"),
    ("FHA-4",  "FHA",            "STANDARD",1630, "FHA"),
    ("FHA-5",  "FHA",            "STANDARD",1640, "FHA"),
    ("FHA-6",  "FHA",            "STANDARD",1650, "FHA"),
    ("FHA-7",  "FHA",            "STANDARD",1660, "FHA"),
    ("FHA-8",  "FHA",            "STANDARD",1670, "FHA"),
    ("FHA-9",  "FHA",            "STANDARD",1680, "FHA"),
    ("FHA-10", "FHA",            "STANDARD",1690, "FHA"),
    ("FHA-11", "FHA",            "STANDARD",1700, "FHA"),
    ("FHA-12", "FHA",            "STANDARD",1710, "FHA"),
    ("FHA-13", "FHA",            "STANDARD",1720, "FHA"),
    ("FHA-14", "FHA",            "STANDARD",1730, "FHA"),
    # ── USDA + Multi-Family ───────────────────────────────────────────────────
    ("USDA-1", "USDA",           "STANDARD",1800, "USDA"),
    ("MF-1",   "MultiFamily",    "STANDARD",1810, "ALL"),
    ("MF-2",   "MultiFamily",    "STANDARD",1820, "ALL"),
    # ── Commentary / LLM — run LAST ───────────────────────────────────────────
    ("COM-1",  "Commentary",     "ADVISORY",2100, "ALL"),
    ("COM-2",  "Commentary",     "STANDARD",2110, "ALL"),
    ("COM-3",  "Commentary",     "ADVISORY",2120, "ALL"),
    ("COM-4",  "Commentary",     "ADVISORY",2130, "ALL"),
    ("COM-5",  "Commentary",     "STANDARD",2140, "ALL"),
    ("COM-6",  "Commentary",     "ADVISORY",2150, "ALL"),
    ("COM-7",  "Commentary",     "STANDARD",2160, "ALL"),
]

RULE_NAMES = {
    # Subject
    "S-1":"Address Match","S-2":"Borrower Match","S-3":"Owner of Public Record",
    "S-4":"Legal / APN / Taxes","S-5":"Neighborhood Name","S-6":"Map & Census Tract",
    "S-7":"Occupant Status","S-8":"Special Assessments","S-9":"PUD / HOA",
    "S-10":"Lender Match","S-11":"Property Rights","S-12":"Prior Listing History",
    # Contract
    "C-1":"Contract Analysis","C-2":"Contract Price & Date","C-3":"Owner of Record Source",
    "C-4":"Financial Assistance","C-5":"Personal Property",
    # Neighborhood
    "N-1":"Neighborhood Characteristics","N-2":"Housing Trends",
    "N-3":"One-Unit Housing Price Range","N-4":"Present Land Use Total",
    "N-5":"Neighborhood Boundaries","N-6":"Neighborhood Description Present",
    "N-7":"Market Conditions Present",
    # Site
    "ST-1":"Site Dimensions","ST-2":"Site Area","ST-3":"Site Shape","ST-4":"View",
    "ST-5":"Zoning Classification","ST-6":"Highest and Best Use",
    "ST-7":"Utilities and Off-Site Improvements","ST-8":"FEMA Flood Hazard Area",
    "ST-9":"Utilities Typical for Market","ST-10":"Adverse Site Conditions",
    # Improvements
    "I-1":"General Description","I-2":"Foundation","I-3":"Exterior Description",
    "I-4":"Interior Description","I-5":"Utilities Status","I-6":"Appliances",
    "I-7":"Above Grade Room Count","I-8":"Additional Features",
    "I-9":"Property Condition Rating","I-10":"Adverse Conditions Affecting Livability",
    "I-11":"Neighborhood Conformity","I-12":"Additions to Subject","I-13":"Security Bars",
    # Sales Comparison
    "SCA-1":"Comparable Market Summary","SCA-2":"Comparables Required",
    "SCA-3":"Address UAD Compliance","SCA-4":"Proximity to Subject",
    "SCA-5":"Data Sources","SCA-6":"Verification Sources",
    "SCA-7":"Sale or Financing Concessions","SCA-8":"Date of Sale / Time Adjustment",
    "SCA-9":"Location Rating","SCA-10":"Leasehold / Fee Simple",
    "SCA-11":"Site","SCA-12":"View","SCA-13":"Design Style",
    "SCA-14":"Quality of Construction","SCA-15":"Actual Age","SCA-16":"Condition",
    "SCA-17":"Above Grade Room Count and GLA","SCA-18":"Basement and Below Grade",
    "SCA-19":"Functional Utility","SCA-20":"Heating / Cooling",
    "SCA-21":"Garage / Carport","SCA-22":"Porch / Patio / Deck",
    "SCA-23":"Listing Comparables","SCA-24":"Unique Design Properties",
    "SCA-25":"New Construction","SCA-26":"Square Footage","SCA-27":"Comparable Photos",
    # Approaches
    "R-1":"Value Reconciliation","R-2":"Final Opinion of Value",
    "CA-1":"Cost Approach Requirement","CA-2":"Cost Approach Completion",
    "IA-1":"Subject Rent Matching","IA-2":"Operating Income Statement",
    # Addendum / Docs / Signature
    "ADD-1":"Commentary Standards","ADD-2":"Comparable Selection Commentary",
    "ADD-3":"Dated Sales Commentary","ADD-4":"Market Conditions Addendum",
    "ADD-5":"1004MC Inventory Analysis","ADD-6":"1004MC Comparables Matching",
    "ADD-7":"1004MC Overall Trend","ADD-8":"1004MC Condo / Co-Op","ADD-9":"USPAP Addendum",
    "DOC-1":"Appraiser License","DOC-2":"E&O Insurance","DOC-3":"UAD Data Set",
    "DOC-4":"Trainee Signatures",
    "SIG-1":"Signature Requirements","SIG-2":"Appraiser Information",
    "SIG-3":"Supervisory Appraiser","SIG-4":"Email Address",
    # Photos / Maps / Sketch
    "PH-1":"Required Subject Photos","PH-2":"Interior Photos","PH-3":"Additional Subject Photos",
    "PH-4":"FHA Specific Photos","PH-5":"Comparable Photos","PH-6":"Obsolescence Photos",
    "M-1":"Location Map","M-2":"Aerial Map","M-3":"Plat Map","M-4":"Flood Map",
    "SK-1":"Sketch Location","SK-2":"Floor Coverage","SK-3":"Dimensions",
    "SK-4":"Outbuildings and Structures","SK-5":"Area Calculations",
    # FHA
    "FHA-1":"HUD Minimum Property Requirements","FHA-2":"FHA Case Number",
    "FHA-3":"FHA Intended Use and User","FHA-4":"FHA MPR Statement",
    "FHA-5":"FHA Comparable Sales Dating","FHA-6":"FHA Repairs",
    "FHA-7":"Space Heater as Primary Heat","FHA-8":"Security Bars on Windows",
    "FHA-9":"FHA Photo Requirements","FHA-10":"Estimated Remaining Economic Life",
    "FHA-11":"Attic / Crawl Space Inspection","FHA-12":"Well and Septic",
    "FHA-13":"FHA Appliances","FHA-14":"FHA Sketch Requirements",
    # USDA / Multi-Family
    "USDA-1":"USDA Cost Approach","MF-1":"Subject Rent Matching","MF-2":"Form 216",
    # Commentary
    "COM-1":"Neighborhood Description Specificity","COM-2":"Market Conditions Quality",
    "COM-3":"Comparable Selection Rationale","COM-4":"Adjustments Explanation",
    "COM-5":"Reconciliation Sufficiency","COM-6":"Addenda Consistency",
    "COM-7":"Prior Sales Disclosure",
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
