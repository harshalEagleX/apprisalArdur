-- ─────────────────────────────────────────────────────────────────────────────
-- V26: Complete schema remediation
--
-- Full audit of every @Audited Java entity vs manually managed AUD tables plus
-- runtime-visible gaps between entity field definitions and migration history.
--
-- Sections:
--   1  qc_result — 4 entity columns missing from schema
--   2  qc_result — replace hard UNIQUE with partial unique (enables reruns)
--   3  qc_result_aud — complete column coverage + naming fixes
--   4  _user_aud — FK points at wrong revision table
--   5  batch_aud — missing columns (Envers INSERT failures)
--   6  batch_file_aud — missing columns (Envers INSERT failures)
--   7  client_aud — missing timestamp columns
--   8  Drop duplicate FK columns added by V18 (double-suffixed)
--   9  Drop orphan column qc_rule_result.field_confidence (V11 relic)
--  10  qc_rule_result.updated_at (reviewer workflow mutates rule results)
--  11  Missing indexes: cross-service bridge + hot query paths
-- ─────────────────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 1: qc_result — add 4 entity columns absent from all migrations
--
-- These columns existed only in the ddl-auto:create-built schema. With manual
-- database handling, keep this as reference SQL for any environment that needs it.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE qc_result
    ADD COLUMN IF NOT EXISTS python_processing_job_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS missing_documents         TEXT,
    ADD COLUMN IF NOT EXISTS rerun_of                  BIGINT REFERENCES qc_result(id),
    ADD COLUMN IF NOT EXISTS superseded_at             TIMESTAMP;

-- Partial index: instant lookup of the ONE active result per file
CREATE UNIQUE INDEX IF NOT EXISTS uq_qc_result_batch_file_active
    ON qc_result (batch_file_id)
    WHERE superseded_at IS NULL;

-- Sparse index: history panel queries ("how many reruns for file X?")
CREATE INDEX IF NOT EXISTS idx_qc_result_rerun_of
    ON qc_result (rerun_of)
    WHERE rerun_of IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 2: qc_result — replace hard UNIQUE with partial unique
--
-- V6: CONSTRAINT uq_qc_result_batch_file UNIQUE (batch_file_id)
-- A rerun creates a second QCResult for the same BatchFile (the first gets
-- superseded_at set). The hard UNIQUE violates before superseded_at is saved.
-- The partial unique above (Section 1) enforces one ACTIVE result per file
-- while allowing historical runs to coexist.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE qc_result
    DROP CONSTRAINT IF EXISTS uq_qc_result_batch_file;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 3: qc_result_aud — complete column coverage
--
-- V13 created a minimal stub. Subsequent migrations added columns to qc_result
-- without updating qc_result_aud. Envers silently drops data for unmapped cols
-- in some versions; in others it throws. All entity columns must be present.
--
-- Envers FK naming convention in this codebase:
--   @JoinColumn(name="foo") where "foo" doesn't end in "_id" → AUD col "foo_id"
--   @JoinColumn(name="bar_id") where it already ends in "_id" → AUD col "bar_id"
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE qc_result_aud
    -- @OneToOne batchFile: @JoinColumn(name="batch_file_id") → already ends _id
    ADD COLUMN IF NOT EXISTS batch_file_id             BIGINT,

    -- Aggregate counters added post-V13
    ADD COLUMN IF NOT EXISTS total_rules               INTEGER,
    ADD COLUMN IF NOT EXISTS passed_count              INTEGER,
    ADD COLUMN IF NOT EXISTS failed_count              INTEGER,
    ADD COLUMN IF NOT EXISTS verify_count              INTEGER,
    ADD COLUMN IF NOT EXISTS manual_pass_count         INTEGER,
    ADD COLUMN IF NOT EXISTS error_count               INTEGER,

    -- Processing metadata added post-V13
    ADD COLUMN IF NOT EXISTS processing_time_ms        INTEGER,
    ADD COLUMN IF NOT EXISTS extraction_method         VARCHAR(50),

    -- Python bridge fields (V11 added to main but not to AUD)
    ADD COLUMN IF NOT EXISTS python_document_id        VARCHAR(36),
    ADD COLUMN IF NOT EXISTS python_processing_job_id  VARCHAR(36),
    ADD COLUMN IF NOT EXISTS cache_hit                 BOOLEAN,

    -- Missing doc flags (entity field, never in any migration)
    ADD COLUMN IF NOT EXISTS missing_documents         TEXT,

    -- Rerun chain: @ManyToOne rerunOf @JoinColumn(name="rerun_of") → "rerun_of" + "_id"
    ADD COLUMN IF NOT EXISTS rerun_of_id               BIGINT,
    ADD COLUMN IF NOT EXISTS superseded_at             TIMESTAMP,

    -- Document version snapshot (V21 added to main + AUD — double-check safe)
    ADD COLUMN IF NOT EXISTS source_document_hash      VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_document_version   BIGINT,

    -- Review metadata that was never mirrored to AUD
    ADD COLUMN IF NOT EXISTS reviewer_notes            TEXT,
    ADD COLUMN IF NOT EXISTS processed_at              TIMESTAMP,
    ADD COLUMN IF NOT EXISTS created_at                TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at                TIMESTAMP;

-- Note: python_response (large TEXT blob) is marked @NotAudited on the entity
-- so it is intentionally absent from qc_result_aud.


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 4: _user_aud — fix FK to revision_info (not revinfo)
--
-- V13 wired _user_aud.rev → revinfo.rev (standard empty table).
-- Every other AUD table references revision_info.id (the custom enriched
-- table that RevisionInfo @RevisionEntity actually writes to).
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE _user_aud
    DROP CONSTRAINT IF EXISTS fk_user_aud_rev,
    DROP CONSTRAINT IF EXISTS _user_aud_rev_fkey;

ALTER TABLE _user_aud
    ADD CONSTRAINT fk_user_aud_revision_info
    FOREIGN KEY (rev) REFERENCES revision_info(id);


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 5: batch_aud — add every column missing from the V13 stub
--
-- V13 created batch_aud with 4 columns. Batch entity has 10+ audited fields.
-- Missing columns cause Envers to crash on every Batch save.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE batch_aud
    -- V2 added created_by to batch, never to batch_aud
    ADD COLUMN IF NOT EXISTS created_by    BIGINT,
    -- V14 added file_hash to batch, never to batch_aud
    ADD COLUMN IF NOT EXISTS file_hash     VARCHAR(64),
    -- Lifecycle timestamps present in entity, absent in AUD stub
    ADD COLUMN IF NOT EXISTS created_at   TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at   TIMESTAMP;

-- Note: error_message was added by V17 to batch_aud already (IF NOT EXISTS).
-- Note: file_count was added by V25 to batch_aud already.


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 6: batch_file_aud — add every column missing from the V13 stub
--
-- V13 created batch_file_aud with 8 columns. BatchFile entity has 15+ audited
-- fields. Missing columns cause Envers to crash on every BatchFile save.
-- ocr_data is intentionally excluded — it is @NotAudited on the entity.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE batch_file_aud
    ADD COLUMN IF NOT EXISTS original_path    VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS storage_path     VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS file_size        BIGINT,
    ADD COLUMN IF NOT EXISTS error_message    TEXT,
    ADD COLUMN IF NOT EXISTS created_at       TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at       TIMESTAMP;

-- Note: content_hash, content_version → V21 added to batch_file_aud ✓
-- Note: document_quality_flags → V23 added to batch_file_aud ✓
-- Note: ocr_data → @NotAudited on entity, intentionally not in AUD table


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 7: client_aud — add lifecycle timestamps
--
-- V13 created client_aud with 5 columns (name, code, status + PK + revtype).
-- Client entity has created_at + updated_at; both audited.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE client_aud
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 8: Drop duplicate FK columns added by V18
--
-- V18 added both the plain FK column AND the Envers _id-suffixed column to
-- qc_result_aud and qc_rule_result_aud. Envers only writes to one; the other
-- wastes storage and causes confusion.
-- ═══════════════════════════════════════════════════════════════════════════

-- qc_result_aud: review_locked_by_id is the Envers column; review_locked_by is the dup
ALTER TABLE qc_result_aud
    DROP COLUMN IF EXISTS review_locked_by;

-- qc_rule_result_aud: *_id columns are the Envers ones; plain names are the dups
ALTER TABLE qc_rule_result_aud
    DROP COLUMN IF EXISTS override_requested_by,
    DROP COLUMN IF EXISTS override_approved_by;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 9: Drop orphan column qc_rule_result.field_confidence
--
-- V11 added field_confidence DOUBLE PRECISION. The Java entity was never
-- updated to map it — the entity uses confidence_score (added in V20).
-- field_confidence has been empty since creation.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE qc_rule_result
    DROP COLUMN IF EXISTS field_confidence;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 10: qc_rule_result.updated_at
--
-- Rule results are mutated post-INSERT by the reviewer workflow:
-- reviewer_verified, reviewer_comment, override_*, review_session_token.
-- Without updated_at, activity feeds and "recently reviewed" queries fail.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE qc_rule_result
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

UPDATE qc_rule_result
    SET updated_at = created_at
    WHERE updated_at IS NULL AND created_at IS NOT NULL;

ALTER TABLE qc_rule_result_aud
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 11: Missing indexes
-- ═══════════════════════════════════════════════════════════════════════════

-- Cross-service bridge: Java → Python lookups (previously full-table scans)
CREATE INDEX IF NOT EXISTS idx_qc_result_python_doc_id
    ON qc_result (python_document_id)
    WHERE python_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_qc_result_python_job_id
    ON qc_result (python_processing_job_id)
    WHERE python_processing_job_id IS NOT NULL;

-- Analytics: "all business events involving entity X"
CREATE INDEX IF NOT EXISTS idx_business_event_entity
    ON business_event (entity_type, entity_id);

-- Reporting: "all outcomes for rule S-1 across all QC runs"
CREATE INDEX IF NOT EXISTS idx_qc_rule_result_rule_id
    ON qc_rule_result (rule_id);
