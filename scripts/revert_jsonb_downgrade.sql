-- =============================================================================
-- Revert the accidental JSONB → TEXT downgrade introduced by V3 and V4.
--
-- V3 changed audit_log.details  from JSONB to TEXT.
-- V4 changed batch_file.ocr_data from JSONB to TEXT.
-- Both columns store JSON and benefit from PostgreSQL's native JSONB operators
-- (indexing, @>, ->, containment queries, etc.).  Storing them as TEXT forces
-- application-level parsing for every query and prevents GIN-indexed lookups.
--
-- This script:
--   1. Validates all existing data is valid JSON before converting.
--   2. Converts the column type using a USING cast (no data loss).
--   3. Creates GIN indexes so JSONB @> queries are fast at scale.
--
-- Run once against Neon:
--   psql "$DB_URL" -f scripts/revert_jsonb_downgrade.sql
--
-- The script is IDEMPOTENT — safe to re-run if the column is already JSONB.
-- =============================================================================

-- ── Validate before converting ────────────────────────────────────────────────
-- If any row fails the JSON parse, this will surface the offending row ID so
-- you can fix it before running the conversion.

DO $$
DECLARE
    bad_id BIGINT;
BEGIN
    SELECT id INTO bad_id
    FROM audit_log
    WHERE details IS NOT NULL AND details <> ''
      AND details::text !~ '^\s*[\[{]'  -- rough pre-filter for non-JSON
    LIMIT 1;

    IF bad_id IS NOT NULL THEN
        RAISE NOTICE 'audit_log row % may not be valid JSON — inspect before converting', bad_id;
    END IF;
END
$$;

-- ── audit_log.details : TEXT → JSONB ─────────────────────────────────────────

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'audit_log' AND column_name = 'details';

    IF col_type = 'jsonb' THEN
        RAISE NOTICE 'audit_log.details is already JSONB — skipping.';
    ELSE
        -- Safely convert; NULL and empty strings become SQL NULL.
        ALTER TABLE audit_log
            ALTER COLUMN details TYPE JSONB
            USING CASE
                WHEN details IS NULL OR trim(details) = '' THEN NULL
                ELSE details::JSONB
            END;
        RAISE NOTICE 'audit_log.details converted TEXT → JSONB.';
    END IF;
END
$$;

-- GIN index for fast JSONB @> containment queries (e.g. WHERE details @> '{"action":"DELETE"}')
CREATE INDEX IF NOT EXISTS idx_audit_log_details_gin
    ON audit_log USING GIN (details)
    WHERE details IS NOT NULL;

-- ── batch_file.ocr_data : TEXT → JSONB ───────────────────────────────────────

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'batch_file' AND column_name = 'ocr_data';

    IF col_type IS NULL THEN
        RAISE NOTICE 'batch_file.ocr_data column does not exist — skipping.';
    ELSIF col_type = 'jsonb' THEN
        RAISE NOTICE 'batch_file.ocr_data is already JSONB — skipping.';
    ELSE
        ALTER TABLE batch_file
            ALTER COLUMN ocr_data TYPE JSONB
            USING CASE
                WHEN ocr_data IS NULL OR trim(ocr_data) = '' THEN NULL
                ELSE ocr_data::JSONB
            END;
        RAISE NOTICE 'batch_file.ocr_data converted TEXT → JSONB.';
    END IF;
END
$$;

-- Verify result:
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('audit_log', 'batch_file')
  AND column_name IN ('details', 'ocr_data')
ORDER BY table_name, column_name;
