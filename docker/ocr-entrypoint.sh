#!/usr/bin/env bash
# Entrypoint for the ocr-service image.
#  - The web service ensures the Python-owned tables exist (idempotent create) before serving.
#  - The Celery worker skips DB creation (the web service is the single owner of schema setup)
#    by setting RUN_DB_CREATE=0 in compose.
set -euo pipefail

if [[ "${RUN_DB_CREATE:-1}" == "1" ]]; then
  echo "[ocr-entrypoint] ensuring Python-owned tables exist (manage_db.py create)…"
  python manage_db.py create || echo "[ocr-entrypoint] WARN: manage_db create failed; continuing"
fi

echo "[ocr-entrypoint] exec: $*"
exec "$@"
