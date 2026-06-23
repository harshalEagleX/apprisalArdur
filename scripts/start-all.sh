#!/usr/bin/env bash
# Start all SHAL platform services in separate Terminal tabs (macOS).
# Usage: ./scripts/start-all.sh
#
# Services started:
#   1. Java Spring Boot  — http://localhost:8080
#   2. Python OCR (FastAPI) — http://localhost:5001
#   3. Celery worker     — redis://localhost:6379/0
#   4. Next.js frontend  — http://localhost:3000
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$REPO_ROOT/scripts"

# ── Infrastructure checks ────────────────────────────────────
echo "[start-all] Checking infrastructure..."

pg_isready -q 2>/dev/null || { echo "[start-all] ERROR: PostgreSQL is not running. Start it with: brew services start postgresql@18"; exit 1; }
redis-cli ping -q 2>/dev/null | grep -q PONG || { echo "[start-all] ERROR: Redis is not running. Start it with: brew services start redis"; exit 1; }

echo "[start-all] PostgreSQL: OK"
echo "[start-all] Redis:      OK"

# ── Helper: open a new Terminal tab and run a script ────────
open_tab() {
  local label="$1"
  local script="$2"
  echo "[start-all] Launching $label..."
  osascript <<EOF
tell application "Terminal"
  activate
  tell application "System Events" to keystroke "t" using command down
  delay 0.3
  do script "echo '=== SHAL: $label ==='; bash '$script'" in front window
end tell
EOF
}

# ── Launch each service in its own tab ──────────────────────
open_tab "Java Backend  (port 8080)" "$SCRIPTS/start-java.sh"
sleep 1
open_tab "OCR Service   (port 5001)" "$SCRIPTS/start-ocr.sh"
sleep 1
open_tab "Celery Worker (Redis)"     "$SCRIPTS/start-celery.sh"
sleep 1
open_tab "Next.js Frontend (port 3000)" "$SCRIPTS/start-frontend.sh"

echo ""
echo "[start-all] All services launched."
echo ""
echo "  Java backend  → http://localhost:8080"
echo "  OCR service   → http://localhost:5001/health"
echo "  Frontend      → http://localhost:3000"
echo ""
echo "  Login: harshal@eaglexinfo.com / Admin123!"
