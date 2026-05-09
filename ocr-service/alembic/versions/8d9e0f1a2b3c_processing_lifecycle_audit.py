"""processing lifecycle audit tables

Revision ID: 8d9e0f1a2b3c
Revises: 7b8c9d0e1f2a
Create Date: 2026-05-09

"""

from alembic import op
import sqlalchemy as sa


revision = "8d9e0f1a2b3c"
down_revision = "7b8c9d0e1f2a"
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if not _column_exists(inspector, table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(inspector, name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not _index_exists(inspector, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "processing_jobs"):
        op.create_table(
            "processing_jobs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("correlation_id", sa.String(length=128), nullable=True),
            sa.Column("batch_id", sa.String(length=64), nullable=True),
            sa.Column("batch_file_id", sa.String(length=64), nullable=True),
            sa.Column("qc_result_id", sa.String(length=64), nullable=True),
            sa.Column("source_document_hash", sa.String(length=64), nullable=True),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("model_provider", sa.String(length=50), nullable=True),
            sa.Column("model_name", sa.String(length=100), nullable=True),
            sa.Column("vision_model", sa.String(length=100), nullable=True),
            sa.Column("traceparent", sa.String(length=128), nullable=True),
            sa.Column("tracestate", sa.Text(), nullable=True),
            sa.Column("rule_set_version", sa.String(length=50), nullable=True),
            sa.Column("current_stage", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=True),
            sa.Column("document_id", sa.UUID(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("failed_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_processing_jobs_idempotency_key", "processing_jobs", ["idempotency_key"], unique=True)
    _create_index_if_missing(inspector, "ix_processing_jobs_correlation_id", "processing_jobs", ["correlation_id"])
    _create_index_if_missing(inspector, "ix_processing_jobs_batch_id", "processing_jobs", ["batch_id"])
    _create_index_if_missing(inspector, "ix_processing_jobs_batch_file_id", "processing_jobs", ["batch_file_id"])
    _create_index_if_missing(inspector, "ix_processing_jobs_qc_result_id", "processing_jobs", ["qc_result_id"])
    _create_index_if_missing(inspector, "ix_processing_jobs_source_document_hash", "processing_jobs", ["source_document_hash"])
    _create_index_if_missing(inspector, "ix_processing_jobs_current_stage", "processing_jobs", ["current_stage"])
    _create_index_if_missing(inspector, "ix_processing_jobs_status", "processing_jobs", ["status"])
    _create_index_if_missing(inspector, "ix_processing_jobs_corr_status", "processing_jobs", ["correlation_id", "status"])
    _create_index_if_missing(inspector, "ix_processing_jobs_hash_status", "processing_jobs", ["source_document_hash", "status"])

    if not _table_exists(inspector, "processing_stages"):
        op.create_table(
            "processing_stages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.UUID(), nullable=False),
            sa.Column("stage_name", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_processing_stages_job_id", "processing_stages", ["job_id"])
    _create_index_if_missing(inspector, "ix_processing_stages_stage_name", "processing_stages", ["stage_name"])
    _create_index_if_missing(inspector, "ix_processing_stages_status", "processing_stages", ["status"])
    _create_index_if_missing(inspector, "ix_processing_stages_job_stage", "processing_stages", ["job_id", "stage_name"])

    if not _table_exists(inspector, "llm_call_logs"):
        op.create_table(
            "llm_call_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.UUID(), nullable=True),
            sa.Column("correlation_id", sa.String(length=128), nullable=True),
            sa.Column("stage_name", sa.String(length=80), nullable=True),
            sa.Column("task_name", sa.String(length=100), nullable=True),
            sa.Column("prompt_hash", sa.String(length=64), nullable=False),
            sa.Column("model_name", sa.String(length=100), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=True),
            sa.Column("timed_out", sa.Boolean(), nullable=True),
            sa.Column("fallback_path", sa.String(length=80), nullable=True),
            sa.Column("confidence_label", sa.String(length=30), nullable=True),
            sa.Column("response_hash", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_llm_call_logs_job_id", "llm_call_logs", ["job_id"])
    _create_index_if_missing(inspector, "ix_llm_call_logs_correlation_id", "llm_call_logs", ["correlation_id"])
    _create_index_if_missing(inspector, "ix_llm_call_logs_prompt_hash", "llm_call_logs", ["prompt_hash"])
    _create_index_if_missing(inspector, "ix_llm_call_logs_status", "llm_call_logs", ["status"])
    _create_index_if_missing(inspector, "ix_llm_call_logs_job_stage", "llm_call_logs", ["job_id", "stage_name"])

    if not _table_exists(inspector, "confidence_calibration"):
        op.create_table(
            "confidence_calibration",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("field_name", sa.String(length=100), nullable=False),
            sa.Column("extraction_method", sa.String(length=50), nullable=False),
            sa.Column("reviewed_count", sa.Integer(), nullable=False),
            sa.Column("correct_count", sa.Integer(), nullable=False),
            sa.Column("incorrect_count", sa.Integer(), nullable=False),
            sa.Column("historical_precision", sa.Float(), nullable=True),
            sa.Column("historical_recall", sa.Float(), nullable=True),
            sa.Column("sample_size", sa.Integer(), nullable=False),
            sa.Column("last_calibrated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("field_name", "extraction_method", name="uq_conf_calibration_field_method"),
        )
    else:
        _add_column_if_missing(inspector, "confidence_calibration", sa.Column("historical_recall", sa.Float(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_conf_calibration_field_method", "confidence_calibration", ["field_name", "extraction_method"])

    _add_column_if_missing(inspector, "extracted_fields", sa.Column("processing_job_id", sa.UUID(), sa.ForeignKey("processing_jobs.id"), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("processing_job_id", sa.UUID(), sa.ForeignKey("processing_jobs.id"), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("severity", sa.String(length=30), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("extracted_value", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("expected_value", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("confidence_score", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("target_field", sa.String(length=100), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("rule_version", sa.String(length=50), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("processing_job_id", sa.UUID(), sa.ForeignKey("processing_jobs.id"), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("correlation_id", sa.String(length=128), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("reviewer_role", sa.String(length=50), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("decision_latency_ms", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("acknowledged", sa.Boolean(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("source_page", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("bbox_x", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("bbox_y", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("bbox_w", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("bbox_h", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "feedback_events", sa.Column("confidence_score", sa.Float(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_rule_results_job_rule", "rule_results", ["processing_job_id", "rule_id"])
    _create_index_if_missing(inspector, "ix_feedback_events_correlation_id", "feedback_events", ["correlation_id"])


def downgrade():
    op.drop_index("ix_feedback_events_correlation_id", table_name="feedback_events")
    op.drop_index("ix_rule_results_job_rule", table_name="rule_results")
    for column_name in [
        "confidence_score", "bbox_h", "bbox_w", "bbox_y", "bbox_x", "source_page",
        "acknowledged", "decision_latency_ms", "reviewer_role", "correlation_id",
        "processing_job_id",
    ]:
        op.drop_column("feedback_events", column_name)
    for column_name in [
        "rule_version", "target_field", "confidence_score", "expected_value",
        "extracted_value", "severity", "processing_job_id",
    ]:
        op.drop_column("rule_results", column_name)
    op.drop_column("extracted_fields", "processing_job_id")
    op.drop_index("ix_conf_calibration_field_method", table_name="confidence_calibration")
    op.drop_table("confidence_calibration")
    op.drop_index("ix_llm_call_logs_job_stage", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_status", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_prompt_hash", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_correlation_id", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_job_id", table_name="llm_call_logs")
    op.drop_table("llm_call_logs")
    op.drop_index("ix_processing_stages_job_stage", table_name="processing_stages")
    op.drop_index("ix_processing_stages_status", table_name="processing_stages")
    op.drop_index("ix_processing_stages_stage_name", table_name="processing_stages")
    op.drop_index("ix_processing_stages_job_id", table_name="processing_stages")
    op.drop_table("processing_stages")
    op.drop_index("ix_processing_jobs_hash_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_corr_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_current_stage", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_source_document_hash", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_qc_result_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_batch_file_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_batch_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_correlation_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_idempotency_key", table_name="processing_jobs")
    op.drop_table("processing_jobs")
