-- V23: Store intake-level document quality warnings for reviewer context.

ALTER TABLE batch_file
    ADD COLUMN IF NOT EXISTS document_quality_flags TEXT;

ALTER TABLE batch_file_AUD
    ADD COLUMN IF NOT EXISTS document_quality_flags TEXT;
