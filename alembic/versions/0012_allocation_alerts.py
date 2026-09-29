"""allocation_alerts: drift threshold to watch per symbol

New table only (issue #320). Unlike price_alerts, `triggered` auto-resets
when drift recovers - see scripts/check_allocation_alerts.py.

Revision ID: 0012_allocation_alerts
Revises: 0011_price_alerts
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_allocation_alerts"
down_revision = "0011_price_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allocation_alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("triggered_at", sa.DateTime()),
    )
    op.create_index("ix_allocation_alerts_user_id", "allocation_alerts", ["user_id"])
    op.create_index("ix_allocation_alerts_symbol", "allocation_alerts", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_allocation_alerts_symbol", table_name="allocation_alerts")
    op.drop_index("ix_allocation_alerts_user_id", table_name="allocation_alerts")
    op.drop_table("allocation_alerts")
