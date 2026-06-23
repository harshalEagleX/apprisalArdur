#!/usr/bin/env bash
# Start the SHAL Python OCR / FastAPI service on port 5001.
# Activates the conda env (default 'shal') and loads .env before launching uvicorn.
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
for bin in tesseract pdftoppm pdfinfo; do
  command -v "$bin" >/dev/null 2>&1 || echo "[start-ocr] WARN: '$bin' not found in PATH (install tesseract / poppler-utils)"
done

# ── Launch ───────────────────────────────────────────────────
cd "$OCR_DIR"
echo "[start-ocr] Starting uvicorn on http://0.0.0.0:5001"
exec uvicorn main:app --host 0.0.0.0 --port 5001 --reload
