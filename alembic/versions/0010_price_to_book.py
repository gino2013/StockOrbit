"""fundamentals_cache: add priceToBook

Needed by the style box (issue #298) to classify a stock as value/growth
when trailingPE is missing or negative. Nullable - existing cached rows
just have it as null until the next scheduled refresh.

Revision ID: 0010_price_to_book
Revises: 0009_dividend_fallback
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_price_to_book"
down_revision = "0009_dividend_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fundamentals_cache", sa.Column("priceToBook", sa.Float()))


def downgrade() -> None:
    op.drop_column("fundamentals_cache", "priceToBook")
