#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# clean_run.sh — Clean rebuild + full local run of the SHAL stack.
#
# Order of operations (exactly as intended):
#   1. ALWAYS ask whether to reset & clean the database (drops ALL data).
#   2. Start SHALqc (the Python QC service) — BEFORE Java, so the first order
#      Java processes finds a live QC backend instead of a connection refused.
#   3. Clean-compile the Java backend into a fresh jar and start it.
#   4. Start the frontend — last.
#
#   SHALqc     : http://localhost:5001
#   Java API   : http://localhost:8080
#   Frontend   : http://localhost:3000
#
# SHALqc replaced the retired ocr-service and reuses its port (5001) — that is
# what Java's OCR_SERVICE_URL still points at. It runs out of ./shalqc with the
# conda env `shal` (override with SHALQC_PYTHON=/path/to/python) and reads its
# OWN ./shalqc/.env — the root .env is NOT enough for it.
#
# Java and SHALqc share ONE Postgres database (shal_qc): Java's tables come from
# Hibernate ddl-auto, SHALqc's from SQLAlchemy create_all on first persist. A
# schema drop therefore wipes both, and both recreate themselves on startup/use.
#
# This script never compiles AMC bundles. The compiled bundle under
# shalqc/compiled/ is the source of record (hand-tuned bindings live only there);
# recompiling would destroy it. The preflight only *reports* its sign-off status.
#
# Logs + PIDs live in ./.uat-run/ ; stop everything with:
#   bash scripts/uat/stop-local.sh
#
# Env overrides: JAVA_PORT / SHALQC_PORT / FRONTEND_PORT / SHALQC_PYTHON,
#                SKIP_SHALQC=1 to run the stack without QC.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
SHALQC_DIR="$SCRIPT_DIR/shalqc"
RUN_DIR="$SCRIPT_DIR/.uat-run"
mkdir -p "$RUN_DIR"

# ── Load .env files ───────────────────────────────────────────────────────────
# Parse each KEY=VALUE line directly. NOTE: do NOT use `source <(grep …)` here —
# macOS ships bash 3.2, where process-substitution sourcing silently drops the
# assignments under `set -euo pipefail`. A plain `while read` works everywhere.
load_env() {
    local file="$1" line key val
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue
        [[ "$line" != *=* ]] && continue
        key="${line%%=*}"
        val="${line#*=}"
        key="${key//[[:space:]]/}"
        export "$key=$val"
    done < "$file"
}
load_env "$SCRIPT_DIR/.env"
load_env "$SCRIPT_DIR/.env.uat"

# Read a single KEY from an env file WITHOUT exporting it (used by the preflight
# to compare secrets across the two .env files without leaking them into logs).
env_value() { # file key
    local file="$1" key="$2" line
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [[ "$line" == \#* ]] && continue
        [[ "$line" != "$key"=* ]] && continue
        printf '%s' "${line#*=}"
        return 0
    done < "$file"
}

# ── Service env defaults (local, no Docker; plain http on localhost) ──────────
export SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-uat}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export NEXT_PUBLIC_JAVA_URL="${NEXT_PUBLIC_JAVA_URL:-http://localhost:8080}"
JAVA_PORT="${JAVA_PORT:-8080}"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"
SHALQC_PORT="${SHALQC_PORT:-5001}"
# Java reaches SHALqc through OCR_SERVICE_URL (the config key kept its retired
# ocr-service name; the URL is SHALqc's). Keep the two in lockstep by default.
export OCR_SERVICE_URL="${OCR_SERVICE_URL:-http://127.0.0.1:${SHALQC_PORT}}"
JAR="app/target/app-0.0.1-SNAPSHOT.jar"

# ── Resolve a psql-compatible URL (only needed if the DB reset is chosen) ─────
resolve_psql_url() {
    if [[ -n "${DATABASE_URL:-}" ]]; then
        PSQL_URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
    elif [[ -n "${DB_URL:-}" ]]; then
        local base host_path
        base="${DB_URL#jdbc:}"; host_path="${base#postgresql://}"
        PSQL_URL="postgresql://${DB_USERNAME:-postgres}:${DB_PASSWORD:-}@${host_path}"
    else
        PSQL_URL=""
    fi
}

# ── SHALqc interpreter + preflight ────────────────────────────────────────────
# SHALqc runs under the conda env `shal`. We invoke that env's python DIRECTLY
# rather than `conda activate` — activation needs conda's shell hook, which is
# not loaded in a non-interactive bash script.
resolve_shalqc_python() {
    local cand base
    if [[ -n "${SHALQC_PYTHON:-}" ]]; then SHALQC_PY="$SHALQC_PYTHON"; return 0; fi
    if command -v conda >/dev/null 2>&1; then
        base="$(conda info --base 2>/dev/null || true)"
        if [[ -n "$base" && -x "$base/envs/shal/bin/python" ]]; then
            SHALQC_PY="$base/envs/shal/bin/python"; return 0
        fi
    fi
    for cand in "$HOME/miniconda3/envs/shal/bin/python" \
                "$HOME/anaconda3/envs/shal/bin/python" \
                "/opt/homebrew/Caskroom/miniconda/base/envs/shal/bin/python"; do
        [[ -x "$cand" ]] && { SHALQC_PY="$cand"; return 0; }
    done
    SHALQC_PY="$(command -v python3 || true)"
}

# Everything that makes SHALqc start-but-be-useless is checked here, loudly, so a
# failure shows up now instead of as a wall of 401s or mass-VERIFY cards later.
preflight_shalqc() {
    resolve_shalqc_python
    [[ -n "$SHALQC_PY" && -x "$SHALQC_PY" ]] || {
        echo "ERROR: no python for SHALqc (conda env 'shal' not found)." >&2
        echo "       Create it, or set SHALQC_PYTHON=/path/to/python." >&2
        exit 1; }
    "$SHALQC_PY" -c 'import uvicorn, fastapi' 2>/dev/null || {
        echo "ERROR: $SHALQC_PY cannot import uvicorn/fastapi." >&2
        echo "       Install deps:  $SHALQC_PY -m pip install -r shalqc/requirements.txt" >&2
        exit 1; }
    echo "   • interpreter : $SHALQC_PY"

    [[ -f "$SHALQC_DIR/.env" ]] || {
        echo "ERROR: shalqc/.env is missing — SHALqc reads its own env file, the root" >&2
        echo "       .env is not enough. Copy shalqc/.env.example and fill it in." >&2
        exit 1; }

    # A mismatched key is the single most confusing failure: SHALqc starts fine,
    # is healthy, and 401s every request Java sends.
    local root_key qc_key
    root_key="$(env_value "$SCRIPT_DIR/.env" INTERNAL_API_KEY)"
    qc_key="$(env_value "$SHALQC_DIR/.env" INTERNAL_API_KEY)"
    if [[ -n "$root_key" && -n "$qc_key" && "$root_key" != "$qc_key" ]]; then
        echo "   ⚠ INTERNAL_API_KEY differs between .env and shalqc/.env — Java's QC"
        echo "     calls will 401. Make the two values identical."
    fi

    # The compiled bundle is the source of record. Report its sign-off status:
    # a draft bundle is refused outright in production, and a MISSING one means
    # SHALqc silently falls back to the generic _base catalog → mass VERIFY.
    local bundle
    bundle="$(ls "$SHALQC_DIR"/compiled/EQUITYSOLUTIONS/*.yaml 2>/dev/null | head -n1 || true)"
    if [[ -z "$bundle" ]]; then
        echo "   ⚠ no compiled EQUITYSOLUTIONS bundle — QC will fall back to _base (mass VERIFY)."
    elif grep -qE '^\s*status:\s*active' "$bundle"; then
        echo "   • bundle      : $(basename "$bundle") (active)"
    else
        echo "   ⚠ bundle $(basename "$bundle") is NOT status=active (draft) — dev runs it with a"
        echo "     degradation warning; a strict/production deploy would refuse to run it."
    fi
}

# ── Background/wait helpers (shared with scripts/uat/run-local.sh) ────────────
start_bg() { # name command…
    local name="$1"; shift
    echo "==> Starting $name"
    ( nohup "$@" >"$RUN_DIR/$name.log" 2>&1 </dev/null & echo $! >"$RUN_DIR/$name.pid" )
}
wait_http() { # name url
    # NOTE (macOS bash 3.2): a single `local a=$1 b=$a` does NOT see `a` when
    # expanding `b`, so `pidfile`/`pid` are assigned on their own lines below.
    local name="$1" url="$2" tries=90 pid pidfile
    pidfile="$RUN_DIR/$name.pid"
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    printf "==> Waiting for %s (%s) " "$name" "$url"
    until curl -fsS -o /dev/null "$url" 2>/dev/null; do
        # Fail fast if the process we started has already died (e.g. port still held
        # by a stale server) — otherwise we'd falsely "succeed" against that old server.
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
            echo " FAILED (process $pid exited — see log)"
            echo "--- last 40 log lines ---"; tail -n 40 "$RUN_DIR/$name.log" 2>/dev/null
            exit 1
        fi
        ((tries--)) || { echo " FAILED"; echo "--- last 30 log lines ---"; tail -n 30 "$RUN_DIR/$name.log" 2>/dev/null; exit 1; }
        printf "."; sleep 2
    done; echo " OK"
}

# Free a TCP port: kill whatever is LISTENing on it (graceful, then SIGKILL), and
# wait until it is actually released so the fresh process can bind it.
free_port() { # port
    local port="$1" pids waited=0
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -z "$pids" ]] && return 0
    echo "   • freeing port $port (was held by: $(echo "$pids" | tr '\n' ' '))"
    kill $pids 2>/dev/null || true
    while lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; do
        ((waited++))
        if (( waited >= 10 )); then
            echo "   • force-killing port $port"
            kill -9 $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true
            break
        fi
        sleep 1
    done
}

# Stop any previously-running SHAL services BEFORE we reset the DB or start fresh.
# Without this, an old server keeps holding its port, the new process can't bind,
# and the health check passes against the STALE server (which is now pointed at a
# freshly-wiped DB → login 500s). Stops by pid-file AND by port (a stale process
# from a prior run is not in the current pid-file).
stop_existing() {
    echo "==> Stopping any existing SHAL services…"
    local name pid
    for name in frontend java shalqc; do
        pid="$(cat "$RUN_DIR/$name.pid" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "   • stopping $name (pid $pid)"
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$RUN_DIR/$name.pid"
    done
    for port in "$FRONTEND_PORT" "$JAVA_PORT" "$SHALQC_PORT"; do
        free_port "$port"
    done
    # A uvicorn --reload parent respawns its worker, and the worker is not the pid
    # we recorded; clear any straggler still bound to the SHALqc app.
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
}

# ═════════════════════════════════════════════════════════════════════════════
# Step 1/4 — ALWAYS ask whether to reset & clean the database
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           SHAL — clean rebuild & run                  ║"
echo "╚══════════════════════════════════════════════════════╝"

# Stop any old run FIRST — otherwise a stale server keeps its port and the fresh
# build never actually takes over (the cause of "up" but login 500s on a wiped DB).
stop_existing

read -r -p "Reset and CLEAN the database (drops ALL data)? [y/N]: " RESET_ANS || RESET_ANS=""
if [[ "${RESET_ANS:-}" =~ ^([Yy]|[Yy][Ee][Ss])$ ]]; then
    resolve_psql_url
    if [[ -z "$PSQL_URL" ]]; then
        echo "ERROR: no DATABASE_URL or DB_URL found in .env files — cannot reset the DB." >&2
        exit 1
    fi
    echo ""
    echo "Step 1/4 — Resetting database (DROP SCHEMA CASCADE)…"
    psql "$PSQL_URL" <<-'SQL'
        DROP SCHEMA IF EXISTS public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO PUBLIC;
	SQL
    echo "  ✓ Schema cleared. Java tables recreate on app startup (Hibernate ddl-auto);"
    echo "    SHALqc's tables recreate on its first persist (SQLAlchemy create_all)."
else
    echo "Step 1/4 — Skipping DB reset (existing data kept; Hibernate will update Java tables)."
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 2/4 — Start SHALqc (the Python QC service) BEFORE Java
# ═════════════════════════════════════════════════════════════════════════════
echo ""
if [[ "${SKIP_SHALQC:-}" == "1" ]]; then
    echo "Step 2/4 — Skipping SHALqc (SKIP_SHALQC=1). QC calls from Java WILL fail."
else
    echo "Step 2/4 — Starting SHALqc on :${SHALQC_PORT}…"
    preflight_shalqc
    # Run from the shalqc folder: app.config loads ./shalqc/.env relative to the
    # package, and the compiled bundles/config are resolved from there too.
    ( cd "$SHALQC_DIR"
      start_bg shalqc "$SHALQC_PY" -m uvicorn app.main:app \
          --host 0.0.0.0 --port "$SHALQC_PORT" )
    # /health is one of the few unauthenticated paths, so this probe needs no key.
    wait_http shalqc "http://127.0.0.1:${SHALQC_PORT}/health"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 3/4 — Clean-compile the Java backend into a fresh jar, then start it
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "Step 3/4 — Clean-building Java jar (mvnw clean package -DskipTests)…"
./mvnw -q -B -pl app -am clean package -DskipTests
[[ -f "$JAR" ]] || { echo "ERROR: expected jar not found at $JAR after build." >&2; exit 1; }
start_bg java java -jar "$JAR"
wait_http java "http://127.0.0.1:${JAVA_PORT}/actuator/health"

# ═════════════════════════════════════════════════════════════════════════════
# Step 4/4 — Start the frontend (LAST)
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "Step 4/4 — Building & starting the frontend (last)…"
( cd "$FRONTEND_DIR"
  [[ -d node_modules ]] || npm ci
  NEXT_PUBLIC_JAVA_URL="$NEXT_PUBLIC_JAVA_URL" npm run build
  start_bg frontend npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" )
wait_http frontend "http://127.0.0.1:${FRONTEND_PORT}"

cat <<EOF

✅ SHAL is up (clean run complete).
   Frontend   : http://localhost:${FRONTEND_PORT}
   Java API   : http://localhost:${JAVA_PORT}
   SHALqc     : http://localhost:${SHALQC_PORT}  (health: /health, docs: /docs, metrics: /metrics)

   Logs : $RUN_DIR/{java,shalqc,frontend}.log
   Stop : bash scripts/uat/stop-local.sh
EOF
