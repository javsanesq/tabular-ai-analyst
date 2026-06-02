"""add owner scoping

Revision ID: 20260602_0003
Revises: 20260601_0002
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260602_0003"
down_revision = "20260601_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("owner_hash", sa.String(length=64), nullable=False, server_default="legacy-demo"))
    op.add_column("analyses", sa.Column("owner_hash", sa.String(length=64), nullable=False, server_default="legacy-demo"))
    op.add_column("eval_runs", sa.Column("owner_hash", sa.String(length=64), nullable=False, server_default="legacy-demo"))
    op.create_index("ix_datasets_owner_hash", "datasets", ["owner_hash"])
    op.create_index("ix_analyses_owner_hash", "analyses", ["owner_hash"])
    op.create_index("ix_eval_runs_owner_hash", "eval_runs", ["owner_hash"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_owner_hash", table_name="eval_runs")
    op.drop_index("ix_analyses_owner_hash", table_name="analyses")
    op.drop_index("ix_datasets_owner_hash", table_name="datasets")
    op.drop_column("eval_runs", "owner_hash")
    op.drop_column("analyses", "owner_hash")
    op.drop_column("datasets", "owner_hash")
