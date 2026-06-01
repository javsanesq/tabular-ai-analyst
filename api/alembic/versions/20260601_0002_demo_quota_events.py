"""add demo quota events

Revision ID: 20260601_0002
Revises: 20260601_0001
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260601_0002"
down_revision = "20260601_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_quota_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_demo_quota_events_identity_hash", "demo_quota_events", ["identity_hash"])
    op.create_index("ix_demo_quota_events_created_at", "demo_quota_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_demo_quota_events_created_at", table_name="demo_quota_events")
    op.drop_index("ix_demo_quota_events_identity_hash", table_name="demo_quota_events")
    op.drop_table("demo_quota_events")
