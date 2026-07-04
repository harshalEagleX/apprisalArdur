#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# clean_run.sh — Clean rebuild + full local run of the SHAL stack.
#
# Order of operations (exactly as intended):
#   1. ALWAYS ask whether to reset & clean the database (drops ALL data).
#   2. Clean-compile the Java backend into a fresh jar and start it.
#   3. Start the Python OCR/QC service (fresh process).
#   4. Start the frontend — last.
#
#   Java API   : http://localhost:8080
#   OCR/QC API : http://localhost:5001
#   Frontend   : http://localhost:3000
#
# Logs + PIDs live in ./.uat-run/ ; stop everything with:
#   bash scripts/uat/stop-local.sh
#
# Env overrides: PYTHON_CMD="…" or CONDA_ENV=<name> (default: shal),
#                JAVA_PORT / OCR_PORT / FRONTEND_PORT.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
OCR_DIR="$SCRIPT_DIR/ocr-service"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
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
load_env "$OCR_DIR/.env"
load_env "$SCRIPT_DIR/.env"
load_env "$SCRIPT_DIR/.env.uat"

# ── Service env defaults (local, no Docker; plain http on localhost) ──────────
export SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-uat}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export OCR_SERVICE_URL="${OCR_SERVICE_URL:-http://127.0.0.1:5001}"
export NEXT_PUBLIC_JAVA_URL="${NEXT_PUBLIC_JAVA_URL:-http://localhost:8080}"
JAVA_PORT="${JAVA_PORT:-8080}"; OCR_PORT="${OCR_PORT:-5001}"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"
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

# ── Resolve the Python for the ocr-service (must run inside the conda env) ─────
# The OCR/QC service runs in a conda env (default: shal). When this script is run
# non-interactively (`bash clean_run.sh`), `conda` is usually NOT on PATH — conda
# only initialises itself in interactive shells — so we locate the env's own
# python binary and use it directly. That binary runs *inside* the env (its
# site-packages resolve there) without needing `conda activate` / `conda run`.
# Override with PYTHON_CMD="…" (full command) or CONDA_ENV=<name>.
CONDA_ENV="${CONDA_ENV:-shal}"
if [[ -n "${PYTHON_CMD:-}" ]]; then
    PY="$PYTHON_CMD"
else
    # Find the conda base: an on-PATH conda, else $CONDA_EXE, else common installs.
    CONDA_BASE=""
    if command -v conda >/dev/null 2>&1; then
        CONDA_BASE="$(conda info --base 2>/dev/null || true)"
    elif [[ -n "${CONDA_EXE:-}" && -x "${CONDA_EXE:-}" ]]; then
        CONDA_BASE="$(cd "$(dirname "$CONDA_EXE")/.." && pwd)"
    else
        for b in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" \
                 "/opt/homebrew/Caskroom/miniconda/base" "/opt/miniconda3" "/opt/anaconda3"; do
            [[ -x "$b/envs/$CONDA_ENV/bin/python" || -x "$b/bin/conda" ]] && { CONDA_BASE="$b"; break; }
        done
    fi

    ENV_PY="${CONDA_BASE:+$CONDA_BASE/envs/$CONDA_ENV/bin/python}"
    if [[ -n "$ENV_PY" && -x "$ENV_PY" ]]; then
        PY="$ENV_PY"
    else
        echo "ERROR: could not find the '$CONDA_ENV' conda env's python." >&2
        echo "       Looked under conda base: ${CONDA_BASE:-<not found>}" >&2
        echo "       Fix with: CONDA_ENV=<name> bash clean_run.sh" >&2
        echo "             or: PYTHON_CMD='/full/path/to/envs/$CONDA_ENV/bin/python' bash clean_run.sh" >&2
        exit 1
    fi
fi
if ! $PY -c "import sqlalchemy, uvicorn" >/dev/null 2>&1; then
    echo "ERROR: '$PY' is missing ocr-service deps (sqlalchemy / uvicorn)." >&2
    echo "       Install them into the '$CONDA_ENV' env, or point PYTHON_CMD at the right python." >&2
    exit 1
fi
echo "==> Python interpreter: $PY"

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
    for name in frontend ocr java; do
        pid="$(cat "$RUN_DIR/$name.pid" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "   • stopping $name (pid $pid)"
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$RUN_DIR/$name.pid"
    done
    for port in "$FRONTEND_PORT" "$OCR_PORT" "$JAVA_PORT"; do
        free_port "$port"
    done
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
    echo "  ✓ Schema cleared."
    echo "  → Recreating Python-owned tables (interpreter: $PY)…"
    ( cd "$OCR_DIR" && printf 'yes\n' | $PY manage_db.py recreate && $PY manage_db.py seed-schema )
    echo "  ✓ Python tables recreated. Java tables recreate on app startup."
else
    echo "Step 1/4 — Skipping DB reset (existing data kept; Hibernate will update Java tables)."
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 2/4 — Clean-compile the Java backend into a fresh jar, then start it
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "Step 2/4 — Clean-building Java jar (mvnw clean package -DskipTests)…"
./mvnw -q -B -pl app -am clean package -DskipTests
[[ -f "$JAR" ]] || { echo "ERROR: expected jar not found at $JAR after build." >&2; exit 1; }
start_bg java java -jar "$JAR"
wait_http java "http://127.0.0.1:${JAVA_PORT}/actuator/health"

# ═════════════════════════════════════════════════════════════════════════════
# Step 3/4 — Start the Python OCR/QC service
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "Step 3/4 — Starting Python OCR/QC service…"
( cd "$OCR_DIR" && start_bg ocr $PY -m uvicorn main:app --host 0.0.0.0 --port "$OCR_PORT" )
wait_http ocr "http://127.0.0.1:${OCR_PORT}/live"

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
   OCR/QC API : http://localhost:${OCR_PORT}

   Logs : $RUN_DIR/{java,ocr,frontend}.log
   Stop : bash scripts/uat/stop-local.sh
EOF
