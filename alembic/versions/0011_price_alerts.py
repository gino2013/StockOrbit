"""price_alerts: target price + direction to watch per symbol

New table only (issue #18). checked/emailed by scripts/check_price_alerts.py.

Revision ID: 0011_price_alerts
Revises: 0010_price_to_book
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_price_alerts"
down_revision = "0010_price_to_book"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("triggered_at", sa.DateTime()),
    )
    op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
    op.create_index("ix_price_alerts_symbol", "price_alerts", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_price_alerts_symbol", table_name="price_alerts")
    op.drop_index("ix_price_alerts_user_id", table_name="price_alerts")
    op.drop_table("price_alerts")
