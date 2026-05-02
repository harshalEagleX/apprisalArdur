"""
manage_db.py — Python equivalent of JPA ddl-auto
=================================================

Manages the Python service's own tables (OCR cache, rule config, feedback, etc.)
using SQLAlchemy's metadata API — the same approach JPA uses under the hood.

Usage:
    python manage_db.py create      # CREATE all tables if they don't exist (ddl-auto=update)
    python manage_db.py drop        # DROP all tables (ddl-auto=none + manual drop)
    python manage_db.py recreate    # DROP then CREATE  (ddl-auto=create-drop equivalent)
    python manage_db.py status      # Show which tables exist

The DATABASE_URL is read from the .env file (same as the FastAPI service).
"""

import sys
import os
from dotenv import load_dotenv

# Load .env so DATABASE_URL is available
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import inspect, text
from app.database import engine, ensure_schema_compatibility

# Import all models so their metadata is registered before we touch the DB
from app.models.db_models import Base as DBBase  # noqa: F401


def _get_defined_tables() -> list[str]:
    """Tables declared in SQLAlchemy models."""
    return sorted(DBBase.metadata.tables.keys())


def _get_existing_tables() -> list[str]:
    """Tables that actually exist in the database right now."""
    inspector = inspect(engine)
    return sorted(inspector.get_table_names())


def cmd_status() -> None:
    """Show table status — which are defined in models vs. exist in DB."""
    defined  = set(_get_defined_tables())
    existing = set(_get_existing_tables())

    print("\n=== Python DB Table Status ===")
    print(f"  Database: {engine.url}\n")

    all_names = sorted(defined | existing)
    for name in all_names:
        in_model = "✓" if name in defined  else " "
        in_db    = "✓" if name in existing else " "
        status   = "OK" if (name in defined and name in existing) else \
                   "MISSING IN DB" if name in defined else "ORPHAN (not in models)"
        print(f"  [{in_model}model] [{in_db}db]  {name:<40}  {status}")

    missing  = defined  - existing
    orphaned = existing - defined
    print(f"\n  Defined: {len(defined)}  |  In DB: {len(existing)}  |  "
          f"Missing: {len(missing)}  |  Orphaned: {len(orphaned)}\n")


def cmd_create() -> None:
    """CREATE all tables that don't yet exist (safe — never drops data)."""
    before = set(_get_existing_tables())
    DBBase.metadata.create_all(bind=engine, checkfirst=True)
    after  = set(_get_existing_tables())
    created = after - before

    if created:
        print(f"✓ Created {len(created)} table(s): {', '.join(sorted(created))}")
    else:
        print("✓ All tables already exist — nothing to create.")


def cmd_update() -> None:
    """Apply safe, additive schema updates for existing local dev databases."""
    ensure_schema_compatibility()
    print("✓ Applied safe schema compatibility updates.")


def cmd_drop() -> None:
    """DROP all model-managed tables (DESTRUCTIVE — all data is lost)."""
    existing = set(_get_existing_tables())
    defined  = set(_get_defined_tables())
    to_drop  = existing & defined

    if not to_drop:
        print("No matching tables found in database — nothing to drop.")
        return

    print(f"⚠  About to DROP {len(to_drop)} table(s): {', '.join(sorted(to_drop))}")
    confirm = input("   Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    DBBase.metadata.drop_all(bind=engine, checkfirst=True)
    print(f"✓ Dropped {len(to_drop)} table(s).")


def cmd_recreate() -> None:
    """DROP then CREATE all tables (equivalent to JPA ddl-auto=create-drop)."""
    defined  = set(_get_defined_tables())
    existing = set(_get_existing_tables())
    to_drop  = existing & defined

    print(f"⚠  RECREATE will DROP {len(to_drop)} Python-managed table(s) and recreate {len(defined)}.")
    print(f"   Java/JPA tables in this DB will NOT be touched.")
    confirm = input("   Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    DBBase.metadata.drop_all(bind=engine, checkfirst=True)
    DBBase.metadata.create_all(bind=engine, checkfirst=True)

    # Only report Python-owned tables, not the full DB (which includes Java/JPA tables)
    after_all = set(_get_existing_tables())
    py_tables = after_all & defined
    print(f"✓ Recreated {len(py_tables)} Python-managed table(s): {', '.join(sorted(py_tables))}")
    orphans = after_all - defined
    if orphans:
        print(f"  (Ignored {len(orphans)} Java/JPA-managed table(s): {', '.join(sorted(orphans))})")


COMMANDS = {
    "status":   cmd_status,
    "create":   cmd_create,
    "update":   cmd_update,
    "drop":     cmd_drop,
    "recreate": cmd_recreate,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()
