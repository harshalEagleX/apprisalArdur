#!/usr/bin/env bash
# Stop the no-Docker local UAT stack started by run-local.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT/.uat-run"

# Prefer PID files; fall back to process-name patterns.
for name in frontend java celery ocr; do
  pidf="$RUN_DIR/$name.pid"
  if [[ -f "$pidf" ]]; then
    pid="$(cat "$pidf")"
    if kill -0 "$pid" 2>/dev/null; then echo "==> Stopping $name (pid $pid)"; kill "$pid" 2>/dev/null || true; fi
    rm -f "$pidf"
  fi
done

# Safety net for anything spawned that outlived its parent.
pkill -f "app-0.0.1-SNAPSHOT.jar" 2>/dev/null || true
pkill -f "uvicorn main:app"       2>/dev/null || true
pkill -f "celery -A celery_app"   2>/dev/null || true
pkill -f "next start"             2>/dev/null || true

echo "Done."
