"""Add rank column to moonshot_market_screen_cache

Fixes the "依市值排序" claim that wasn't true (issue #364): the cache read
path was re-sorting by symbol on score ties, discarding the market-cap
order the screener itself returned. This column records insertion order
at write time so reads can preserve it instead of falling back to symbol.

Revision ID: 0017_screen_cache_rank
Revises: 0016_market_screen_cache
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_screen_cache_rank"
down_revision = "0016_market_screen_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "moonshot_market_screen_cache",
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("moonshot_market_screen_cache", "rank")
