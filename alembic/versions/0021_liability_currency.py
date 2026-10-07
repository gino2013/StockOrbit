"""liabilities: add currency (USD/TWD)

TWD loans are stored in NT$ and converted at the current USD/TWD rate on
read (issue #382). Existing rows were entered or converted to USD, so they
default to USD.

Revision ID: 0021_liability_currency
Revises: 0020_dedupe_settled_trades
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_liability_currency"
down_revision = "0020_dedupe_settled_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("liabilities", sa.Column("currency", sa.String(), nullable=False, server_default="USD"))


def downgrade() -> None:
    op.drop_column("liabilities", "currency")
