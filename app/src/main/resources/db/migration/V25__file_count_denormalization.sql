-- Replace the @Formula subquery on Batch.fileCount with a denormalized column.
-- Eliminates one correlated subquery per row on every batch list load.
--
-- Three-step pattern (safe on existing data):
--   1. Add column with temporary DEFAULT 0 (allows ALTER on non-empty tables)
--   2. Backfill all existing rows from batch_file count
--   3. Lock in NOT NULL after backfill guarantees no NULLs remain

ALTER TABLE batch ADD COLUMN IF NOT EXISTS file_count INTEGER NOT NULL DEFAULT 0;

UPDATE batch
SET file_count = (
    SELECT COUNT(*) FROM batch_file bf WHERE bf.batch_id = batch.id
);

-- batch_aud stores one row per audit revision. Historical revisions pre-date this
-- column so they legitimately have no file count — NULL is correct here.
ALTER TABLE batch_aud ADD COLUMN IF NOT EXISTS file_count INTEGER;
