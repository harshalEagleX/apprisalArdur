#!/usr/bin/env bash
# One-time Python-side setup for SHAL (macOS + Ubuntu).
# Creates the conda env, installs OCR deps, and creates the Python-owned DB tables.
# Idempotent: safe to re-run.
#
#   ./scripts/setup-python.sh
#   CONDA_ENV=myenv ./scripts/setup-python.sh   # use a different env name
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OCR_DIR="$REPO_ROOT/ocr-service"
ENV_NAME="${CONDA_ENV:-shal}"
PY_VER="${PY_VER:-3.11}"

# shellcheck source=scripts/_lib.sh
source "$REPO_ROOT/scripts/_lib.sh"

# ── Locate + source conda (reuses the same detection as the run scripts) ──
locate_conda_sh() {
  local candidates=()
  [[ -n "${CONDA_SH:-}" ]] && candidates+=("$CONDA_SH")
  if command -v conda >/dev/null 2>&1; then
    local base; base="$(conda info --base 2>/dev/null || true)"
    [[ -n "$base" ]] && candidates+=("$base/etc/profile.d/conda.sh")
  fi
  [[ -n "${CONDA_EXE:-}" ]] && candidates+=("$(dirname "$(dirname "$CONDA_EXE")")/etc/profile.d/conda.sh")
  candidates+=(
    "$HOME/miniconda3/etc/profile.d/conda.sh"
    "$HOME/anaconda3/etc/profile.d/conda.sh"
    "$HOME/miniforge3/etc/profile.d/conda.sh"
    "$HOME/mambaforge/etc/profile.d/conda.sh"
    "/opt/conda/etc/profile.d/conda.sh"
    "/opt/miniconda3/etc/profile.d/conda.sh"
    "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    "/usr/local/Caskroom/miniconda/base/etc/profile.d/conda.sh"
  )
  local c
  for c in "${candidates[@]}"; do [[ -f "$c" ]] && { echo "$c"; return 0; }; done
  return 1
}

CONDA_SH_PATH="$(locate_conda_sh || true)"
if [[ -z "$CONDA_SH_PATH" ]]; then
  echo "[setup-python] ERROR: conda not found. Install Miniconda first:" >&2
  echo "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && bash Miniconda3-latest-Linux-x86_64.sh" >&2
  exit 1
fi
set +u
# shellcheck disable=SC1090
source "$CONDA_SH_PATH"
set -u
echo "[setup-python] using conda: $CONDA_SH_PATH"

# ── Accept channel Terms of Service (the CondaToSNonInteractiveError fix) ──
# Newer conda refuses to use the defaults channels until ToS is accepted.
if conda tos --help >/dev/null 2>&1; then
  for ch in "https://repo.anaconda.com/pkgs/main" "https://repo.anaconda.com/pkgs/r"; do
    conda tos accept --override-channels --channel "$ch" >/dev/null 2>&1 || true
  done
  echo "[setup-python] conda ToS accepted (defaults channels)"
fi

# ── Create the env if missing ────────────────────────────────────────
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "[setup-python] conda env '$ENV_NAME' already exists — reusing"
else
  echo "[setup-python] creating conda env '$ENV_NAME' (python $PY_VER)..."
  # conda-forge avoids the defaults-channel ToS entirely as a fallback.
  conda create -n "$ENV_NAME" "python=$PY_VER" -y \
    || conda create -n "$ENV_NAME" "python=$PY_VER" -y -c conda-forge --override-channels
fi

# ── Activate + install requirements ──────────────────────────────────
set +u
conda activate "$ENV_NAME"
set -u
echo "[setup-python] activated '$ENV_NAME' ($(python --version 2>&1))"

echo "[setup-python] installing OCR requirements (this can take a few minutes)..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$OCR_DIR/requirements.txt"

# ── Verify the heavy native imports actually load ────────────────────
echo "[setup-python] verifying imports..."
python - <<'PY'
import importlib, sys
mods = ["fastapi","uvicorn","celery","redis","fitz","pdfplumber","camelot",
        "cv2","pytesseract","sqlalchemy","psycopg2","slowapi","sklearn","pandas","numpy"]
bad = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        bad.append(f"{m}: {e}")
if bad:
    print("IMPORT FAILURES:\n  " + "\n  ".join(bad)); sys.exit(1)
print("all core OCR imports OK")
PY

# ── Ensure .env exists, then create Python-owned tables ──────────────
[[ -f "$REPO_ROOT/.env" ]] || bash "$REPO_ROOT/scripts/init-env.sh"

set -a
[[ -f "$REPO_ROOT/.env" ]] && source "$REPO_ROOT/.env"
[[ -f "$OCR_DIR/.env" ]]   && source "$OCR_DIR/.env"
set +a

echo "[setup-python] creating Python-owned DB tables (manage_db.py create)..."
( cd "$OCR_DIR" && python manage_db.py create )

cat <<EOF

[setup-python] Python side ready.
  conda env : $ENV_NAME ($(python --version 2>&1))
  DB tables : created/verified in shal_qc
  Next      : ./scripts/start-all.sh
EOF
