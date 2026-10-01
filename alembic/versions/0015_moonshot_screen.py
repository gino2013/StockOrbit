"""fundamentals_cache: add grossMargins; new watchlist_symbols table

Supports the 千金股 (moonshot stock) screener (issue #348): grossMargins
is the Novy-Marx gross-profitability metric used by the screen's
profitability criterion. watchlist_symbols is the app-local 自選股
list - deliberately separate from Firstrade's own watchlists, which are
read-only and fetched live, not cached.

Revision ID: 0015_moonshot_screen
Revises: 0014_target_sort_order
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_moonshot_screen"
down_revision = "0014_target_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals_cache", sa.Column("grossMargins", sa.Float()))
    op.create_table(
        "watchlist_symbols",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("added_at", sa.DateTime()),
    )
    op.create_index("ix_watchlist_symbols_user_id", "watchlist_symbols", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_symbols_user_id", table_name="watchlist_symbols")
    op.drop_table("watchlist_symbols")
    op.drop_column("fundamentals_cache", "grossMargins")
