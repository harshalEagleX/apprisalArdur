#!/usr/bin/env bash
# Full DB reset + ZIP preparation for the load-test scenario.
# Run from repo root or brain/ directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UPLOADS="$REPO_ROOT/uploads"
TMP="$REPO_ROOT/brain/src/fixtures/.sim-batches"

# ── Load .env ────────────────────────────────────────────────────────────────
ENV_FILE="$REPO_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found"; exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

# Convert JDBC URL → libpq URL
PG_URL="${DB_URL/jdbc:postgresql:/postgresql:}"

run_sql() {
  PGPASSWORD="$DB_PASSWORD" psql "$PG_URL" -U "$DB_USERNAME" -v ON_ERROR_STOP=1 "$@"
}

echo ""
echo "══════════════════════════════════════════════════"
echo "  STEP 0  Stop OCR service (clears stale threads)"
echo "══════════════════════════════════════════════════"
pkill -f "python main.py" 2>/dev/null || true
pkill -f "uvicorn.*main" 2>/dev/null || true
sleep 2
echo "  ✓ OCR service stopped"

echo ""
echo "══════════════════════════════════════════════════"
echo "  STEP 1  Full database reset"
echo "══════════════════════════════════════════════════"
run_sql <<'SQL'
-- Audit tables (no downstream FKs; safe to delete first)
DELETE FROM qc_rule_result_aud;
DELETE FROM qc_result_aud;
DELETE FROM batch_file_aud;
DELETE FROM batch_aud;
DELETE FROM client_aud;
DELETE FROM _user_aud;

-- Deepest leaves first (follow FK chains bottom-up)
DELETE FROM processing_metrics;
DELETE FROM qc_rule_result;
DELETE FROM rule_results;
DELETE FROM page_ocr_results;
DELETE FROM extracted_fields;
DELETE FROM documents;
DELETE FROM feedback_events;
DELETE FROM operator_session;
DELETE FROM llm_response_cache;
DELETE FROM training_examples;

-- Mid-level (qc_result references batch_file)
DELETE FROM qc_result;

-- batch_file references batch
DELETE FROM batch_file;

-- batch references client/_user
DELETE FROM batch;

-- Audit log references _user; clear sim-user audit entries first
DELETE FROM audit_log WHERE user_id IN (SELECT id FROM _user WHERE username LIKE 'sim.%');

-- Simulation users and clients only
DELETE FROM _user WHERE username LIKE 'sim.%';
DELETE FROM client WHERE code LIKE 'SIM%';
SQL
echo "  ✓ Database cleaned"

echo ""
echo "══════════════════════════════════════════════════"
echo "  STEP 2  Build simulation ZIP batches"
echo "══════════════════════════════════════════════════"
rm -rf "$TMP" && mkdir -p "$TMP"

make_zip() {
  local name="$1"
  local src="$2"
  local src_path="$UPLOADS/$src"
  if [[ ! -d "$src_path" ]]; then
    echo "  SKIP $name — source not found: $src_path"; return
  fi
  local staging="$TMP/_stage/$name"
  mkdir -p "$staging"
  for sub in appraisal engagement contract; do
    if [[ -d "$src_path/$sub" ]]; then
      mkdir -p "$staging/$sub"
      find "$src_path/$sub" -maxdepth 1 -name "*.pdf" -exec cp {} "$staging/$sub/" \;
    fi
  done
  local zip_path="$TMP/${name}.zip"
  (cd "$TMP/_stage" && zip -r "$zip_path" "$name" -x "__MACOSX/*" -x "*/.DS_Store" -x "*/.gitkeep" > /dev/null)
  echo "  ✓ $zip_path ($(du -sh "$zip_path" | cut -f1))"
}

make_zip "SIMB001" "EQSS/MSL"
make_zip "SIMB002" "EQSS/TestX121"
make_zip "SIMB003" "EQSS/8234X 2"
make_zip "SIMB004" "EQSS/xBatch"
make_zip "SIMB005" "ADD1/MSL"

rm -rf "$TMP/_stage"

echo ""
echo "══════════════════════════════════════════════════"
echo "  STEP 3  Restart OCR service"
echo "══════════════════════════════════════════════════"
OCR_DIR="$REPO_ROOT/ocr-service"
LOG_DIR="$OCR_DIR/logs"
mkdir -p "$LOG_DIR"
(
  source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh
  conda activate apprisal
  cd "$OCR_DIR"
  nohup python main.py >> "$LOG_DIR/app.log" 2>> "$LOG_DIR/error.log" &
  echo $! > /tmp/apprisal_ocr.pid
)
sleep 4

# Wait until /health returns 200
echo "  Waiting for OCR service to be ready..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:5001/health > /dev/null 2>&1; then
    echo "  ✓ OCR service healthy (attempt $i)"
    break
  fi
  if [[ $i -eq 20 ]]; then
    echo "  WARNING: OCR service did not become healthy in time — proceeding anyway"
  fi
  sleep 2
done

echo ""
echo "══════════════════════════════════════════════════"
echo "  STEP 4  Preload Ollama model"
echo "══════════════════════════════════════════════════"
# Trigger Ollama to load the vision model into memory before the first QC batch.
# This prevents the cold-start failure on the first batch of every run.
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "  Warming up llava:7b model (may take 30-60 seconds)..."
  curl -s --max-time 90 -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"llava:7b","prompt":"ready","stream":false,"options":{"num_predict":1}}' \
    > /dev/null 2>&1 && echo "  ✓ Ollama model loaded" || echo "  WARNING: Ollama preload timed out — first batch may be slow"
else
  echo "  Ollama not running on :11434 — skipping preload"
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  Done — ZIPs ready in:"
echo "  $TMP"
echo "══════════════════════════════════════════════════"
ls -lh "$TMP"/*.zip 2>/dev/null || true
