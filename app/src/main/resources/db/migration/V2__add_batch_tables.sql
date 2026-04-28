-- V2: Add batch processing tables and extend user table

-- Extend _user table
ALTER TABLE _user 
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS full_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS client_id BIGINT,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Create client table
CREATE TABLE IF NOT EXISTS client (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add foreign key constraint for user -> client
ALTER TABLE _user 
ADD CONSTRAINT fk_user_client 
FOREIGN KEY (client_id) REFERENCES client(id) ON DELETE SET NULL;

-- Create batch table
CREATE TABLE IF NOT EXISTS batch (
    id BIGSERIAL PRIMARY KEY,
    parent_batch_id VARCHAR(100) NOT NULL,
    client_id BIGINT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'UPLOADED',
    assigned_reviewer_id BIGINT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_batch_client FOREIGN KEY (client_id) REFERENCES client(id),
    CONSTRAINT fk_batch_creator FOREIGN KEY (created_by) REFERENCES _user(id),
    CONSTRAINT fk_batch_reviewer FOREIGN KEY (assigned_reviewer_id) REFERENCES _user(id)
);

-- Create batch_file table
CREATE TABLE IF NOT EXISTS batch_file (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    original_path VARCHAR(500),
    storage_path VARCHAR(500),
    file_size BIGINT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    ocr_data JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_batch_file_batch FOREIGN KEY (batch_id) REFERENCES batch(id) ON DELETE CASCADE
);

-- Create audit_log table
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id BIGINT,
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_log_user FOREIGN KEY (user_id) REFERENCES _user(id) ON DELETE SET NULL
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_batch_client_id ON batch(client_id);
CREATE INDEX IF NOT EXISTS idx_batch_status ON batch(status);
CREATE INDEX IF NOT EXISTS idx_batch_created_by ON batch(created_by);
CREATE INDEX IF NOT EXISTS idx_batch_file_batch_id ON batch_file(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_file_status ON batch_file(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
