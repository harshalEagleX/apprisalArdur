-- Feedback corrections table for human-in-the-loop learning.
-- Compatible with PostgreSQL.

CREATE TABLE IF NOT EXISTS field_corrections (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    section VARCHAR(50),
    predicted_value TEXT,
    corrected_value TEXT,
    confidence_score FLOAT,
    was_correct BOOLEAN NOT NULL,
    operator_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_corrections_created_at
    ON field_corrections (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_field_corrections_field_name
    ON field_corrections (field_name);
