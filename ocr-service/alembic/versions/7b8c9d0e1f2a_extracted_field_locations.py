"""Add extracted field bbox columns.

Revision ID: 7b8c9d0e1f2a
Revises: 2d7c8e9f0a1b
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "7b8c9d0e1f2a"
down_revision = "2d7c8e9f0a1b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("extracted_fields", sa.Column("bbox_x", sa.Float(), nullable=True))
    op.add_column("extracted_fields", sa.Column("bbox_y", sa.Float(), nullable=True))
    op.add_column("extracted_fields", sa.Column("bbox_w", sa.Float(), nullable=True))
    op.add_column("extracted_fields", sa.Column("bbox_h", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("extracted_fields", "bbox_h")
    op.drop_column("extracted_fields", "bbox_w")
    op.drop_column("extracted_fields", "bbox_y")
    op.drop_column("extracted_fields", "bbox_x")
