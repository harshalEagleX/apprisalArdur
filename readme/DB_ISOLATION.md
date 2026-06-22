# Shared Database — Why It's Fine, and the One Thing to Fix

## The observation

Both services point at the **same database**:

```
Java   → localhost:5432 / ardurApprisal   (user: eaglexmac)
Python → localhost:5432 / ardurApprisal   (user: postgres ← superuser)
```

## Why one shared database is the right call here

"Same database" only causes the classic shared-DB problems when two services write the **same tables**. They don't:

| Owner | Tables |
|---|---|
| Java (JPA) | `batch`, `batch_file`, `qc_result`, `qc_rule_result`, `document_match`, `business_event`, `audit_log`, `doc_stat*`, `processing_metrics`, `user`, `client`, … |
| Python (`manage_db.py`) | `adaptive_*` only |

The table sets are **disjoint**, and Java↔Python integration is over **HTTP + the Redis/Celery queue** — Python *returns* results, Java writes `qc_result`. Python never writes Java's tables. So one Postgres instance gives you ACID, one place to query, and simple ops, **without** the "distributed monolith" coupling. For an internal single-org tool, splitting into two databases would add cost for no real benefit. **Keep one database.**

## The real gap: Python runs as superuser

The only genuine risk behind "same DB" is that **Python connects as `postgres` (superuser)** — so the ownership boundary is enforced only by `manage_db.py`'s good behavior, not by the database. A bug or a stray script *could* reach Java's tables.

**Fix:** least-privilege roles — same database, but Postgres itself enforces the boundary. See `scripts/db/least_privilege_roles.sql`:

- `apprisal_python` owns the `adaptive_*` tables and is **revoked** from Java's tables.
- `apprisal_java` owns the workflow/QC tables and is **revoked** from `adaptive_*`.
- Neither is a superuser. No second database, no Python code change (tables stay in `public`; isolation is by ownership + grants).

### Apply (run-when-ready, as a DB superuser)

1. Edit the two passwords in `scripts/db/least_privilege_roles.sql`.
2. `psql "postgres://postgres@localhost/ardurApprisal" -f scripts/db/least_privilege_roles.sql`
3. Point Python at the scoped role: `ocr-service/.env` → `DATABASE_URL=postgresql://apprisal_python:<pw>@localhost/ardurApprisal`
4. (Optional, recommended) point Java at its role: root `.env` → `DB_USERNAME=apprisal_java`, `DB_PASSWORD=<pw>`.
5. Restart both services. Confirm with the verify query at the bottom of the script (each role should own only its own tables).

After this, even if Python tried to `DROP TABLE batch`, Postgres refuses — the isolation your architecture assumes is now guaranteed by the database, not by convention.

## When you'd actually want two databases

Only if you later need independent teams deploying on independent schedules, separate scaling/storage, or true bounded-context autonomy. None of those apply to an internal single-org tool today — revisit only if that changes (see `TENANCY_DECISION.md`).
