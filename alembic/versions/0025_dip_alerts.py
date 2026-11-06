"""dip_plans: alert_enabled + alert_level

大跌自動寄信（issue #441）：alert_enabled 開關（預設開），alert_level 是這一波
下跌已經通知到第幾階，回升後歸零。

Revision ID: 0025_dip_alerts
Revises: 0024_dip_plans
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_dip_alerts"
down_revision = "0024_dip_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A scheduled script's create_all may have built the table with these already.
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("dip_plans")}
    if "alert_enabled" not in cols:
        op.add_column("dip_plans", sa.Column("alert_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "alert_level" not in cols:
        op.add_column("dip_plans", sa.Column("alert_level", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("dip_plans", "alert_level")
    op.drop_column("dip_plans", "alert_enabled")
