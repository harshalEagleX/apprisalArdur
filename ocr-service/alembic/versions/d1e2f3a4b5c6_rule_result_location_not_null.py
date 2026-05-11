"""Enforce NOT NULL with defaults on rule-result location columns.

Previously pdf_page, bbox_x/y/w/h, and confidence_score were nullable.
This migration:
  - Backfills any remaining NULLs with their sentinel values (0 / 0.0)
  - Alters each column to NOT NULL with the same default

The business rule these enforce:
  pdf_page   = 0  means "section default page was used (no field-level page)"
  bbox_*     = 0.0 means "page is known but field box was not captured"
  confidence = 0.0 means "confidence was not computed"

Reviewer code checks pdf_page > 0 before scrolling, so 0 is safe as a sentinel.

Revision ID: d1e2f3a4b5c6
Revises: b5c6d7e8f9a0
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill NULLs before applying NOT NULL constraint.
    # Using raw SQL to avoid ORM dependency and handle all DB dialects.
    op.execute("UPDATE qc_rule_result SET pdf_page       = 0   WHERE pdf_page       IS NULL")
    op.execute("UPDATE qc_rule_result SET bbox_x         = 0.0 WHERE bbox_x         IS NULL")
    op.execute("UPDATE qc_rule_result SET bbox_y         = 0.0 WHERE bbox_y         IS NULL")
    op.execute("UPDATE qc_rule_result SET bbox_w         = 0.0 WHERE bbox_w         IS NULL")
    op.execute("UPDATE qc_rule_result SET bbox_h         = 0.0 WHERE bbox_h         IS NULL")
    op.execute("UPDATE qc_rule_result SET confidence_score = 0.0 WHERE confidence_score IS NULL")

    # Alter columns to NOT NULL with server-side defaults so future inserts
    # that omit the field also receive the correct sentinel.
    with op.batch_alter_table("qc_rule_result") as batch_op:
        batch_op.alter_column(
            "pdf_page",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0",
        )
        batch_op.alter_column(
            "bbox_x",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.0",
        )
        batch_op.alter_column(
            "bbox_y",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.0",
        )
        batch_op.alter_column(
            "bbox_w",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.0",
        )
        batch_op.alter_column(
            "bbox_h",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.0",
        )
        batch_op.alter_column(
            "confidence_score",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.0",
        )


def downgrade() -> None:
    # Reverse the NOT NULL constraints back to nullable.
    with op.batch_alter_table("qc_rule_result") as batch_op:
        for col in ("pdf_page", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "confidence_score"):
            batch_op.alter_column(col, nullable=True, server_default=None)
