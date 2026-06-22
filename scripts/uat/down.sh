#!/usr/bin/env bash
# Stop the SHAL UAT stack.
#   bash scripts/uat/down.sh           # stop containers, keep volumes (data persists)
#   bash scripts/uat/down.sh --wipe    # also remove volumes (DB/redis/uploads gone)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker-compose.uat.yml --env-file .env.uat)

if [[ "${1:-}" == "--wipe" ]]; then
  echo "==> Stopping stack and REMOVING volumes (all UAT data will be lost)…"
  "${COMPOSE[@]}" down -v
else
  echo "==> Stopping stack (volumes kept)…"
  "${COMPOSE[@]}" down
fi
echo "Done."
