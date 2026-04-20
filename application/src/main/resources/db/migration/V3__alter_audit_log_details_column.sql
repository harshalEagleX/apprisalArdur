-- V3: Change audit_log.details from jsonb to text
ALTER TABLE audit_log ALTER COLUMN details TYPE TEXT;
