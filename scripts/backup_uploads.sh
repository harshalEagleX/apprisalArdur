#!/usr/bin/env bash
# Scaling Phase 5 (readme/SCALABILITY_PLAN.md) — document-store snapshot backup.
#
# Space-efficient hardlink snapshots (rsync --link-dest): each snapshot is a full,
# browsable tree, but files unchanged since the previous snapshot are hardlinks, so
# only changed/new documents consume new space. Schedule nightly.
#
#   STORAGE_PATH=./uploads UPLOADS_BACKUP_DIR=/var/backups/apprisal/uploads ./scripts/backup_uploads.sh
#
# For off-host durability point UPLOADS_BACKUP_DIR at a mounted second volume / NAS,
# or wrap with restic/rclone to push the latest snapshot offsite.
set -euo pipefail

SRC="${STORAGE_PATH:-./uploads}"
DEST="${UPLOADS_BACKUP_DIR:-./backups/uploads}"
RETENTION="${UPLOADS_BACKUP_RETENTION:-14}"   # number of snapshots to keep

[ -d "$SRC" ] || { echo "[backup_uploads] source '$SRC' not found" >&2; exit 1; }
mkdir -p "$DEST"
ts="$(date +%Y%m%d-%H%M%S)"
target="$DEST/snapshot-$ts"
latest="$(ls -1dt "$DEST"/snapshot-* 2>/dev/null | head -1 || true)"

if [ -n "$latest" ]; then
  echo "[backup_uploads] incremental snapshot (link-dest=$latest)"
  rsync -a --delete --link-dest="$latest" "$SRC"/ "$target"/
else
  echo "[backup_uploads] first full snapshot"
  rsync -a "$SRC"/ "$target"/
fi
echo "[backup_uploads] snapshot -> $target"

# Retention: keep the newest N snapshots.
ls -1dt "$DEST"/snapshot-* | tail -n +"$((RETENTION + 1))" | xargs -r rm -rf
echo "[backup_uploads] done (keeping newest ${RETENTION} snapshots)"
