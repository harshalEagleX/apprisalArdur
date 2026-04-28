-- V5: Add order_id column to batch_file for matching appraisal↔engagement files
-- The order_id is extracted from filename pattern: appraisal_001.pdf → order_id = '001'

ALTER TABLE batch_file ADD COLUMN order_id VARCHAR(50);

-- Backfill existing records by extracting order_id from filename
-- Pattern: {type}_{orderId}.pdf → extract orderId
UPDATE batch_file 
SET order_id = REGEXP_REPLACE(
    REGEXP_REPLACE(filename, '\.[^.]+$', ''),  -- Remove extension (.pdf)
    '^.*_', ''                                  -- Remove prefix before last underscore
)
WHERE order_id IS NULL;

-- Create indexes for efficient file matching queries
CREATE INDEX idx_batch_file_order_id ON batch_file(order_id);
CREATE INDEX idx_batch_file_batch_order ON batch_file(batch_id, order_id);
CREATE INDEX idx_batch_file_batch_order_type ON batch_file(batch_id, order_id, file_type);
