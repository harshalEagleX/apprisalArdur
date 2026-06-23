#!/usr/bin/env bash
# Start the SHAL Java / Spring Boot backend on port 8080.
# Always performs a clean Maven build so a git pull on the server is always
# reflected — never runs a stale JAR from a previous checkout.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAR="$REPO_ROOT/app/target/app-0.0.1-SNAPSHOT.jar"

# ── Ensure .env exists (INTERNAL_API_KEY is required, no default) ─────
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "[start-java] .env missing — generating it..."
  bash "$REPO_ROOT/scripts/init-env.sh"
fi

# ── Always do a clean build — picks up every git pull change ──────────
echo "[start-java] Building JAR (clean, skipping tests)..."
(cd "$REPO_ROOT" && ./mvnw -q -DskipTests clean package)
echo "[start-java] Build complete: $JAR"

# ── Launch ───────────────────────────────────────────────────────────
# Run from repo root so Spring's 'optional:file:.env' import resolves.
cd "$REPO_ROOT"
echo "[start-java] Starting Spring Boot on http://0.0.0.0:8080"
exec java -jar "$JAR"
