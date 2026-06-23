#!/usr/bin/env bash
# Stop all SHAL services started by start-all.sh. Cross-platform: macOS + Linux.
# Reads logs/<service>.pid, terminates each process tree, removes the pid file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"

stop_one() {
  # Separate declarations: a single `local a=$1 b=$a` expands $a BEFORE the
  # assignment of a, so under `set -u` it errors "name: unbound variable".
  local name="${1:?stop_one requires a service name}"
  local pidf="$LOG_DIR/$name.pid"
  [[ -f "$pidf" ]] || { echo "[stop-all] $name: no pid file — skipping"; return; }

  local pid; pid="$(cat "$pidf" 2>/dev/null || true)"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    echo "[stop-all] $name: not running (stale pid file removed)"
    rm -f "$pidf"; return
  fi

  echo "[stop-all] stopping $name (pid $pid)..."
  # Kill the whole process group so child workers (uvicorn reloader,
  # celery prefork, next.js) also exit.
  if kill -TERM -- "-$pid" 2>/dev/null; then :; else kill -TERM "$pid" 2>/dev/null || true; fi

  # Give it a few seconds, then force-kill if still alive.
  local i
  for ((i=1; i<=10; i++)); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "[stop-all] $name: forcing kill"
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pidf"
  echo "[stop-all] $name stopped"
}

for svc in frontend celery ocr java; do
  stop_one "$svc"
done

echo "[stop-all] Done."
