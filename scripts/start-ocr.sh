#!/usr/bin/env bash
# Start the SHAL Python OCR / FastAPI service on port 5001.
# Activates the 'shal' conda env and loads .env before launching uvicorn.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OCR_DIR="$REPO_ROOT/ocr-service"

# ── Conda ────────────────────────────────────────────────────
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
if [[ ! -f "$CONDA_SH" ]]; then
  echo "[start-ocr] ERROR: conda init script not found at $CONDA_SH"; exit 1
fi
# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate shal

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$REPO_ROOT/.env" ]]     && source "$REPO_ROOT/.env"
[[ -f "$OCR_DIR/.env" ]]       && source "$OCR_DIR/.env"
set +a

# ── Required binaries ────────────────────────────────────────
export PATH="/opt/homebrew/bin:$PATH"
for bin in tesseract pdftoppm pdfinfo; do
  command -v "$bin" >/dev/null 2>&1 || { echo "[start-ocr] WARN: $bin not found in PATH"; }
done

# ── Launch ───────────────────────────────────────────────────
cd "$OCR_DIR"
echo "[start-ocr] Starting uvicorn on http://0.0.0.0:5001 (env: shal)"
exec uvicorn main:app --host 0.0.0.0 --port 5001 --reload
