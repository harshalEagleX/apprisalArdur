-- V13: Hibernate Envers revision tables + operator session + processing metrics

-- ── Envers revision info ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS revision_info (
    id             SERIAL PRIMARY KEY,
    timestamp      BIGINT        NOT NULL,
    username       VARCHAR(100),
    ip_address     VARCHAR(50),
    correlation_id VARCHAR(64)
);

-- ── Operator session ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operator_session (
    id               BIGSERIAL   PRIMARY KEY,
    user_id          BIGINT      NOT NULL REFERENCES _user(id),
    session_token    VARCHAR(128) NOT NULL UNIQUE,
    started_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    last_active_at   TIMESTAMP,
    ended_at         TIMESTAMP,
    ip_address       VARCHAR(50),
    user_agent       VARCHAR(512),
    files_processed  INTEGER     NOT NULL DEFAULT 0,
    files_failed     INTEGER     NOT NULL DEFAULT 0,
    corrections_made INTEGER     NOT NULL DEFAULT 0,
    active_minutes   INTEGER     NOT NULL DEFAULT 0,
    status           VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE INDEX IF NOT EXISTS idx_op_session_user_start ON operator_session (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_session_status     ON operator_session (status);

-- ── Processing metrics ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processing_metrics (
    id                    BIGSERIAL  PRIMARY KEY,
    qc_result_id          BIGINT     NOT NULL UNIQUE REFERENCES qc_result(id),
    operator_session_id   BIGINT,
    correlation_id        VARCHAR(64),
    total_processing_ms   BIGINT,
    ocr_time_ms           BIGINT,
    queue_wait_ms         BIGINT,
    ocr_confidence_avg    DOUBLE PRECISION,
    ocr_confidence_min    DOUBLE PRECISION,
    fields_extracted      INTEGER,
    fields_low_confidence INTEGER,
    extraction_method     VARCHAR(50),
    pages_processed       INTEGER,
    rule_pass_rate        DOUBLE PRECISION,
    rules_total           INTEGER,
    rules_passed          INTEGER,
    rules_failed          INTEGER,
    rules_verify          INTEGER,
    model_version         VARCHAR(50),
    retry_count           INTEGER  NOT NULL DEFAULT 0,
    cache_hit             BOOLEAN  NOT NULL DEFAULT FALSE,
    file_size_bytes       BIGINT,
    created_at            TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pm_qc_result     ON processing_metrics (qc_result_id);
CREATE INDEX IF NOT EXISTS idx_pm_created_at    ON processing_metrics (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_session       ON processing_metrics (operator_session_id);
CREATE INDEX IF NOT EXISTS idx_pm_model_version ON processing_metrics (model_version);
CREATE INDEX IF NOT EXISTS idx_pm_cache_hit     ON processing_metrics (cache_hit);

-- ── Envers audit tables for core entities ────────────────────────────────────
-- Hibernate Envers creates _AUD tables automatically on ddl-auto=validate,
-- so we pre-create them to satisfy Flyway baseline.

CREATE TABLE IF NOT EXISTS batch_AUD (
    id             BIGINT  NOT NULL,
    rev            INTEGER NOT NULL REFERENCES revision_info(id),
    revtype        SMALLINT,
    parent_batch_id VARCHAR(255),
    status          VARCHAR(50),
    client_id       BIGINT,
    assigned_reviewer_id BIGINT,
    PRIMARY KEY (id, rev)
);

CREATE TABLE IF NOT EXISTS batch_file_AUD (
    id            BIGINT  NOT NULL,
    rev           INTEGER NOT NULL REFERENCES revision_info(id),
    revtype       SMALLINT,
    filename      VARCHAR(255),
    file_type     VARCHAR(50),
    status        VARCHAR(50),
    order_id      VARCHAR(100),
    batch_id      BIGINT,
    PRIMARY KEY (id, rev)
);

CREATE TABLE IF NOT EXISTS qc_result_AUD (
    id             BIGINT  NOT NULL,
    rev            INTEGER NOT NULL REFERENCES revision_info(id),
    revtype        SMALLINT,
    qc_decision    VARCHAR(50),
    final_decision VARCHAR(50),
    reviewed_by_id BIGINT,
    reviewed_at    TIMESTAMP,
    PRIMARY KEY (id, rev)
);

CREATE TABLE IF NOT EXISTS apprisal_user_AUD (
    id       BIGINT  NOT NULL,
    rev      INTEGER NOT NULL REFERENCES revision_info(id),
    revtype  SMALLINT,
    username VARCHAR(100),
    role     VARCHAR(50),
    email    VARCHAR(255),
    PRIMARY KEY (id, rev)
);

CREATE TABLE IF NOT EXISTS client_AUD (
    id      BIGINT  NOT NULL,
    rev     INTEGER NOT NULL REFERENCES revision_info(id),
    revtype SMALLINT,
    name    VARCHAR(255),
    code    VARCHAR(50),
    status  VARCHAR(50),
    PRIMARY KEY (id, rev)
);

CREATE TABLE IF NOT EXISTS qc_rule_result_AUD (
    id              BIGINT  NOT NULL,
    rev             INTEGER NOT NULL REFERENCES revision_info(id),
    revtype         SMALLINT,
    rule_id         VARCHAR(50),
    rule_name       VARCHAR(255),
    status          VARCHAR(50),
    review_required BOOLEAN,
    reviewer_verified BOOLEAN,
    reviewer_comment  TEXT,
    qc_result_id    BIGINT,
    PRIMARY KEY (id, rev)
);
