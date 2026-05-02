"""Add hOCR and spatial word cache columns.

Revision ID: 2d7c8e9f0a1b
Revises: 9a7d4b1c2e3f
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "2d7c8e9f0a1b"
down_revision = "9a7d4b1c2e3f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("page_ocr_results", sa.Column("hocr_text", sa.Text(), nullable=True))
    op.add_column("page_ocr_results", sa.Column("word_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("page_ocr_results", "word_json")
    op.drop_column("page_ocr_results", "hocr_text")
