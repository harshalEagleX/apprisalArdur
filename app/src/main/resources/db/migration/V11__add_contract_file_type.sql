-- V11: Add CONTRACT file type support
-- No schema change needed — file_type is a VARCHAR, not a DB enum.
-- This migration just documents the new CONTRACT value.

-- Add python_document_id column to qc_result for linking to Python cache
ALTER TABLE qc_result ADD COLUMN IF NOT EXISTS python_document_id VARCHAR(36);
ALTER TABLE qc_result ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT FALSE;

-- Add severity column to qc_rule_result (matches Phase 3 Python changes)
ALTER TABLE qc_rule_result ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'STANDARD';
ALTER TABLE qc_rule_result ADD COLUMN IF NOT EXISTS source_page INTEGER;
ALTER TABLE qc_rule_result ADD COLUMN IF NOT EXISTS field_confidence DOUBLE PRECISION;
