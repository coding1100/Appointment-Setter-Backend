"""add sms_integrations table (dedicated Twilio creds for the SMS app)

Revision ID: 20260630_0004
Revises: 20260630_0003
Create Date: 2026-06-30 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260630_0004"
down_revision = "20260630_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_integrations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_integrations_tenant_id", "sms_integrations", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sms_integrations_tenant_id", table_name="sms_integrations")
    op.drop_table("sms_integrations")
