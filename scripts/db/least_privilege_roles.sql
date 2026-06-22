-- ─────────────────────────────────────────────────────────────────────────────
-- Least-privilege DB roles — make table ownership DB-ENFORCED, not just code-enforced
--
-- WHY: Java and Python share one database (localhost/ardurApprisal). Today Python
-- connects as the `postgres` SUPERUSER, so nothing at the DB level stops it from
-- dropping or rewriting Java's tables — only manage_db.py's discipline does. This
-- script scopes each service to its own tables so the database itself guarantees
-- the ownership boundary the architecture relies on.
--
-- MODEL (one database, two scoped roles — NO second database, NO Python code change):
--   apprisal_python : owns the adaptive_* tables, CANNOT touch Java's tables.
--   apprisal_java   : owns the workflow/QC tables, CANNOT touch Python's adaptive_*.
--   (Postgres tables stay in schema `public`; isolation is by ownership + grants.)
--
-- SAFE ROLLOUT — NOT auto-applied. Run deliberately as a DB superuser, then update
-- each service's .env to use its scoped role, then restart the services:
--     psql "postgres://postgres@localhost/ardurApprisal" -f scripts/db/least_privilege_roles.sql
-- After it runs:
--   1) ocr-service/.env : DATABASE_URL=postgresql://apprisal_python:<pw>@localhost/ardurApprisal
--   2) root .env        : DB_USERNAME=apprisal_java  DB_PASSWORD=<pw>   (if you migrate Java too)
--   3) verify with the SELECT at the bottom, then restart both services.
-- Set real passwords below before running.
-- ─────────────────────────────────────────────────────────────────────────────

\set ON_ERROR_STOP on

-- 1) Roles (login users). Replace the passwords.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apprisal_python') THEN
    CREATE ROLE apprisal_python LOGIN PASSWORD 'CHANGE_ME_python';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apprisal_java') THEN
    CREATE ROLE apprisal_java LOGIN PASSWORD 'CHANGE_ME_java';
  END IF;
END$$;

-- 2) Both may connect and use the public schema. Python needs CREATE (manage_db.py
--    create_all builds its own tables); Java's DDL is Hibernate ddl-auto.
GRANT CONNECT ON DATABASE "ardurApprisal" TO apprisal_python, apprisal_java;
GRANT USAGE, CREATE ON SCHEMA public TO apprisal_python, apprisal_java;

-- 3) Hand each role ownership of ITS OWN tables + sequences. Ownership = full control
--    of your own tables and NONE of the other role's (a non-owner non-superuser cannot
--    ALTER/DROP another role's table). adaptive_* → Python; everything else → Java.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    IF r.tablename LIKE 'adaptive_%' THEN
      EXECUTE format('ALTER TABLE public.%I OWNER TO apprisal_python', r.tablename);
    ELSE
      EXECUTE format('ALTER TABLE public.%I OWNER TO apprisal_java',   r.tablename);
    END IF;
  END LOOP;

  FOR r IN
    SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
  LOOP
    IF r.sequencename LIKE 'adaptive_%' THEN
      EXECUTE format('ALTER SEQUENCE public.%I OWNER TO apprisal_python', r.sequencename);
    ELSE
      EXECUTE format('ALTER SEQUENCE public.%I OWNER TO apprisal_java',   r.sequencename);
    END IF;
  END LOOP;
END$$;

-- 4) Hard wall: explicitly REVOKE each role from the OTHER's tables, in case a prior
--    PUBLIC grant existed. (Ownership already blocks DDL; this blocks DML too.)
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    IF r.tablename LIKE 'adaptive_%' THEN
      EXECUTE format('REVOKE ALL ON public.%I FROM apprisal_java', r.tablename);
    ELSE
      EXECUTE format('REVOKE ALL ON public.%I FROM apprisal_python', r.tablename);
    END IF;
  END LOOP;
END$$;

-- 5) (Optional) cross-read: if Java must READ Python's adaptive_* results directly via
--    SQL (it currently does NOT — it gets results over HTTP), grant read-only instead of
--    full access. Uncomment if/when needed:
-- DO $$
-- DECLARE r record; BEGIN
--   FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'adaptive_%' LOOP
--     EXECUTE format('GRANT SELECT ON public.%I TO apprisal_java', r.tablename);
--   END LOOP;
-- END$$;

-- 6) Verify ownership split (run after applying):
SELECT tableowner,
       count(*) FILTER (WHERE tablename LIKE 'adaptive_%') AS adaptive_tables,
       count(*) FILTER (WHERE tablename NOT LIKE 'adaptive_%') AS java_tables
FROM pg_tables
WHERE schemaname = 'public'
GROUP BY tableowner
ORDER BY tableowner;
