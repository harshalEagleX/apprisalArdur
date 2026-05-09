#!/usr/bin/env bash
set -euo pipefail

# Run OCR-service Alembic migrations against the configured PostgreSQL database.
#
# Usage from repo root:
#   bash scripts/run_ocr_migrations.sh
#
# Optional:
#   DATABASE_URL="postgresql+psycopg2://user:pass@host/db?sslmode=require" bash scripts/run_ocr_migrations.sh
#   DRY_RUN=1 bash scripts/run_ocr_migrations.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OCR_DIR="${ROOT_DIR}/ocr-service"

if [[ "${LOAD_ENV:-true}" != "false" ]]; then
  set -a
  [[ -f "${ROOT_DIR}/.env" ]] && source "${ROOT_DIR}/.env"
  [[ -f "${OCR_DIR}/.env" ]] && source "${OCR_DIR}/.env"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" && -n "${DB_URL:-}" ]]; then
  if [[ -z "${DB_USERNAME:-}" || -z "${DB_PASSWORD:-}" ]]; then
    echo "DATABASE_URL is not set and DB_USERNAME/DB_PASSWORD are missing for DB_URL conversion." >&2
    exit 2
  fi
  jdbc_target="${DB_URL#jdbc:postgresql://}"
  export DATABASE_URL="postgresql+psycopg2://${DB_USERNAME}:${DB_PASSWORD}@${jdbc_target}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required. Set it directly or provide DB_URL, DB_USERNAME, and DB_PASSWORD." >&2
  exit 2
fi

if [[ "${DATABASE_URL}" == postgresql://* ]]; then
  export DATABASE_URL="postgresql+psycopg2://${DATABASE_URL#postgresql://}"
fi

export PYTHONPATH="${OCR_DIR}:${PYTHONPATH:-}"

cd "${OCR_DIR}"

echo "== OCR migration target =="
python - <<'PY'
import os
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
print(f"dialect={url.drivername}")
print(f"host={url.host}")
print(f"database={url.database}")
print(f"username={url.username}")
PY

echo "== DB connectivity check =="
python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
with engine.connect() as conn:
    version = conn.execute(text("select version()")).scalar()
print(version)
PY

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "== Alembic dry run SQL =="
  python -m alembic -c alembic.ini upgrade head --sql
  exit 0
fi

echo "== Alembic current before =="
python -m alembic -c alembic.ini current

echo "== Applying Alembic migrations =="
python -m alembic -c alembic.ini upgrade head

echo "== Alembic current after =="
python -m alembic -c alembic.ini current

echo "== Verifying OCR lifecycle schema =="
python - <<'PY'
import os
from sqlalchemy import create_engine, text

required_tables = {
    "processing_jobs",
    "processing_stages",
    "llm_call_logs",
    "confidence_calibration",
}
required_columns = {
    ("extracted_fields", "processing_job_id"),
    ("rule_results", "processing_job_id"),
    ("feedback_events", "processing_job_id"),
    ("feedback_events", "correlation_id"),
    ("confidence_calibration", "historical_recall"),
}

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
with engine.connect() as conn:
    tables = {
        row[0]
        for row in conn.execute(text("""
            select table_name
            from information_schema.tables
            where table_schema = 'public'
        """))
    }
    columns = {
        (row[0], row[1])
        for row in conn.execute(text("""
            select table_name, column_name
            from information_schema.columns
            where table_schema = 'public'
        """))
    }

missing_tables = sorted(required_tables - tables)
missing_columns = sorted(required_columns - columns)

if missing_tables or missing_columns:
    print("Missing tables:", missing_tables)
    print("Missing columns:", missing_columns)
    raise SystemExit(1)

print("Schema verification passed.")
PY

echo "OCR migrations completed successfully."
