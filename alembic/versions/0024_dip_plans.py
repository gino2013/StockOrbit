"""new dip_plans table

分批加碼計畫（issue #439）：一人一筆，tiers_json 存 [[跌幅門檻, 投入比例], ...]。

Revision ID: 0024_dip_plans
Revises: 0023_moonshot_evaluation
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_dip_plans"
down_revision = "0023_moonshot_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scheduled scripts call init_db() (create_all) and may get there first.
    if sa.inspect(op.get_bind()).has_table("dip_plans"):
        return
    op.create_table(
        "dip_plans",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("symbol", sa.String(), nullable=False, server_default="QQQ"),
        sa.Column("budget", sa.Float(), nullable=False),
        sa.Column("tiers_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("dip_plans")
