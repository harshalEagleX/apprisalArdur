#!/usr/bin/env bash
# Bring up the SHAL UAT stack and wait until every service is reachable.
#   bash scripts/uat/up.sh [--build]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.uat.yml --env-file .env.uat)

if [[ ! -f .env.uat ]]; then
  echo "ERROR: .env.uat not found. Run:  cp .env.uat.example .env.uat  then fill in the CHANGE-ME secrets." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env.uat; set +a
OCR_PORT="${OCR_PORT:-5001}"; JAVA_PORT="${JAVA_PORT:-8080}"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "==> Building images…"
"${COMPOSE[@]}" build

echo "==> Starting stack…"
"${COMPOSE[@]}" up -d

wait_for() { # name url
  local name="$1" url="$2" tries=60
  printf "==> Waiting for %s (%s) " "$name" "$url"
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    ((tries--)) || { echo " FAILED"; echo "Recent logs:"; "${COMPOSE[@]}" logs --tail=40 "$name" || true; exit 1; }
    printf "."; sleep 3
  done
  echo " OK"
}
wait_for_tcp() { # name host port
  local name="$1" host="$2" port="$3" tries=60
  printf "==> Waiting for %s (tcp %s:%s) " "$name" "$host" "$port"
  until (exec 3<>/dev/tcp/"$host"/"$port") 2>/dev/null; do
    ((tries--)) || { echo " FAILED"; "${COMPOSE[@]}" logs --tail=40 "$name" || true; exit 1; }
    printf "."; sleep 3
  done
  echo " OK"
}

wait_for ocr-service   "http://localhost:${OCR_PORT}/live"
wait_for_tcp java-backend localhost "${JAVA_PORT}"
wait_for frontend      "http://localhost:${FRONTEND_PORT}"

cat <<EOF

✅ SHAL UAT stack is up.
   Frontend   : http://localhost:${FRONTEND_PORT}
   Java API   : http://localhost:${JAVA_PORT}
   OCR/QC API : http://localhost:${OCR_PORT}
   Prometheus : http://localhost:${PROMETHEUS_PORT:-9090}
   Grafana    : http://localhost:${GRAFANA_PORT:-3001}

   Admin login: ${ADMIN_EMAIL:-harshal@eaglexinfo.com}
   Stop with  : bash scripts/uat/down.sh
EOF
