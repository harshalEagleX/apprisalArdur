-- =============================================================================
-- Scrub legacy local-LLM model labels (ollama / llava:7b) from persisted rows.
--
-- Ollama was removed; the engine uses Groq. New runs already record the correct
-- labels, but historical rows still display "ollama · llava:7b" on the batch /
-- DocStats screens, which is confusing. This rewrites those stored labels to the
-- current Groq equivalents so no removed provider is ever shown.
--   text model  -> gpt-oss-120b   |   vision model -> llama-4-scout   |   provider -> groq
--
--   psql -d shal -f scripts/scrub_legacy_model_labels.sql
-- Idempotent: re-running is a no-op once the strings are gone.
-- =============================================================================

-- processing_metrics.model_version (the text model that ran)
UPDATE processing_metrics
SET model_version = 'gpt-oss-120b'
WHERE model_version IN ('llava:7b', 'llava:13b', 'mistral:7b');

-- qc_result.python_response (stored Python response JSON: model_provider / model_name / vision_model)
UPDATE qc_result
SET python_response = replace(
                        replace(
                          replace(python_response, '"vision_model": "llava:7b"', '"vision_model": "llama-4-scout"'),
                          'llava:7b', 'gpt-oss-120b'),
                        '"ollama"', '"groq"')
WHERE python_response LIKE '%llava%' OR python_response LIKE '%ollama%';

-- business_event.payload_json (model_name / vision_model / model_provider in QC event payloads)
UPDATE business_event
SET payload_json = replace(
                     replace(
                       replace(payload_json, '"vision_model":"llava:7b"', '"vision_model":"llama-4-scout"'),
                       'llava:7b', 'gpt-oss-120b'),
                     '"ollama"', '"groq"')
WHERE payload_json LIKE '%llava%' OR payload_json LIKE '%ollama%';
