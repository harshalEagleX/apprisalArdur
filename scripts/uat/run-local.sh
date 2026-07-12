#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run-local.sh — Bring up the SHAL stack WITHOUT Docker, each service on its own
# port, using your already-running local PostgreSQL + Redis.
#
#   Java backend : http://localhost:8080   (jar, SPRING_PROFILES_ACTIVE=uat)
#   Frontend     : http://localhost:3000   (next build + start)
#
# Prereqs (this script does NOT install or manage them):
#   • PostgreSQL running with the app DB (default shal) reachable
#   • Redis running on 127.0.0.1:6379
#   • Java 21 + Maven wrapper; Node 20+
#   • Secrets in ./.env (dev) and/or ./.env.uat — this script sources both if present
#
# Usage:
#   bash scripts/uat/run-local.sh            # start everything (build jar/frontend if needed)
#   bash scripts/uat/run-local.sh --rebuild  # force rebuild of jar + frontend
#   bash scripts/uat/stop-local.sh           # stop everything
# Logs + PIDs live in ./.uat-run/
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
RUN_DIR="$ROOT/.uat-run"
mkdir -p "$RUN_DIR"
REBUILD="${1:-}"

# ── load env (dev first, then uat overrides) ─────────────────────────────────
load_env() {
  if [[ -f "$1" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$1"
    set +a
    echo "  sourced $1"
  fi
}
echo "==> Loading environment"
load_env "$ROOT/.env"
load_env "$ROOT/.env.uat"

# UAT profile + sane local defaults. COOKIE_SECURE stays false (plain http on localhost).
export SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-uat}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export NEXT_PUBLIC_JAVA_URL="${NEXT_PUBLIC_JAVA_URL:-http://localhost:8080}"
JAVA_PORT="${JAVA_PORT:-8080}"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"

JAR="app/target/app-0.0.1-SNAPSHOT.jar"

# ── preflight ────────────────────────────────────────────────────────────────
command -v npm     >/dev/null || { echo "ERROR: 'npm' not on PATH"; exit 1; }

start_bg() { # name "command…"
  local name="$1"; shift
  echo "==> Starting $name"
  (
    nohup "$@" >"$RUN_DIR/$name.log" 2>&1 </dev/null &
    echo $! >"$RUN_DIR/$name.pid"
  )
}

wait_http() { # name url
  local name="$1" url="$2" tries=60
  printf "==> Waiting for %s (%s) " "$name" "$url"
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    ((tries--)) || { echo " FAILED"; echo "--- last 30 log lines ---"; tail -n 30 "$RUN_DIR/$name.log" 2>/dev/null; exit 1; }
    printf "."; sleep 2
  done; echo " OK"
}
wait_tcp() { # name port
  local name="$1" port="$2" tries=90
  printf "==> Waiting for %s (tcp :%s) " "$name" "$port"
  until (exec 3<>/dev/tcp/127.0.0.1/"$port") 2>/dev/null; do
    ((tries--)) || { echo " FAILED"; tail -n 30 "$RUN_DIR/$name.log" 2>/dev/null; exit 1; }
    printf "."; sleep 2
  done; echo " OK"
}

# ── 1. Java backend ──────────────────────────────────────────────────────────
if [[ ! -f "$JAR" || "$REBUILD" == "--rebuild" ]]; then
  echo "==> Building Java jar (mvnw -pl app -am -DskipTests package)…"
  ./mvnw -q -B -pl app -am -DskipTests package
fi
start_bg java java -jar "$JAR"
wait_tcp java "$JAVA_PORT"

# ── 4. Frontend (build once, then start) ─────────────────────────────────────
if [[ ! -d frontend/.next || "$REBUILD" == "--rebuild" ]]; then
  echo "==> Building frontend (npm ci + build)…"
  ( cd frontend && npm ci && NEXT_PUBLIC_JAVA_URL="$NEXT_PUBLIC_JAVA_URL" npm run build )
fi
( cd frontend && start_bg frontend npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" )
wait_http frontend "http://127.0.0.1:${FRONTEND_PORT}"

cat <<EOF

✅ SHAL UAT (local, no Docker) is up.
   Frontend   : http://localhost:${FRONTEND_PORT}
   Java API   : http://localhost:${JAVA_PORT}
   Admin login: ${ADMIN_EMAIL:-harshal@eaglexinfo.com}

   Logs : $RUN_DIR/{java,frontend}.log
   Stop : bash scripts/uat/stop-local.sh
EOF
