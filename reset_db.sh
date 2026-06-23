#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# reset_db.sh — Full database reset for SHAL platform
#
# Drops ALL tables (Java + Python) from the shared PostgreSQL database, then
# recreates the Python-managed tables with manage_db.py recreate. Java tables
# are managed by JPA/Hibernate when the Spring Boot app starts. No Flyway.
#
# Usage:
#   bash reset_db.sh          # interactive confirmation
#   bash reset_db.sh --yes    # skip confirmation (CI / scripted use)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OCR_DIR="$SCRIPT_DIR/ocr-service"

# ── Load .env files ───────────────────────────────────────────────────────────
# ocr-service/.env has DATABASE_URL in standard psql format — use it for psql.
# Root .env has DB_URL in jdbc: format — used as fallback.
OCR_ENV="$OCR_DIR/.env"
ROOT_ENV="$SCRIPT_DIR/.env"

set -a
if [[ -f "$OCR_ENV" ]]; then
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$OCR_ENV" | grep -v '^\s*$')
fi
if [[ -f "$ROOT_ENV" ]]; then
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$ROOT_ENV" | grep -v '^\s*$')
fi
set +a

# ── Resolve psql-compatible URL ───────────────────────────────────────────────
# DATABASE_URL from ocr-service/.env uses postgresql+psycopg2:// — strip the driver
if [[ -n "${DATABASE_URL:-}" ]]; then
    PSQL_URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
elif [[ -n "${DB_URL:-}" ]]; then
    # jdbc:postgresql://host/db?params  →  postgresql://user:pass@host/db?params
    BASE="${DB_URL#jdbc:}"
    HOST_PATH="${BASE#postgresql://}"
    PSQL_URL="postgresql://${DB_USERNAME:-postgres}:${DB_PASSWORD:-}@${HOST_PATH}"
else
    echo "ERROR: Neither DATABASE_URL nor DB_URL found in .env files" >&2
    exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
if [[ "${1:-}" != "--yes" ]]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║              ⚠   FULL DATABASE RESET   ⚠            ║"
    echo "╠══════════════════════════════════════════════════════╣"
    echo "║  This will DROP ALL TABLES — ALL DATA IS LOST.       ║"
    echo "║                                                       ║"
    echo "║  After reset:                                         ║"
    echo "║  • Python tables → manage_db.py recreate             ║"
    echo "║  • Java tables   → JPA/Hibernate on app start        ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    read -r -p "  Type 'yes' to continue: " confirm
    [[ "$confirm" != "yes" ]] && { echo "Aborted."; exit 0; }
fi

# ── Step 1: Drop and recreate public schema ───────────────────────────────────
echo ""
echo "Step 1/3 — Dropping all tables (DROP SCHEMA CASCADE)..."
psql "$PSQL_URL" <<-'SQL'
    DROP SCHEMA IF EXISTS public CASCADE;
    CREATE SCHEMA public;
    GRANT ALL ON SCHEMA public TO PUBLIC;
SQL
echo "  ✓ Schema cleared."

# ── Step 2: Recreate Python-managed tables ────────────────────────────────────
echo ""
echo "Step 2/3 — Recreating Python-managed tables..."
if [[ ! -d "$OCR_DIR" ]]; then
    echo "  WARNING: ocr-service directory not found at $OCR_DIR — skipping Python tables."
else
    PYTHON="${PYTHON_CMD:-python}"
    cd "$OCR_DIR"
    printf 'yes\n' | $PYTHON manage_db.py recreate
    echo ""
    echo "  → Seeding rules_config (146 rules)..."
    $PYTHON -c "
from dotenv import load_dotenv; load_dotenv()
from app.rule_engine.rules_db import seed_rules_config, load_rule_configs
seed_rules_config()
n = len(load_rule_configs())
print(f'  ✓ rules_config seeded — {n} rules.')
"
    cd "$SCRIPT_DIR"
fi

# ── Step 3: Instructions for Java / JPA-Hibernate ─────────────────────────────
echo ""
echo "Step 3/3 — Java tables (JPA/Hibernate)"
echo "  ✓ Hibernate will manage Java-owned tables on next Spring Boot startup."
echo "  ✓ Flyway/Liquibase/third-party migration runners are intentionally not used."

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Reset complete. Start the Java app to finish:"
echo ""
echo "    Option A — Maven:"
echo "      cd $SCRIPT_DIR"
echo "      ./mvnw spring-boot:run"
echo ""
echo "    Option B — IntelliJ:"
echo "      Run ShalApplication.java"
echo ""
echo "  After Java starts, verify Hibernate connects cleanly and creates/updates Java-owned tables."
echo "══════════════════════════════════════════════════════════"
