-- V4: Change batch_file.ocr_data from jsonb to text
ALTER TABLE batch_file ALTER COLUMN ocr_data TYPE TEXT;
