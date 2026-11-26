"""add notification preferences to organizations

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("notify_low_credits", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "organizations",
        sa.Column("notify_campaign_reports", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("organizations", "notify_campaign_reports")
    op.drop_column("organizations", "notify_low_credits")
