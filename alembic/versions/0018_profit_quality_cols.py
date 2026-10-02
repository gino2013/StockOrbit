"""Add profit-quality/growth/liveness columns to fundamentals_cache

Supports 千倍股篩選's獲利品質/成長來源 flags + ticker 存活檢查 (issue #366):
operatingMargins/netIncomeToCommon/totalRevenue/forwardEps/trailingEps/
regularMarketTime are all already returned by the same get_info() call
fundamentals_cache already makes, just not stored before now.

Revision ID: 0018_profit_quality_cols
Revises: 0017_screen_cache_rank
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_profit_quality_cols"
down_revision = "0017_screen_cache_rank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in ("operatingMargins", "netIncomeToCommon", "totalRevenue", "forwardEps", "trailingEps", "regularMarketTime"):
        op.add_column("fundamentals_cache", sa.Column(col, sa.Float()))


def downgrade() -> None:
    for col in ("operatingMargins", "netIncomeToCommon", "totalRevenue", "forwardEps", "trailingEps", "regularMarketTime"):
        op.drop_column("fundamentals_cache", col)
