"""fundamentals_cache: add totalAssets/longName/exchange/currency/dividendRate

These back the individual-stock-lookup page's quote card: totalAssets is
the AUM equivalent for ETFs (which have no marketCap), the rest are the
company-identity/dividend fields that page needs but the portfolio-wide
fundamentals section never did. All nullable - existing cached rows just
have them as null until the next scheduled refresh.

Revision ID: 0008_fundamentals_cache_quote_fields
Revises: 0007_coast_fire
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_fundamentals_cache_quote_fields"
down_revision = "0007_coast_fire"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals_cache", sa.Column("totalAssets", sa.Float()))
    op.add_column("fundamentals_cache", sa.Column("longName", sa.String()))
    op.add_column("fundamentals_cache", sa.Column("exchange", sa.String()))
    op.add_column("fundamentals_cache", sa.Column("currency", sa.String()))
    op.add_column("fundamentals_cache", sa.Column("dividendRate", sa.Float()))


def downgrade() -> None:
    op.drop_column("fundamentals_cache", "dividendRate")
    op.drop_column("fundamentals_cache", "currency")
    op.drop_column("fundamentals_cache", "exchange")
    op.drop_column("fundamentals_cache", "longName")
    op.drop_column("fundamentals_cache", "totalAssets")
