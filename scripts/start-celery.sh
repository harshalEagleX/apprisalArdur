#!/usr/bin/env bash
# Start the SHAL Celery worker (uses Redis as broker + result backend).
# Activates the conda env (default 'shal') and loads .env before launching.
# Always reinstalls Python dependencies so a git pull is immediately reflected.
# Cross-platform: macOS + Linux (Ubuntu).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OCR_DIR="$REPO_ROOT/ocr-service"

# shellcheck source=scripts/_lib.sh
source "$REPO_ROOT/scripts/_lib.sh"

# ── Conda ────────────────────────────────────────────────────
activate_conda

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$REPO_ROOT/.env" ]] && source "$REPO_ROOT/.env"
[[ -f "$OCR_DIR/.env" ]]   && source "$OCR_DIR/.env"
set +a

# ── Required binaries ────────────────────────────────────────
ensure_local_bins

# ── Always reinstall Python dependencies ─────────────────────
echo "[start-celery] Installing/refreshing Python dependencies..."
pip install -q -r "$OCR_DIR/requirements.txt"

# ── Launch ───────────────────────────────────────────────────
cd "$OCR_DIR"
echo "[start-celery] Starting Celery worker (concurrency=2, broker=${REDIS_URL:-redis://localhost:6379/0})"
exec celery -A app.tasks.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=shal-worker@%h
