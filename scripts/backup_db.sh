#!/usr/bin/env bash
# Scaling Phase 5 (readme/SCALABILITY_PLAN.md) — PostgreSQL logical backup + retention.
#
# Custom-format pg_dump (already compressed, supports parallel/selective restore).
# Schedule via cron/systemd timer, e.g. hourly or nightly. P-15: data is the asset —
# retention removes only OLD backups, never the live DB.
#
#   DB_NAME=shal BACKUP_DIR=/var/backups/shal/db ./scripts/backup_db.sh
#   restore: pg_restore --clean --if-exists -d <db> <file.dump>
set -euo pipefail

DB_NAME="${DB_NAME:-${PGDATABASE:-shal}}"
BACKUP_DIR="${BACKUP_DIR:-./backups/db}"
RETENTION_DAYS="${DB_BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d-%H%M%S)"
out="$BACKUP_DIR/${DB_NAME}-${ts}.dump"

echo "[backup_db] dumping '$DB_NAME' -> $out"
pg_dump --format=custom --no-owner --file="$out" "$DB_NAME"
echo "[backup_db] wrote $(du -h "$out" | cut -f1)"

# Retention: delete dumps older than RETENTION_DAYS (kept ones are the archive).
find "$BACKUP_DIR" -name "${DB_NAME}-*.dump" -type f -mtime +"${RETENTION_DAYS}" -print -delete
echo "[backup_db] done (retention=${RETENTION_DAYS}d)"
