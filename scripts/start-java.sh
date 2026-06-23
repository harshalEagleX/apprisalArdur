#!/usr/bin/env bash
# Start the SHAL Java / Spring Boot backend on port 8080.
# Loads .env and passes all vars as JVM -D flags.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAR="$REPO_ROOT/app/target/app-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$JAR" ]]; then
  echo "[start-java] JAR not found — building first..."
  cd "$REPO_ROOT"
  ./mvnw -q -DskipTests clean package
fi

# ── Env vars ─────────────────────────────────────────────────
set -a
[[ -f "$REPO_ROOT/.env" ]] && source "$REPO_ROOT/.env"
set +a

# ── Launch ───────────────────────────────────────────────────
echo "[start-java] Starting Spring Boot on http://localhost:8080"
exec java \
  -Dspring.datasource.url="${DB_URL}" \
  -Dspring.datasource.username="${DB_USERNAME}" \
  -Dspring.datasource.password="${DB_PASSWORD}" \
  -Djwt.secret="${JWT_SECRET}" \
  -Dadmin.email="${ADMIN_EMAIL}" \
  -Dadmin.password="${ADMIN_PASSWORD}" \
  -Docr.service.url="${OCR_SERVICE_URL}" \
  -Docr.service.api-key="${INTERNAL_API_KEY}" \
  -Dredis.url="${REDIS_URL:-redis://localhost:6379/0}" \
  -jar "$JAR"
