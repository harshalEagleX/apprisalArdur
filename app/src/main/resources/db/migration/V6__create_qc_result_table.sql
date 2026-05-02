-- V6: Create QC Result table to store Python QC processing results

CREATE TABLE qc_result (
    id BIGSERIAL PRIMARY KEY,
    batch_file_id BIGINT NOT NULL REFERENCES batch_file(id) ON DELETE CASCADE,
    
    -- Decision fields
    qc_decision VARCHAR(20) NOT NULL,      -- AUTO_PASS, TO_VERIFY, AUTO_FAIL
    final_decision VARCHAR(10),             -- PASS, FAIL (after reviewer verification)
    
    -- Python response storage
    python_response TEXT,                   -- Full JSON from Python /qc/process
    
    -- Counts from Python response
    total_rules INT DEFAULT 0,
    passed_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    
    -- Processing metadata
    processing_time_ms INT,
    extraction_method VARCHAR(50),          -- pymupdf, tesseract, env
    
    -- Timestamps
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Review metadata
    reviewed_by BIGINT REFERENCES _user(id),
    reviewed_at TIMESTAMP,
    reviewer_notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Each batch_file can only have one QC result
    CONSTRAINT uq_qc_result_batch_file UNIQUE (batch_file_id)
);

-- Indexes for common queries
CREATE INDEX idx_qc_result_decision ON qc_result(qc_decision);
CREATE INDEX idx_qc_result_final ON qc_result(final_decision);
CREATE INDEX idx_qc_result_reviewed_by ON qc_result(reviewed_by);
