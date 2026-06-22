# Migration & Release Runbook (shared Postgres)

Closes audit items **MIG-001, MIG-003, MIG-006, MIG-009, MIG-010, DB-006**.

The platform uses **no migration runner** by policy (Java = Hibernate `ddl-auto`, Python = `manage_db.py`). That keeps day-to-day simple but leaves three gaps this runbook fills: a reviewed schema record per release, an explicit cross-service deploy order, and a rollback path.

## 1. Per-release schema snapshot (the "migration note")

Before tagging a release, capture a schema-only snapshot and commit it:

```bash
DB_URL="$DATABASE_URL" scripts/db/snapshot_schema.sh    # writes db-snapshots/schema-<date>-<sha>.sql
diff db-snapshots/schema-<prev>.sql db-snapshots/schema-<new>.sql   # THIS diff is the migration note
```

Review the diff in the PR. Additive, nullable/defaulted columns are safe (the codebase already follows this — e.g. `confidence_score`, `pdf_page`, `bbox_*` ship with `columnDefinition ... DEFAULT`). A column drop or type change is **not** auto-safe — see §3.

## 2. Production schema validation (stop silent auto-mutation)

In production set `JPA_DDL_AUTO=validate` (the app already supports this env, default `update`). Hibernate then **verifies** the live schema matches the entities and refuses to silently alter it. Apply reviewed DDL by hand (from the snapshot diff) *before* deploying the code that needs it.

## 3. Cross-service deploy order (Java + Python share the DB)

Because table ownership is **disjoint** (Java owns workflow/QC tables; Python owns `adaptive_*`), most changes are independent. For the few shared-contract changes:

| Change type | Order | Why |
|---|---|---|
| Add column / table (additive) | DDL → either service | Old code ignores new columns |
| New field in PythonQCResponse | bump `schema_version`, deploy **Python then Java** | Java tolerates unknown fields (`@JsonIgnoreProperties`); drift is logged |
| Remove/rename column | Two-phase: (1) stop writing, deploy; (2) drop column next release | Never break the still-running peer |
| New rule status string | deploy Python; Java logs unknown status & treats as review (DB-002) | No coordinated deploy needed |

## 4. Rollback

- **Code rollback:** redeploy the previous artifact. Safe as long as the schema is backward-compatible (additive changes are — that's why §1 review matters).
- **Schema rollback:** additive changes need no rollback (old code ignores the new column). For a destructive change that must be undone, restore the column from the previous snapshot in `db-snapshots/` and redeploy the matching code. Keep at least the last 2 snapshots.
- **Python tables:** `cd ocr-service && python manage_db.py recreate` rebuilds `adaptive_*` (operational/cache data only — no workflow truth is lost, per the `StuckBatchReconciler` consistency model).

## 5. Wire-contract version

`PythonQCResponse.schema_version` (currently `"1.0"`) is the explicit version of the Java↔Python JSON contract. Bump it (Python `CONTRACT_SCHEMA_VERSION` + Java `EXPECTED_PYTHON_SCHEMA_VERSION`) on any structural change to the response or its nested `rule_results`/`evidence`/`timings`. A mismatch is logged at persist time so a half-deployed pair is caught in logs, not as silent corruption.
