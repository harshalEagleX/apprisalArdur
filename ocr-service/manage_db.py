"""
Python-owned database management.

Per CLAUDE.md Database Schema Policy:
  Python-owned tables are managed here — never via Alembic, Flyway, or Liquibase.
  Java-owned tables remain untouched by this script.

Usage:
  python manage_db.py create    — create all adaptive_* tables (skip if exist)
  python manage_db.py drop      — drop all adaptive_* tables (asks for confirmation)
  python manage_db.py recreate  — drop then create (development only)
  python manage_db.py status    — show current table state
  python manage_db.py seed-schema — seed field schema log from config/field_schema.yaml
"""

import json
import sys

from sqlalchemy import inspect, text

from app.database import Base, engine, get_db, verify_connection
from app.models.db_models import (
    AmcProfileRow,
    AmcTemplateVersionRow,
    BaselineRunRow,
    DocumentClassificationRow,
    ExtractionResultRow,
    CorrectionRow,
    FieldRoutingConfigRow,
    FieldSchemaLogRow,
    PageOcrResultRow,
    TestGroundTruthRow,
    TestSetDocumentRow,
    ValidationResultRow,
)

# Only adaptive_* tables — never touch Java-owned tables
MANAGED_TABLES = [
    "adaptive_extraction_results",
    "adaptive_corrections",
    "adaptive_amc_profiles",
    "adaptive_amc_template_versions",
    "adaptive_field_schema_log",
    "adaptive_test_set",
    "adaptive_test_ground_truth",
    "adaptive_baseline_runs",
    "adaptive_page_ocr_results",
    "adaptive_document_classifications",
    "adaptive_field_routing_config",    # Day 23
    "adaptive_validation_results",      # Day 21
]


def cmd_status():
    if not verify_connection():
        print("ERROR: Cannot connect to database")
        return
    insp = inspect(engine)
    existing = set(insp.get_table_names(schema="public"))
    print(f"\nDatabase: {engine.url.database}")
    print(f"{'Table':<45} {'Status'}")
    print("-" * 55)
    for t in MANAGED_TABLES:
        status = "EXISTS" if t in existing else "MISSING"
        print(f"  {t:<43} {status}")
    other_adaptive = [t for t in existing if t.startswith("adaptive_") and t not in MANAGED_TABLES]
    if other_adaptive:
        print(f"\nOther adaptive_* tables found: {other_adaptive}")
    print()


def cmd_create():
    if not verify_connection():
        print("ERROR: Cannot connect to database")
        sys.exit(1)
    print("Creating Python-owned tables (skip if exist)...")
    Base.metadata.create_all(engine, checkfirst=True)
    print("Done. Run 'python manage_db.py status' to verify.")


def cmd_drop(confirmed: bool = False):
    if not confirmed:
        answer = input(
            f"\nThis will DROP {len(MANAGED_TABLES)} adaptive_* tables. "
            "Type 'yes' to confirm: "
        ).strip().lower()
        if answer != "yes":
            print("Aborted.")
            return

    print("Dropping Python-owned tables...")
    with engine.begin() as conn:
        for table in reversed(MANAGED_TABLES):
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            print(f"  dropped: {table}")
    print("Done.")


def cmd_recreate():
    print("Recreating Python-owned tables (drop then create)...")
    cmd_drop(confirmed=True)
    cmd_create()


def cmd_seed_schema():
    """Seed the field schema log table from config/field_schema.yaml."""
    from app.core.schema import schema_loader
    from app.config import MODEL_VERSION

    schema_version = schema_loader.schema_version
    print(f"Seeding field schema log — version {schema_version}...")

    with get_db() as session:
        # Check if already seeded for this version
        existing = session.query(FieldSchemaLogRow).filter_by(
            schema_version=schema_version
        ).count()
        if existing > 0:
            print(f"  Schema version {schema_version} already seeded ({existing} rows). Skipping.")
            return

        for fd in schema_loader.all_fields():
            row = FieldSchemaLogRow(
                schema_version=schema_version,
                field_name=fd.canonical_name,
                canonical_name=fd.canonical_name,
                data_type=fd.data_type,
                required=fd.required,
                sections_json=json.dumps(fd.sections),
                synonyms_json=json.dumps(fd.synonyms),
                source_authority=fd.source_authority,
            )
            session.add(row)
        session.flush()
        count = session.query(FieldSchemaLogRow).filter_by(
            schema_version=schema_version
        ).count()
    print(f"  Seeded {count} field definitions for schema version {schema_version}.")


if __name__ == "__main__":
    commands = {
        "create": cmd_create,
        "drop": cmd_drop,
        "recreate": cmd_recreate,
        "status": cmd_status,
        "seed-schema": cmd_seed_schema,
    }
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands)}")
        sys.exit(1)
    commands[cmd]()
