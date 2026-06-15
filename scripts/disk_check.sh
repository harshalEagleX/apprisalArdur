#!/usr/bin/env bash
# Scaling Phase 5 (readme/SCALABILITY_PLAN.md) — disk + inode usage alert.
#
# Exits non-zero (and prints to stderr) when any watched volume crosses the threshold,
# so a cron/systemd timer or monitoring agent can alert. 5,000 docs × up to 25 MB needs
# ~150 GB headroom on the uploads volume — catch exhaustion before ingest fails.
#
#   DISK_ALERT_PCT=80 STORAGE_PATH=./uploads BACKUP_DIR=./backups ./scripts/disk_check.sh
set -uo pipefail

THRESHOLD="${DISK_ALERT_PCT:-80}"
PATHS=("${STORAGE_PATH:-./uploads}" "${BACKUP_DIR:-./backups}")
rc=0

for p in "${PATHS[@]}"; do
  [ -e "$p" ] || continue
  disk="$(df -P  "$p" | awk 'NR==2 {gsub("%","",$5); print $5}')"
  inode="$(df -Pi "$p" | awk 'NR==2 {gsub("%","",$5); print $5}')"
  echo "[disk_check] $p  disk=${disk}%  inode=${inode}%"
  if [ "${disk:-0}" -ge "$THRESHOLD" ] || [ "${inode:-0}" -ge "$THRESHOLD" ]; then
    echo "[disk_check] ALERT: '$p' at or above ${THRESHOLD}% (disk=${disk}% inode=${inode}%)" >&2
    rc=1
  fi
done
exit "$rc"
