#!/usr/bin/env bash
# Start the SHAL Next.js frontend dev server on port 3000.
# Always reinstalls npm dependencies and clears the Next.js build cache so a
# git pull on the server is immediately reflected with no stale compiled output.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$FRONTEND_DIR/.env.local" ]] && source "$FRONTEND_DIR/.env.local"
set +a

# ── Always do a fresh install + clear build cache ────────────
cd "$FRONTEND_DIR"
echo "[start-frontend] Installing/refreshing npm dependencies..."
npm install
echo "[start-frontend] Clearing Next.js build cache (.next/)..."
rm -rf .next

# ── Launch ───────────────────────────────────────────────────
# -H 0.0.0.0 binds all interfaces so the app is reachable over the LAN/IP,
# not just localhost. lib/config.ts then auto-targets the backend on the same
# host the browser used, so no per-device URL config is needed.
echo "[start-frontend] Starting Next.js dev server on http://0.0.0.0:3000 (network-accessible)"
exec npm run dev -- -H 0.0.0.0 -p 3000
