"""add is_verified to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("users", "is_verified", server_default=sa.false())


def downgrade() -> None:
    op.drop_column("users", "is_verified")
