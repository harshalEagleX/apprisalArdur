#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DDL snapshot for the shared Postgres schema (MIG-003 / MIG-006 / DB-006).
#
# The project deliberately uses NO migration runner (Java = Hibernate ddl-auto,
# Python = manage_db.py). The gap that leaves is: there is no reviewed record of
# what the schema looked like at each release, so `ddl-auto=validate` has nothing
# to diff against and cross-service schema changes are invisible in review.
#
# This script captures a schema-only snapshot (no data) into db-snapshots/, named
# by date + git short-sha. Commit the snapshot with the release. The diff between
# two snapshots IS your migration note — review it before deploying.
#
# Usage:
#   DB_URL='postgresql://user:pass@host:5432/shal' scripts/db/snapshot_schema.sh
# or rely on the same DATABASE_URL the services use.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DB="${DB_URL:-${DATABASE_URL:-postgresql://localhost:5432/shal}}"
OUT_DIR="$(cd "$(dirname "$0")/../.." && pwd)/db-snapshots"
mkdir -p "$OUT_DIR"

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/schema-${STAMP}-${SHA}.sql"

echo "Snapshotting schema from: ${DB%%\?*}"
# --schema-only: structure only, never data (PII-safe). --no-owner/--no-privileges
# keep the diff focused on structure rather than environment-specific grants.
pg_dump "$DB" --schema-only --no-owner --no-privileges --file "$OUT"

echo "Wrote $OUT"
echo "Review the diff vs the previous snapshot before releasing:"
PREV="$(ls -1 "$OUT_DIR"/schema-*.sql 2>/dev/null | grep -v "$OUT" | tail -1 || true)"
if [[ -n "${PREV:-}" ]]; then
  echo "  diff '$PREV' '$OUT'"
else
  echo "  (this is the first snapshot — it becomes the baseline)"
fi
