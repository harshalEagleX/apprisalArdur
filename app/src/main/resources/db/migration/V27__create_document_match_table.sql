CREATE TABLE IF NOT EXISTS document_match (
    id BIGSERIAL PRIMARY KEY,
    appraisal_file_id BIGINT NOT NULL,
    supporting_file_id BIGINT,
    supporting_file_type VARCHAR(20) NOT NULL,
    match_type VARCHAR(50) NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    match_reason TEXT,
    ambiguous_candidates_json TEXT,
    rejected_candidates_json TEXT,
    matched_by BIGINT,
    matched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_document_match_appraisal_file
        FOREIGN KEY (appraisal_file_id) REFERENCES batch_file(id) ON DELETE CASCADE,
    CONSTRAINT fk_document_match_supporting_file
        FOREIGN KEY (supporting_file_id) REFERENCES batch_file(id) ON DELETE SET NULL,
    CONSTRAINT fk_document_match_matched_by
        FOREIGN KEY (matched_by) REFERENCES _user(id) ON DELETE SET NULL,
    CONSTRAINT uq_document_match_appraisal_support_type
        UNIQUE (appraisal_file_id, supporting_file_type)
);

CREATE INDEX IF NOT EXISTS idx_document_match_supporting
    ON document_match (supporting_file_id);
