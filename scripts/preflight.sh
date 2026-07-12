#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# preflight.sh — validate a SHAL deployment BEFORE starting any service.
#
# Run this on ANY target (laptop, bare server, cloud VM, container, or a hybrid
# where some services are local and some remote). It answers one question:
# "will the stack come up cleanly here, or is something misconfigured/unreachable?"
#
# It never starts anything and never mutates state — it only reads config + probes
# connectivity, then prints a PASS / WARN / FAIL report.
#
# Usage:
#   bash scripts/preflight.sh            # dev: insecure defaults are WARN
#   bash scripts/preflight.sh --strict   # prod: insecure defaults / missing reqs FAIL
#
# Exit code: 0 = safe to start, 1 = a hard problem (always fails), or in --strict
#            mode, any WARN is also promoted to a failure.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

STRICT=0
[[ "${1:-}" == "--strict" || "${STRICT:-0}" == "1" ]] && STRICT=1

PASS=0; WARN=0; FAIL=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=$((WARN+1)); }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
head() { printf "\n\033[1m%s\033[0m\n" "$1"; }

# ── Load .env files (same parser as clean_run.sh; bash-3.2 safe) ──────────────
load_env() {
    local file="$1" line key val
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
        key="${line%%=*}"; val="${line#*=}"; key="${key//[[:space:]]/}"
        # Only set if not already in the real environment (real env wins).
        [[ -z "${!key:-}" ]] && export "$key=$val"
    done < "$file"
}
load_env "$SCRIPT_DIR/.env"
load_env "$SCRIPT_DIR/.env.uat"

DEFAULT_JWT="404E635266556A586E3272357538782F413F4428472B4B6250645367566B5970"
DEFAULT_DB_PW="12345678"
DEFAULT_ADMIN_PW="Admin123!"

printf "\033[1mSHAL preflight\033[0m  (mode: %s)\n" "$([[ $STRICT == 1 ]] && echo strict/production || echo dev)"

# ── 1. Tooling ────────────────────────────────────────────────────────────────
head "1. Tooling"
for tool in java node npm curl psql; do
    if command -v "$tool" >/dev/null 2>&1; then ok "$tool found"; else
        [[ "$tool" == "psql" ]] && warn "$tool not found (DB probe will be skipped)" \
                                 || fail "$tool not found (required)"
    fi
done

# ── 2. Required configuration ─────────────────────────────────────────────────
head "2. Required configuration"
require() { # VAR  human-hint
    local v="$1"
    if [[ -n "${!v:-}" ]]; then ok "$v is set"; else fail "$v is not set — $2"; fi
}
require INTERNAL_API_KEY "shared Java↔Python secret (X-API-Key)"
# DB may be provided as DB_URL (Java) or DATABASE_URL (Python) — need at least one.
if [[ -n "${DB_URL:-}" || -n "${DATABASE_URL:-}" ]]; then ok "database URL is set (DB_URL/DATABASE_URL)"
else fail "no DB_URL / DATABASE_URL — the database is required"; fi

# ── 3. Secret hygiene (WARN in dev, FAIL in --strict) ─────────────────────────
head "3. Secret hygiene"
check_secret() { # value  default  name
    if [[ "$1" == "$2" ]]; then
        [[ $STRICT == 1 ]] && fail "$3 is the shipped default — set a real value for production" \
                           || warn "$3 is the shipped default (fine for local; MUST change for prod)"
    else ok "$3 is customised"; fi
}
check_secret "${JWT_SECRET:-}"     "$DEFAULT_JWT"      "JWT_SECRET"
check_secret "${DB_PASSWORD:-}"    "$DEFAULT_DB_PW"    "DB_PASSWORD"
check_secret "${ADMIN_PASSWORD:-}" "$DEFAULT_ADMIN_PW" "ADMIN_PASSWORD"
if [[ "${COOKIE_SECURE:-false}" == "true" ]]; then ok "COOKIE_SECURE=true"
else [[ $STRICT == 1 ]] && fail "COOKIE_SECURE=false — must be true behind HTTPS in production" \
                        || warn "COOKIE_SECURE=false (ok for local http; set true behind HTTPS)"; fi

# ── 4. Connectivity (probes; a down optional service is a WARN, not a stop) ────
head "4. Connectivity"
# 4a. Database (required) — resolve a psql URL from DATABASE_URL or DB_URL.
PSQL_URL=""
if [[ -n "${DATABASE_URL:-}" ]]; then PSQL_URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
elif [[ -n "${DB_URL:-}" ]]; then
    _b="${DB_URL#jdbc:}"; PSQL_URL="postgresql://${DB_USERNAME:-postgres}:${DB_PASSWORD:-}@${_b#postgresql://}"
fi
if [[ -n "$PSQL_URL" ]] && command -v psql >/dev/null 2>&1; then
    if psql "$PSQL_URL" -tAc "SELECT 1" >/dev/null 2>&1; then ok "database reachable"
    else fail "database NOT reachable at the configured URL — start/verify Postgres before running"; fi
else warn "database probe skipped (no psql or no URL) — verify DB manually"; fi

# 4b. Redis (optional — Java + Python fall back to local/sync if absent).
if [[ -n "${REDIS_URL:-}" ]]; then
    if command -v redis-cli >/dev/null 2>&1 && redis-cli -u "$REDIS_URL" ping 2>/dev/null | grep -qi pong; then
        ok "Redis reachable"
    else warn "Redis not reachable (${REDIS_URL}) — Celery/token-bucket features degrade to local fallback"; fi
else warn "REDIS_URL not set — running without Redis (sync fallback; fine for single-node)"; fi

# ── Summary ───────────────────────────────────────────────────────────────────
head "Summary"
printf "  %d passed, %d warnings, %d failures\n" "$PASS" "$WARN" "$FAIL"
if (( FAIL > 0 )); then
    printf "\033[31mPREFLIGHT FAILED — fix the ✗ items before starting.\033[0m\n"; exit 1
fi
if (( STRICT == 1 && WARN > 0 )); then
    printf "\033[31mPREFLIGHT FAILED (strict) — resolve warnings for production.\033[0m\n"; exit 1
fi
printf "\033[32mPREFLIGHT OK — safe to start.\033[0m\n"; exit 0
