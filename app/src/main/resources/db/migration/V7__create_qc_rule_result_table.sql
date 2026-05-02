-- V7: Create QC Rule Result table to store individual rule outcomes

CREATE TABLE qc_rule_result (
    id BIGSERIAL PRIMARY KEY,
    qc_result_id BIGINT NOT NULL REFERENCES qc_result(id) ON DELETE CASCADE,
    
    -- Rule identification (from Python)
    rule_id VARCHAR(10) NOT NULL,           -- S-1, S-2, C-1, C-2, etc.
    rule_name VARCHAR(100),                 -- "Property Address Validation"
    
    -- Rule outcome
    status VARCHAR(20) NOT NULL,            -- PASS, FAIL, VERIFY
    message TEXT,                           -- Detailed message from Python
    details TEXT,                           -- JSON with expected/actual values
    action_item TEXT,                       -- Suggested action
    
    -- Verification fields (for VERIFY/ERROR items)
    needs_verification BOOLEAN DEFAULT FALSE,
    reviewer_verified BOOLEAN,              -- null=pending, true=OK, false=rejected
    reviewer_comment TEXT,
    verified_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient queries
CREATE INDEX idx_qc_rule_result_qc ON qc_rule_result(qc_result_id);
CREATE INDEX idx_qc_rule_result_status ON qc_rule_result(status);
CREATE INDEX idx_qc_rule_result_rule_id ON qc_rule_result(rule_id);
CREATE INDEX idx_qc_rule_result_verify ON qc_rule_result(needs_verification) WHERE needs_verification = TRUE;
