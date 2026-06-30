#!/usr/bin/env bash
# =============================================================================
# SHAL Platform — Load & Performance Test Runner
# =============================================================================
#
# Usage:
#   ./scripts/run-load-tests.sh [OPTIONS]
#
# OPTIONS:
#   --java-only          Run only Gatling Java API tests
#   --python-only        Run only Locust Python OCR service tests
#   --smoke              Small-scale smoke run (50 users, 60 s)
#   --full               Full scale: 5,000 users, 10 min hold (default)
#   --volume             Document volume test: 10,000 docs
#   --reviewer           Reviewer workflow deep test
#   --base-url URL       Spring Boot base URL (default: http://localhost:8080)
#   --python-url URL     OCR service URL  (default: http://localhost:8000)
#   --admin-user U       Admin username   (default: admin)
#   --admin-pass P       Admin password   (default: admin123)
#   -h | --help          Show this help
#
# Examples:
#   # Smoke test everything (fastest, ~2 min)
#   ./scripts/run-load-tests.sh --smoke
#
#   # Full 5,000-user + 10,000-doc test
#   ./scripts/run-load-tests.sh --full --volume
#
#   # Java only against a staging server
#   ./scripts/run-load-tests.sh --java-only --base-url http://staging:8080
#
#   # Python only, 200 concurrent users for 5 minutes
#   ./scripts/run-load-tests.sh --python-only --full
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

# ── Defaults ──────────────────────────────────────────────────────────────────
RUN_JAVA=true
RUN_PYTHON=true
RUN_VOLUME=false
RUN_REVIEWER=false
BASE_URL="http://localhost:8080"
PYTHON_URL="http://localhost:5001"
ADMIN_USER="admin"
ADMIN_PASS="admin123"

# Scale: smoke vs full
USERS=5000
RAMP_SECS=60
HOLD_SECS=300
DOC_VOLUME=10000
PYTHON_USERS=200
PYTHON_SPAWN=10
PYTHON_RUNTIME=300

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --java-only)    RUN_PYTHON=false; shift ;;
    --python-only)  RUN_JAVA=false;   shift ;;
    --smoke)
      USERS=50; RAMP_SECS=10; HOLD_SECS=60; DOC_VOLUME=500
      PYTHON_USERS=20; PYTHON_SPAWN=4; PYTHON_RUNTIME=60
      shift ;;
    --full)
      USERS=5000; RAMP_SECS=60; HOLD_SECS=300; DOC_VOLUME=10000
      PYTHON_USERS=200; PYTHON_SPAWN=10; PYTHON_RUNTIME=300
      shift ;;
    --volume)       RUN_VOLUME=true; shift ;;
    --reviewer)     RUN_REVIEWER=true; shift ;;
    --base-url)     BASE_URL="$2"; shift 2 ;;
    --python-url)   PYTHON_URL="$2"; shift 2 ;;
    --admin-user)   ADMIN_USER="$2"; shift 2 ;;
    --admin-pass)   ADMIN_PASS="$2"; shift 2 ;;
    -h|--help)
      head -40 "$0" | tail -30
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()    { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; }
section() { echo -e "\n${GREEN}══════════════════════════════════════════${RESET}"; \
             echo -e "${GREEN}  $*${RESET}"; \
             echo -e "${GREEN}══════════════════════════════════════════${RESET}"; }

# ── Preflight checks ──────────────────────────────────────────────────────────
section "SHAL Load Test Runner"
info "Base URL  : $BASE_URL"
info "Python URL: $PYTHON_URL"
info "Scale     : $USERS users, ramp=${RAMP_SECS}s, hold=${HOLD_SECS}s"
info "Doc volume: $DOC_VOLUME"

check_server() {
  local url="$1"; local name="$2"
  if curl -sf --connect-timeout 5 "$url" > /dev/null 2>&1 || \
     curl -sf --connect-timeout 5 "$url/health" > /dev/null 2>&1 || \
     curl -sf --connect-timeout 5 "$url/api/qc/health" > /dev/null 2>&1; then
    info "$name is reachable at $url"
  else
    warn "$name at $url did not respond — tests will continue but may see high error rates"
  fi
}

$RUN_JAVA   && check_server "$BASE_URL"   "Spring Boot"
$RUN_PYTHON && check_server "$PYTHON_URL" "Python OCR service"

# ── Common Gatling properties ─────────────────────────────────────────────────
GATLING_PROPS=(
  "-Dloadtest.baseUrl=$BASE_URL"
  "-Dloadtest.adminUser=$ADMIN_USER"
  "-Dloadtest.adminPass=$ADMIN_PASS"
  "-Dloadtest.users=$USERS"
  "-Dloadtest.rampSeconds=$RAMP_SECS"
  "-Dloadtest.holdSeconds=$HOLD_SECS"
  "-Dloadtest.docVolume=$DOC_VOLUME"
)

RESULTS_DIR="loadtest/target/gatling"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="loadtest/reports/${TIMESTAMP}"
mkdir -p "$REPORT_DIR"

EXIT_CODE=0

# ── 1. Java API load tests (Gatling) ─────────────────────────────────────────
if $RUN_JAVA; then
  section "Phase 1 — Gatling: Full Platform (5,000 users)"
  info "Simulation: FullPlatformSimulation"
  info "Covers: Auth, Dashboard, Batch CRUD, QC status, Reviewer queue,"
  info "        Analytics (7 endpoints), Transactions, Audit graph, Overrides"

  ./mvnw gatling:test -pl loadtest \
    "${GATLING_PROPS[@]}" \
    -Dgatling.simulationClass=com.shal.load.simulations.FullPlatformSimulation \
    --no-transfer-progress \
    2>&1 | tee "$REPORT_DIR/full-platform.log" || {
      error "FullPlatformSimulation failed or SLAs breached"
      EXIT_CODE=1
    }

  if $RUN_REVIEWER; then
    section "Phase 1b — Gatling: Reviewer Workflow Deep Test"
    info "Simulation: ReviewerWorkflowSimulation"
    info "Covers: Session start/heartbeat, decision saves, sign-off,"
    info "        corrections proxy, re-review requests"

    ./mvnw gatling:test -pl loadtest \
      "${GATLING_PROPS[@]}" \
      -Dloadtest.users=$((USERS / 25)) \
      -Dloadtest.holdSeconds=$((HOLD_SECS / 2)) \
      -Dgatling.simulationClass=com.shal.load.simulations.ReviewerWorkflowSimulation \
      --no-transfer-progress \
      2>&1 | tee "$REPORT_DIR/reviewer-workflow.log" || {
        error "ReviewerWorkflowSimulation failed or SLAs breached"
        EXIT_CODE=1
      }
  fi

  if $RUN_VOLUME; then
    section "Phase 1c — Gatling: Document Volume (${DOC_VOLUME} docs)"
    info "Simulation: DocumentVolumeSimulation"
    info "Phase A: ${USERS} concurrent uploads → ${DOC_VOLUME} documents seeded"
    info "Phase B: 500 concurrent readers hit all seeded records"
    info "Phase C: Deep paginated scan verifies index efficiency"

    ./mvnw gatling:test -pl loadtest \
      "${GATLING_PROPS[@]}" \
      -Dgatling.simulationClass=com.shal.load.simulations.DocumentVolumeSimulation \
      --no-transfer-progress \
      2>&1 | tee "$REPORT_DIR/document-volume.log" || {
        error "DocumentVolumeSimulation failed or SLAs breached"
        EXIT_CODE=1
      }
  fi

  # Copy Gatling HTML reports
  if ls "$RESULTS_DIR"/*/index.html 2>/dev/null | head -1 > /dev/null; then
    cp -r "$RESULTS_DIR"/*/  "$REPORT_DIR/gatling-html/" 2>/dev/null || true
    info "Gatling HTML reports → $REPORT_DIR/gatling-html/"
  fi
fi

# ── 2. Python OCR service load tests (Locust) ─────────────────────────────────
if $RUN_PYTHON; then
  section "Phase 2 — Locust: Python OCR Service ($PYTHON_USERS users)"
  info "Covers: /health, /qc/process (sync), /qc/process-async + status polling,"
  info "        /corrections (write stream), /correction-stats"

  if ! command -v conda &> /dev/null; then
    warn "conda not found — trying system locust"
    LOCUST_CMD="locust"
  else
    LOCUST_CMD="conda run -n shal locust"
  fi

  $LOCUST_CMD \
    -f ocr-service/tests/locustfile.py \
    --headless \
    --host "$PYTHON_URL" \
    -u "$PYTHON_USERS" \
    -r "$PYTHON_SPAWN" \
    -t "${PYTHON_RUNTIME}s" \
    --html "$REPORT_DIR/locust-report.html" \
    --csv "$REPORT_DIR/locust" \
    2>&1 | tee "$REPORT_DIR/locust.log" || {
      warn "Locust reported failures — check $REPORT_DIR/locust.log"
      EXIT_CODE=1
    }

  info "Locust HTML report → $REPORT_DIR/locust-report.html"
  info "Locust CSV stats   → $REPORT_DIR/locust_stats.csv"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
section "Test Run Complete"
info "All reports saved to: $REPORT_DIR"

if $RUN_JAVA; then
  echo ""
  echo "  Gatling logs:"
  ls "$REPORT_DIR"/*.log 2>/dev/null | sed 's/^/    /'
fi

if $RUN_PYTHON; then
  echo ""
  echo "  Locust reports:"
  ls "$REPORT_DIR"/locust* "$REPORT_DIR"/*locust* 2>/dev/null | sed 's/^/    /' || true
fi

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo -e "${GREEN}  ✓ All SLA assertions passed${RESET}"
else
  echo -e "${RED}  ✗ One or more SLA assertions failed — review reports above${RESET}"
fi

exit $EXIT_CODE
