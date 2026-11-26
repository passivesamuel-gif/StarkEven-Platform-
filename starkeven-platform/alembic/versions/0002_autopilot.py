"""lead autopilot campaigns and delivered leads

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "autopilot_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("active", "paused", name="campaign_status", native_enum=False), nullable=False),
        sa.Column("target_keywords", sa.JSON(), nullable=False),
        sa.Column("required_tech_stack", sa.JSON(), nullable=False),
        sa.Column("require_hiring", sa.Boolean(), nullable=False),
        sa.Column("daily_lead_quota", sa.Integer(), nullable=False),
        sa.Column("target_crm_provider", sa.String(50), nullable=False),
        sa.Column("target_crm_url_or_token", sa.String(512), nullable=True),
        sa.Column("total_leads_delivered", sa.Integer(), nullable=False),
        sa.Column("last_run_at", TZ, nullable=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_autopilot_campaigns_org_id", "autopilot_campaigns", ["org_id"])

    op.create_table(
        "delivered_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("autopilot_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("tech_stack", sa.JSON(), nullable=False),
        sa.Column("email_provider", sa.String(100), nullable=True),
        sa.Column("verified_emails", sa.JSON(), nullable=False),
        sa.Column("hiring_ats", sa.JSON(), nullable=False),
        sa.Column("delivered_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "domain", name="uq_org_delivered_domain"),
    )
    op.create_index("ix_delivered_leads_campaign_id", "delivered_leads", ["campaign_id"])
    op.create_index("ix_delivered_leads_org_id", "delivered_leads", ["org_id"])
    op.create_index("ix_delivered_leads_domain", "delivered_leads", ["domain"])


def downgrade() -> None:
    op.drop_table("delivered_leads")
    op.drop_table("autopilot_campaigns")
