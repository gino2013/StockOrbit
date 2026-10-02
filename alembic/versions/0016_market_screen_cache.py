"""New moonshot_market_screen_cache table

Supports falling back to a scheduled result when the live 全市場搜尋
(issue #356) can't reach Yahoo's screener from Render (issue #360) - same
401-Invalid-Crumb limitation as FundamentalsCache, see that model's
docstring. Not user-scoped; wholesale-replaced on every scheduled refresh.

Revision ID: 0016_market_screen_cache
Revises: 0015_moonshot_screen
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_market_screen_cache"
down_revision = "0015_moonshot_screen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moonshot_market_screen_cache",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("criteria_json", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("moonshot_market_screen_cache")
