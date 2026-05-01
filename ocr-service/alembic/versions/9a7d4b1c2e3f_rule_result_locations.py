"""rule_result_locations

Revision ID: 9a7d4b1c2e3f
Revises: c13dab69bd6c
Create Date: 2026-05-01 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a7d4b1c2e3f"
down_revision: Union[str, Sequence[str], None] = "c13dab69bd6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("rule_results", sa.Column("source_page", sa.Integer(), nullable=True))
    op.add_column("rule_results", sa.Column("bbox_x", sa.Float(), nullable=True))
    op.add_column("rule_results", sa.Column("bbox_y", sa.Float(), nullable=True))
    op.add_column("rule_results", sa.Column("bbox_w", sa.Float(), nullable=True))
    op.add_column("rule_results", sa.Column("bbox_h", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("rule_results", "bbox_h")
    op.drop_column("rule_results", "bbox_w")
    op.drop_column("rule_results", "bbox_y")
    op.drop_column("rule_results", "bbox_x")
    op.drop_column("rule_results", "source_page")
