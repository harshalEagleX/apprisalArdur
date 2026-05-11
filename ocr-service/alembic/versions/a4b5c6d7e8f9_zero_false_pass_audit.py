"""zero false pass audit metadata

Revision ID: a4b5c6d7e8f9
Revises: 8d9e0f1a2b3c
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "a4b5c6d7e8f9"
down_revision = "8d9e0f1a2b3c"
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if not _column_exists(inspector, table_name, column.name):
        op.add_column(table_name, column)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_column_if_missing(inspector, "extracted_fields", sa.Column("extraction_status", sa.String(length=30), nullable=False, server_default="NOT_FOUND"))
    _add_column_if_missing(inspector, "extracted_fields", sa.Column("source_document", sa.String(length=50), nullable=True))
    _add_column_if_missing(inspector, "extracted_fields", sa.Column("parser", sa.String(length=80), nullable=True))
    _add_column_if_missing(inspector, "extracted_fields", sa.Column("normalization_steps", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "extracted_fields", sa.Column("failure_reason", sa.Text(), nullable=True))

    _add_column_if_missing(inspector, "rule_results", sa.Column("source_documents", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("compared_fields", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("compared_values", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("comparison_method", sa.String(length=80), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("decision_path", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("exception_type", sa.String(length=120), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("exception_trace", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("stage", sa.String(length=80), nullable=True))
    _add_column_if_missing(inspector, "rule_results", sa.Column("retry_eligible", sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade():
    for column in (
        "retry_eligible",
        "stage",
        "exception_trace",
        "exception_type",
        "decision_path",
        "comparison_method",
        "compared_values",
        "compared_fields",
        "source_documents",
    ):
        op.drop_column("rule_results", column)

    for column in (
        "failure_reason",
        "normalization_steps",
        "parser",
        "source_document",
        "extraction_status",
    ):
        op.drop_column("extracted_fields", column)
