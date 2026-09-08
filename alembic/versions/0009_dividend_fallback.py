"""fundamentals_cache: add trailingAnnualDividendRate

yfinance's dividendRate (forward, per-payment x frequency) is often None
for ETFs even when they clearly pay dividends (e.g. VOO) - this is the
trailing-12-months actual total instead, used as a fallback when
dividendRate is missing. Nullable - existing cached rows just have it as
null until the next scheduled refresh.

Revision ID: 0009_dividend_fallback
Revises: 0008_fundamentals_quote
Create Date: 2026-09-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_dividend_fallback"
down_revision = "0008_fundamentals_quote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals_cache", sa.Column("trailingAnnualDividendRate", sa.Float()))


def downgrade() -> None:
    op.drop_column("fundamentals_cache", "trailingAnnualDividendRate")
