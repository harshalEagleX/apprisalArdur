-- =============================================================================
-- Backfill persisted pipeline-stage labels to the plain-language names.
--
-- Cause: the human stage label is SNAPSHOTTED into doc_stat rows at QC time
-- (doc_stat_stage.label, doc_stat.slowest_stage_label) from Python's
-- python_response._STAGE_LABELS. Renaming the label map only affects NEW runs, so
-- historical DocStats kept the old jargon (e.g. "Subject/contract gap-fill (LLM)").
-- This one-time backfill rewrites the stored labels for existing rows, keyed by the
-- stable stage key. Values MUST match python_response._STAGE_LABELS.
--
--   psql -d ardurApprisal -f scripts/backfill_stage_labels.sql
-- Idempotent: re-running is a no-op once labels already match.
-- =============================================================================

UPDATE doc_stat_stage AS s SET label = m.label
FROM (VALUES
    ('extract_appraisal',  'Reading the appraisal report'),
    ('sca_grid',           'Comparable sales grid'),
    ('sca_llm',            'Comparable sales analysis'),
    ('subject_llm',        'Subject & contract details'),
    ('sketch',             'Floor plan & living area'),
    ('photos',             'Property photographs'),
    ('locate',             'Preparing review highlights'),
    ('extract_engagement', 'Reading the engagement letter'),
    ('extract_contract',   'Reading the sales contract'),
    ('rules',              'Running quality checks'),
    ('extraction',         'Reading the documents'),
    ('done',               'Finishing up')
) AS m(stage, label)
WHERE s.stage = m.stage AND s.label IS DISTINCT FROM m.label;

-- doc_stat.slowest_stage_label stores the label text (not the key) — map old -> new.
UPDATE doc_stat AS d SET slowest_stage_label = m.new
FROM (VALUES
    ('Appraisal OCR + field extraction',  'Reading the appraisal report'),
    ('Sales-comparison grid',             'Comparable sales grid'),
    ('Comparable adjustments (LLM)',      'Comparable sales analysis'),
    ('Subject/contract gap-fill (LLM)',   'Subject & contract details'),
    ('Building-sketch GLA',               'Floor plan & living area'),
    ('Photograph analysis',               'Property photographs'),
    ('Field location (review highlights)', 'Preparing review highlights'),
    ('Engagement letter extraction',      'Reading the engagement letter'),
    ('Sales contract extraction',         'Reading the sales contract'),
    ('QC rule evaluation',                'Running quality checks')
) AS m(old, new)
WHERE d.slowest_stage_label = m.old;
