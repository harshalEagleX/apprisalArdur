# SHAL UAT — Deployment & Rollback Runbook

Stack defined in [`docker-compose.uat.yml`](../docker-compose.uat.yml). Scripts in `scripts/uat/`.

## Bring up / tear down
```bash
cp .env.uat.example .env.uat          # then fill in CHANGE-ME secrets
bash scripts/uat/up.sh                 # build + start + health-gate
bash scripts/uat/down.sh               # stop, keep data
bash scripts/uat/down.sh --wipe        # stop + delete volumes (full clean)
bash scripts/uat/reset-data.sh --yes   # wipe data, keep containers/images
```

Services & ports: frontend `:3000`, java `:8080`, ocr `:5001`, prometheus `:9090`,
grafana `:3001`. Actuator/metrics are on the **internal** management port `9091`
(not published to the host — only Prometheus reaches it over the compose network).

## Release model
- Each release is the set of images built from a tagged git commit. **Tag before deploying:**
  ```bash
  git tag uat-$(date +%Y%m%d-%H%M) && git push --tags
  ```
- Images are built locally by `up.sh`. For a reproducible rollback, tag the built images too:
  ```bash
  docker tag shal-uat-java-backend shal-uat-java-backend:<gitsha>
  docker tag shal-uat-frontend     shal-uat-frontend:<gitsha>
  docker tag shal-uat-ocr-service  shal-uat-ocr-service:<gitsha>
  ```
  (Or push them to a registry so the previous release is always recoverable.)

## Rollback (fast path)
1. `git checkout <previous-uat-tag>`
2. `bash scripts/uat/down.sh`  (volumes are kept — data survives)
3. `bash scripts/uat/up.sh`    (rebuilds the previous code; `--build` forces a clean rebuild)

If you tagged images, rollback is even faster — repoint the compose `image:`/build to the
prior tag and `up -d` without rebuilding.

## Database & rollback safety — READ THIS
The DB has **no migration runner** (project policy: no Flyway/Liquibase/Alembic).
- **Java tables**: managed by Hibernate `ddl-auto`. With `update` (UAT default) schema changes
  are **additive** — a new column is added on deploy but **not dropped on rollback**. An older
  jar runs fine against a newer (superset) schema. This makes most rollbacks safe.
- **One-way hazards to watch** (a rollback will NOT undo these automatically):
  - A column/table **renamed or dropped** in code (Hibernate won't drop with `update`, but if a
    manual DDL drop was run, the old jar may expect the gone column).
  - A column **retyped** (e.g. varchar→bytea) — old and new jars disagree.
  - Any **manual SQL** applied out-of-band.
  Before any release that does the above, snapshot the DB first (below) so rollback can restore it.
- **Python tables**: recreated by `manage_db.py create` (idempotent, additive). A destructive
  reset is `reset-data.sh` / `manage_db.py recreate` — never run that to "roll back" unless you
  intend to lose data.

## Snapshot / restore (use before risky releases)
```bash
# snapshot
docker compose -f docker-compose.uat.yml --env-file .env.uat exec -T postgres \
  pg_dump -U "$DB_USERNAME" -d "$DB_NAME" > uat-snapshot-$(date +%F-%H%M).sql
# restore
docker compose -f docker-compose.uat.yml --env-file .env.uat exec -T postgres \
  psql -U "$DB_USERNAME" -d "$DB_NAME" < uat-snapshot-<stamp>.sql
```

## Switching `ddl-auto=validate` (schema-drift gate)
Once the UAT schema is stable, set `JPA_DDL_AUTO=validate` in `.env.uat`. The app will then
**refuse to start** if code and schema disagree — the desired safety behavior. To adopt it:
1. Boot once with `update` so the schema is complete.
2. Flip to `validate` and restart `java-backend`.
3. A startup failure now means a real drift to investigate, not a silent ALTER.

## Known UAT environment caveats
- **OCR Python deps**: `ocr-service/requirements.txt` is intentionally minimal (pure-Python).
  The image installs an OCR-extras layer (`pdfplumber`, `opencv-python-headless`, `pytesseract`,
  …) so scanned-PDF paths work, but the canonical local env is conda. If a scanned-doc test
  behaves differently than local, reconcile by promoting the conda extras into `requirements.txt`.
- **Groq is load-bearing** (P-14a): SCA-grid / gap-fill extraction needs `GROQ_API_KEY`. Without
  it those fields fall back and more rules land VERIFY. Set real Groq keys in `.env.uat`.
- **`NEXT_PUBLIC_JAVA_URL` is baked at build time.** Changing the UAT host means rebuilding the
  frontend image with the new value.
