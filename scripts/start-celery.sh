#!/usr/bin/env bash
# Start the SHAL Celery worker (uses Redis as broker + result backend).
# Activates the 'shal' conda env and loads .env before launching.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OCR_DIR="$REPO_ROOT/ocr-service"

# ── Conda ────────────────────────────────────────────────────
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
if [[ ! -f "$CONDA_SH" ]]; then
  echo "[start-celery] ERROR: conda init script not found at $CONDA_SH"; exit 1
fi
# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate shal

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$REPO_ROOT/.env" ]]  && source "$REPO_ROOT/.env"
[[ -f "$OCR_DIR/.env" ]]    && source "$OCR_DIR/.env"
set +a

# ── Required binaries ────────────────────────────────────────
export PATH="/opt/homebrew/bin:$PATH"

# ── Launch ───────────────────────────────────────────────────
cd "$OCR_DIR"
echo "[start-celery] Starting Celery worker (concurrency=2, broker=$REDIS_URL)"
exec celery -A app.tasks.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=shal-worker@%h
