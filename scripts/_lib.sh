#!/usr/bin/env bash
# Shared helpers for SHAL service scripts. Cross-platform: macOS + Linux (Ubuntu).
# This file is meant to be *sourced*, not executed.

# ── Resolve + source conda, then activate the target env ─────────────
# Honors $CONDA_SH (explicit path to etc/profile.d/conda.sh) and
# $CONDA_ENV (env name, default 'shal'). Searches the common install
# locations on both macOS and Linux.
activate_conda() {
  local env_name="${CONDA_ENV:-shal}"
  local candidates=()

  # 1. Explicit override.
  [[ -n "${CONDA_SH:-}" ]] && candidates+=("$CONDA_SH")

  # 2. conda already on PATH → ask it for its base.
  if command -v conda >/dev/null 2>&1; then
    local base; base="$(conda info --base 2>/dev/null || true)"
    [[ -n "$base" ]] && candidates+=("$base/etc/profile.d/conda.sh")
  fi

  # 3. CONDA_EXE is exported once conda is initialized in a shell.
  [[ -n "${CONDA_EXE:-}" ]] && candidates+=("$(dirname "$(dirname "$CONDA_EXE")")/etc/profile.d/conda.sh")

  # 4. Common install locations (Linux first, then macOS).
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

  local conda_sh=""
  local c
  for c in "${candidates[@]}"; do
    [[ -f "$c" ]] && { conda_sh="$c"; break; }
  done

  if [[ -z "$conda_sh" ]]; then
    echo "[conda] ERROR: could not locate conda.sh." >&2
    echo "[conda]   Install Miniconda, or set CONDA_SH=/path/to/etc/profile.d/conda.sh" >&2
    exit 1
  fi

  # conda.sh / 'conda activate' can reference unbound vars under 'set -u';
  # relax it for the activation only.
  set +u
  # shellcheck disable=SC1090
  source "$conda_sh"
  if conda activate "$env_name" 2>/dev/null; then
    set -u
    echo "[conda] activated '$env_name' ($conda_sh)"
    return 0
  fi

  # Requested env missing → fall back to 'base' (deps may be installed there,
  # e.g. an Ubuntu box where requirements went into base). Warn, don't die.
  echo "[conda] WARN: env '$env_name' not found — falling back to 'base'." >&2
  echo "[conda]   (To use a dedicated env: conda create -n $env_name python=3.11 -y" >&2
  echo "[conda]    && conda activate $env_name && pip install -r ocr-service/requirements.txt," >&2
  echo "[conda]    or set CONDA_ENV=<name>.)" >&2
  if conda activate base 2>/dev/null; then
    set -u
    echo "[conda] activated 'base' ($conda_sh)"
    return 0
  fi

  set -u
  echo "[conda] ERROR: could not activate '$env_name' or 'base'." >&2
  exit 1
}

# ── Prepend known local bin dirs to PATH, only if they exist ─────────
# macOS Homebrew lives in /opt/homebrew/bin or /usr/local/bin; on Linux
# the OCR binaries (tesseract, poppler) are already in /usr/bin. No-op
# for any dir that doesn't exist, so this is safe everywhere.
ensure_local_bins() {
  local d
  for d in /opt/homebrew/bin /usr/local/bin; do
    if [[ -d "$d" ]]; then
      case ":$PATH:" in
        *":$d:"*) ;;            # already present
        *) PATH="$d:$PATH" ;;
      esac
    fi
  done
  export PATH
}

# ── Detect this machine's primary LAN IP (Linux + macOS) ─────────────
detect_lan_ip() {
  local ip=""
  if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"      # Linux
  fi
  if [[ -z "$ip" ]] && command -v ipconfig >/dev/null 2>&1; then
    ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"  # macOS
  fi
  echo "$ip"
}

# ── TCP port check using bash /dev/tcp (no external deps) ────────────
port_open() {  # host port
  (exec 3<>"/dev/tcp/$1/$2") 2>/dev/null && { exec 3>&- ; return 0; }
  return 1
}

# ── OS-specific hint for starting infra services ─────────────────────
infra_hint() {  # service: postgres|redis
  if [[ "$(uname -s)" == "Darwin" ]]; then
    case "$1" in
      postgres) echo "brew services start postgresql@18" ;;
      redis)    echo "brew services start redis" ;;
    esac
  else
    case "$1" in
      postgres) echo "sudo systemctl start postgresql" ;;
      redis)    echo "sudo systemctl start redis-server" ;;
    esac
  fi
}
