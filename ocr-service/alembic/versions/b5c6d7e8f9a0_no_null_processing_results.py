"""no null processing result cells

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _exec_if_column(inspector, table_name: str, column_name: str, sql: str) -> None:
    if _has_column(inspector, table_name, column_name):
        op.execute(sa.text(sql))


def _alter_not_null(inspector, table_name: str, column_name: str, type_) -> None:
    if _has_column(inspector, table_name, column_name):
        op.alter_column(table_name, column_name, existing_type=type_, nullable=False)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _exec_if_column(inspector, "page_ocr_results", "hocr_text",
                    "UPDATE page_ocr_results SET hocr_text = '' WHERE hocr_text IS NULL")

    extracted_text_defaults = {
        "field_value": "__NOT_FOUND__",
        "source_document": "appraisal",
        "parser": "unknown_parser",
        "extraction_method": "not_found",
        "raw_ocr_text": "__NOT_FOUND__",
        "normalization_steps": "[]",
    }
    for column, default in extracted_text_defaults.items():
        _exec_if_column(inspector, "extracted_fields", column,
                        f"UPDATE extracted_fields SET {column} = '{default}' WHERE {column} IS NULL")
    _exec_if_column(
        inspector,
        "extracted_fields",
        "failure_reason",
        "UPDATE extracted_fields SET failure_reason = CASE "
        "WHEN UPPER(COALESCE(extraction_status, '')) = 'FOUND' THEN 'no_failure' "
        "ELSE 'not_found' END WHERE failure_reason IS NULL",
    )
    _exec_if_column(inspector, "extracted_fields", "source_page",
                    "UPDATE extracted_fields SET source_page = 0 WHERE source_page IS NULL")
    for column in ("bbox_x", "bbox_y", "bbox_w", "bbox_h"):
        _exec_if_column(inspector, "extracted_fields", column,
                        f"UPDATE extracted_fields SET {column} = 0.0 WHERE {column} IS NULL")

    rule_text_defaults = {
        "rule_name": "UNKNOWN_RULE",
        "status": "system_error",
        "severity": "STANDARD",
        "message": "No rule message provided.",
        "action_item": "No reviewer action required.",
        "appraisal_value": "__NO_APPRAISAL_VALUE__",
        "engagement_value": "__NO_ENGAGEMENT_VALUE__",
        "extracted_value": "__NO_EXTRACTED_VALUE__",
        "expected_value": "__NO_EXPECTED_VALUE__",
        "target_field": "checklist_rule",
        "rule_version": "1.0",
        "source_documents": "[]",
        "compared_fields": "[]",
        "compared_values": "{}",
        "comparison_method": "not_comparison_based",
        "decision_path": "[]",
        "exception_type": "none",
        "exception_trace": "",
        "stage": "rule_engine",
    }
    for column, default in rule_text_defaults.items():
        escaped = default.replace("'", "''")
        _exec_if_column(inspector, "rule_results", column,
                        f"UPDATE rule_results SET {column} = '{escaped}' WHERE {column} IS NULL")
    _exec_if_column(inspector, "rule_results", "confidence_score",
                    "UPDATE rule_results SET confidence_score = 0.0 WHERE confidence_score IS NULL")
    _exec_if_column(inspector, "rule_results", "review_required",
                    "UPDATE rule_results SET review_required = false WHERE review_required IS NULL")
    _exec_if_column(inspector, "rule_results", "retry_eligible",
                    "UPDATE rule_results SET retry_eligible = false WHERE retry_eligible IS NULL")
    _exec_if_column(inspector, "rule_results", "source_page",
                    "UPDATE rule_results SET source_page = 0 WHERE source_page IS NULL")
    for column in ("bbox_x", "bbox_y", "bbox_w", "bbox_h"):
        _exec_if_column(inspector, "rule_results", column,
                        f"UPDATE rule_results SET {column} = 0.0 WHERE {column} IS NULL")

    _alter_not_null(inspector, "page_ocr_results", "hocr_text", sa.Text())
    for column in extracted_text_defaults:
        _alter_not_null(inspector, "extracted_fields", column, sa.Text() if column in {"field_value", "raw_ocr_text", "normalization_steps"} else sa.String())
    _alter_not_null(inspector, "extracted_fields", "failure_reason", sa.Text())
    _alter_not_null(inspector, "extracted_fields", "source_page", sa.Integer())
    for column in ("bbox_x", "bbox_y", "bbox_w", "bbox_h"):
        _alter_not_null(inspector, "extracted_fields", column, sa.Float())

    for column in rule_text_defaults:
        if column in {"message", "action_item", "appraisal_value", "engagement_value", "extracted_value", "expected_value", "source_documents", "compared_fields", "compared_values", "decision_path", "exception_trace"}:
            col_type = sa.Text()
        else:
            col_type = sa.String()
        _alter_not_null(inspector, "rule_results", column, col_type)
    _alter_not_null(inspector, "rule_results", "confidence_score", sa.Float())
    _alter_not_null(inspector, "rule_results", "review_required", sa.Boolean())
    _alter_not_null(inspector, "rule_results", "retry_eligible", sa.Boolean())
    _alter_not_null(inspector, "rule_results", "source_page", sa.Integer())
    for column in ("bbox_x", "bbox_y", "bbox_w", "bbox_h"):
        _alter_not_null(inspector, "rule_results", column, sa.Float())


def downgrade():
    # Keep the data backfill. Downgrade only relaxes nullability.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, columns in {
        "page_ocr_results": ["hocr_text"],
        "extracted_fields": [
            "field_value", "source_document", "source_page", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
            "parser", "extraction_method", "raw_ocr_text", "normalization_steps", "failure_reason",
        ],
        "rule_results": [
            "rule_name", "status", "severity", "message", "action_item", "appraisal_value",
            "engagement_value", "extracted_value", "expected_value", "confidence_score",
            "target_field", "rule_version", "review_required", "source_documents",
            "compared_fields", "compared_values", "comparison_method", "decision_path",
            "exception_type", "exception_trace", "stage", "retry_eligible", "source_page",
            "bbox_x", "bbox_y", "bbox_w", "bbox_h",
        ],
    }.items():
        for column in columns:
            if _has_column(inspector, table, column):
                op.alter_column(table, column, nullable=True)
