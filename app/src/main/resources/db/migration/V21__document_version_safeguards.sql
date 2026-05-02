-- V21: Document content versioning and QC source snapshot for stale-review protection.

ALTER TABLE batch_file
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS content_version BIGINT NOT NULL DEFAULT 1;

ALTER TABLE batch_file_AUD
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS content_version BIGINT;

CREATE INDEX IF NOT EXISTS idx_batch_file_content_hash
    ON batch_file (content_hash);

ALTER TABLE qc_result
    ADD COLUMN IF NOT EXISTS source_document_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_document_version BIGINT;

ALTER TABLE qc_result_AUD
    ADD COLUMN IF NOT EXISTS source_document_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_document_version BIGINT;
