#!/usr/bin/env bash
# Full data reset for the running UAT stack — mirrors reset_db.sh but inside compose.
# Drops ALL tables (Java + Python), then lets each service recreate its own:
#   • Python-owned tables  -> manage_db.py create (on ocr-service restart)
#   • Java-owned tables    -> JPA/Hibernate (on java-backend restart)
# No Flyway/Alembic (DB Schema Policy).
#   bash scripts/uat/reset-data.sh --yes
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker-compose.uat.yml --env-file .env.uat)

# shellcheck disable=SC1091
set -a; source .env.uat; set +a
DB_NAME="${DB_NAME:-ardurApprisal}"; DB_USERNAME="${DB_USERNAME:-apprisal}"

if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "This DROPS ALL data in UAT '${DB_NAME}'. Type 'yes' to confirm: " ans
  [[ "$ans" == "yes" ]] || { echo "Aborted."; exit 0; }
fi

echo "==> Dropping public schema…"
"${COMPOSE[@]}" exec -T postgres \
  psql -U "$DB_USERNAME" -d "$DB_NAME" \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "==> Recreating service schemas (restarting ocr-service + java-backend)…"
"${COMPOSE[@]}" restart ocr-service celery-worker java-backend

echo "✅ UAT data reset. Admin user re-seeds on Java startup."
