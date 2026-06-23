#!/usr/bin/env bash
# Master launcher for all SHAL platform services. Cross-platform: macOS + Linux (Ubuntu).
#
# Runs each service as a background process, writing logs to logs/<service>.log
# and PIDs to logs/<service>.pid. Works headless (Ubuntu servers) and on a desktop.
# Stop everything with: ./scripts/stop-all.sh
#
#   1. Java Spring Boot     — http://localhost:8080
#   2. Python OCR (FastAPI) — http://localhost:5001
#   3. Celery worker        — redis broker
#   4. Next.js frontend     — http://localhost:3000
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$REPO_ROOT/scripts"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

# shellcheck source=scripts/_lib.sh
source "$SCRIPTS/_lib.sh"

# ── Infrastructure checks ────────────────────────────────────
echo "[start-all] Checking infrastructure..."

# PostgreSQL: prefer pg_isready (authoritative, handles unix sockets);
# fall back to a TCP probe; if neither confirms, warn but don't block.
if command -v pg_isready >/dev/null 2>&1; then
  pg_isready -q 2>/dev/null || { echo "[start-all] ERROR: PostgreSQL not reachable. Start it:  $(infra_hint postgres)"; exit 1; }
  echo "[start-all] PostgreSQL: OK"
elif port_open localhost 5432; then
  echo "[start-all] PostgreSQL: OK (tcp)"
else
  echo "[start-all] WARN: could not verify PostgreSQL (no pg_isready, :5432 closed). Continuing — if it's down:  $(infra_hint postgres)"
fi

# Redis: prefer redis-cli ping; fall back to TCP probe; else warn.
if command -v redis-cli >/dev/null 2>&1; then
  [[ "$(redis-cli ping 2>/dev/null)" == "PONG" ]] || { echo "[start-all] ERROR: Redis not responding. Start it:  $(infra_hint redis)"; exit 1; }
  echo "[start-all] Redis:      OK"
elif port_open localhost 6379; then
  echo "[start-all] Redis:      OK (tcp)"
else
  echo "[start-all] WARN: could not verify Redis (no redis-cli, :6379 closed). Continuing — if it's down:  $(infra_hint redis)"
fi

# Enable job control so each '&' service runs in its OWN process group;
# stop-all.sh then kills the whole group (uvicorn reloader, celery prefork,
# next.js children) via the leader PID. Works on macOS (no setsid) + Linux.
set -m

# ── Background runner ────────────────────────────────────────
start_bg() {
  local name="$1" script="$2"
  local log="$LOG_DIR/$name.log" pidf="$LOG_DIR/$name.pid"

  if [[ -f "$pidf" ]] && kill -0 "$(cat "$pidf" 2>/dev/null)" 2>/dev/null; then
    echo "[start-all] $name already running (pid $(cat "$pidf")) — skipping"
    return
  fi

  echo "[start-all] starting $name  →  $log"
  nohup bash "$script" >"$log" 2>&1 &
  echo $! >"$pidf"
}

# ── Wait for a TCP port to come up (best-effort) ─────────────
wait_port() {
  local name="$1" port="$2" tries="${3:-60}"
  local i
  for ((i=1; i<=tries; i++)); do
    port_open localhost "$port" && { echo "[start-all] $name is up on :$port"; return 0; }
    sleep 1
  done
  echo "[start-all] WARN: $name not up on :$port after ${tries}s — check $LOG_DIR/$name.log"
  return 0
}

# ── Launch services ──────────────────────────────────────────
start_bg "java"     "$SCRIPTS/start-java.sh"
start_bg "ocr"      "$SCRIPTS/start-ocr.sh"
start_bg "celery"   "$SCRIPTS/start-celery.sh"
start_bg "frontend" "$SCRIPTS/start-frontend.sh"

echo ""
echo "[start-all] Waiting for services to become reachable..."
wait_port "ocr"      5001 60
wait_port "java"     8080 90
wait_port "frontend" 3000 60

cat <<EOF

[start-all] All services launched.

  Java backend  → http://localhost:8080
  OCR service   → http://localhost:5001/health
  Frontend      → http://localhost:3000

  Logs:  tail -f $LOG_DIR/{java,ocr,celery,frontend}.log
  Stop:  $SCRIPTS/stop-all.sh

  Login: harshal@eaglexinfo.com / Admin123!
EOF
