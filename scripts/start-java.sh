#!/usr/bin/env bash
# Start the SHAL Java / Spring Boot backend on port 8080.
# Spring Boot imports .env itself (see application.yml: spring.config.import),
# so we only ensure .env exists and launch the jar from the repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAR="$REPO_ROOT/app/target/app-0.0.1-SNAPSHOT.jar"

# ── Ensure .env exists (INTERNAL_API_KEY is required, no default) ─────
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "[start-java] .env missing — generating it..."
  bash "$REPO_ROOT/scripts/init-env.sh"
fi

# ── Build the jar if it isn't there yet ──────────────────────────────
if [[ ! -f "$JAR" ]]; then
  echo "[start-java] JAR not found — building (this can take a few minutes)..."
  (cd "$REPO_ROOT" && ./mvnw -q -DskipTests clean package)
fi

# ── Launch ───────────────────────────────────────────────────────────
# Run from repo root so Spring's 'optional:file:.env' import resolves.
cd "$REPO_ROOT"
echo "[start-java] Starting Spring Boot on http://localhost:8080"
exec java -jar "$JAR"
