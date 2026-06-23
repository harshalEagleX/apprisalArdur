#!/usr/bin/env bash
# Start the SHAL Next.js frontend dev server on port 3000.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[start-frontend] node_modules missing — running npm install..."
  cd "$FRONTEND_DIR"
  npm install
fi

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$FRONTEND_DIR/.env.local" ]] && source "$FRONTEND_DIR/.env.local"
set +a

# ── Launch ───────────────────────────────────────────────────
cd "$FRONTEND_DIR"
echo "[start-frontend] Starting Next.js dev server on http://localhost:3000"
exec npm run dev
