#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run-local.sh — Bring up the SHAL stack WITHOUT Docker, each service on its own
# port, using your already-running local PostgreSQL + Redis.
#
#   Java backend : http://localhost:8080   (jar, SPRING_PROFILES_ACTIVE=uat)
#   OCR/QC API   : http://localhost:5001   (uvicorn)
#   Celery worker: (background, Redis broker)
#   Frontend     : http://localhost:3000   (next build + start)
#
# Prereqs (this script does NOT install or manage them):
#   • PostgreSQL running with the app DB (default shal) reachable
#   • Redis running on 127.0.0.1:6379
#   • Java 21 + Maven wrapper; Node 20+; a Python env with ocr-service deps active
#     (e.g. `conda activate shal`) BEFORE running this script
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
load_env() { [[ -f "$1" ]] && { set -a; # shellcheck disable=SC1090
  source "$1"; set +a; echo "  sourced $1"; }; }
echo "==> Loading environment"
load_env "$ROOT/.env"
load_env "$ROOT/.env.uat"

# UAT profile + sane local defaults. COOKIE_SECURE stays false (plain http on localhost).
export SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-uat}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export OCR_SERVICE_URL="${OCR_SERVICE_URL:-http://127.0.0.1:5001}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export NEXT_PUBLIC_JAVA_URL="${NEXT_PUBLIC_JAVA_URL:-http://localhost:8080}"
JAVA_PORT="${JAVA_PORT:-8080}"; OCR_PORT="${OCR_PORT:-5001}"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"

JAR="app/target/app-0.0.1-SNAPSHOT.jar"

# ── preflight ────────────────────────────────────────────────────────────────
command -v uvicorn >/dev/null || { echo "ERROR: 'uvicorn' not on PATH — activate your Python env (e.g. conda activate shal)"; exit 1; }
command -v npm     >/dev/null || { echo "ERROR: 'npm' not on PATH"; exit 1; }

start_bg() { # name "command…"
  local name="$1"; shift
  echo "==> Starting $name"
  ( "$@" >"$RUN_DIR/$name.log" 2>&1 & echo $! >"$RUN_DIR/$name.pid" )
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

# ── 1. OCR service (FastAPI) ─────────────────────────────────────────────────
( cd ocr-service && start_bg ocr uvicorn main:app --host 0.0.0.0 --port "$OCR_PORT" )
wait_http ocr "http://127.0.0.1:${OCR_PORT}/live"

# ── 2. Celery worker (non-fatal if Redis missing — Java falls back to sync) ──
( cd ocr-service && start_bg celery celery -A celery_app worker --loglevel=info --concurrency=2 ) || true

# ── 3. Java backend ──────────────────────────────────────────────────────────
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
   OCR/QC API : http://localhost:${OCR_PORT}
   Admin login: ${ADMIN_EMAIL:-harshal@eaglexinfo.com}

   Logs : $RUN_DIR/{ocr,celery,java,frontend}.log
   Stop : bash scripts/uat/stop-local.sh
EOF
