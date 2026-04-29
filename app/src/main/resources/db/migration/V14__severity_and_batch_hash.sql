-- V14: Add severity to qc_rule_result + file_hash to batch for deduplication

-- qc_rule_result: severity level for each rule outcome
ALTER TABLE qc_rule_result
    ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'STANDARD';

-- batch: SHA-256 hash of the uploaded ZIP for idempotent re-upload detection
ALTER TABLE batch
    ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_batch_file_hash ON batch (file_hash)
    WHERE file_hash IS NOT NULL;

-- batch: error detail for failed batches (visible to admin)
ALTER TABLE batch
    ADD COLUMN IF NOT EXISTS error_message TEXT;
