"""Add auto_pass_examples table for P3.5 ML calibration.

This table accumulates reviewer acceptance/rejection labels for each rule
result so the auto-pass calibration model can learn when rules can be
trusted to pass without human review.

The model uses these examples to train a LogisticRegression / RandomForest
pipeline.  Until MIN_EXAMPLES_TO_TRAIN (30) examples exist, the engine
falls back to its tiered confidence thresholds — no behaviour change.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auto_pass_examples",
        sa.Column("id",                  sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("rule_id",             sa.String(20),   nullable=False),
        sa.Column("rule_family",         sa.String(10),   nullable=False),
        sa.Column("extraction_method",   sa.String(50)),
        sa.Column("confidence",          sa.Float()),
        sa.Column("has_source_page",     sa.Boolean(),    server_default="false"),
        sa.Column("has_bbox",            sa.Boolean(),    server_default="false"),
        sa.Column("has_compared_values", sa.Boolean(),    server_default="false"),
        sa.Column("has_extracted_value", sa.Boolean(),    server_default="false"),
        sa.Column("loan_type",           sa.String(20)),
        sa.Column("is_presence_rule",    sa.Boolean(),    server_default="false"),
        sa.Column("is_extraction_rule",  sa.Boolean(),    server_default="false"),
        sa.Column("reviewer_accepted",   sa.Boolean(),    nullable=False),
        sa.Column("document_id",         sa.String(100)),
        sa.Column("reviewer_comment",    sa.Text()),
        sa.Column("used_in_training",    sa.Boolean(),    server_default="false"),
        sa.Column("training_version",    sa.Integer(),    server_default="0"),
        sa.Column("created_at",          sa.DateTime(),   server_default=sa.text("NOW()")),
    )
    op.create_index("ix_auto_pass_rule_id",       "auto_pass_examples", ["rule_id"])
    op.create_index("ix_auto_pass_not_trained",   "auto_pass_examples", ["used_in_training"])
    op.create_index("ix_auto_pass_family_method", "auto_pass_examples", ["rule_family", "extraction_method"])


def downgrade() -> None:
    op.drop_index("ix_auto_pass_family_method", table_name="auto_pass_examples")
    op.drop_index("ix_auto_pass_not_trained",   table_name="auto_pass_examples")
    op.drop_index("ix_auto_pass_rule_id",        table_name="auto_pass_examples")
    op.drop_table("auto_pass_examples")
