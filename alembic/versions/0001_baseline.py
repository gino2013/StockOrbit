"""baseline - the single-user schema as it stood before multi-user work

On an existing database where these tables were created by
`Base.metadata.create_all`, run once:  alembic stamp 0001_baseline
On a fresh database, `alembic upgrade head` creates them.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_number", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False, index=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("cost_basis", sa.Float()),
        sa.Column("market_value", sa.Float()),
        sa.Column("price", sa.Float()),
        sa.Column("raw_json", sa.Text()),
        sa.Column("snapshot_at", sa.DateTime(), index=True),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_number", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), index=True),
        sa.Column("trans_type", sa.String(), nullable=False, index=True),
        sa.Column("report_date", sa.Date(), nullable=False, index=True),
        sa.Column("quantity", sa.Float()),
        sa.Column("trade_price", sa.Float()),
        sa.Column("amount", sa.Float()),
        sa.Column("description", sa.Text()),
        sa.Column("raw_json", sa.Text()),
        sa.Column("fetched_at", sa.DateTime()),
    )
    op.create_table(
        "target_allocations",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("target_weight", sa.Float(), nullable=False),
    )
    op.create_table(
        "exchange_rate_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("pair", sa.String(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), index=True),
    )
    op.create_table(
        "fundamentals_cache",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("quoteType", sa.String()),
        sa.Column("sector", sa.String()),
        sa.Column("industry", sa.String()),
        sa.Column("marketCap", sa.Float()),
        sa.Column("trailingPE", sa.Float()),
        sa.Column("forwardPE", sa.Float()),
        sa.Column("pegRatio", sa.Float()),
        sa.Column("returnOnEquity", sa.Float()),
        sa.Column("profitMargins", sa.Float()),
        sa.Column("revenueGrowth", sa.Float()),
        sa.Column("earningsGrowth", sa.Float()),
        sa.Column("debtToEquity", sa.Float()),
        sa.Column("beta", sa.Float()),
        sa.Column("fiftyTwoWeekLow", sa.Float()),
        sa.Column("fiftyTwoWeekHigh", sa.Float()),
        sa.Column("targetMeanPrice", sa.Float()),
        sa.Column("recommendationKey", sa.String()),
        sa.Column("next_earnings_date", sa.String()),
        sa.Column("fetched_at", sa.DateTime()),
    )
    op.create_table(
        "position_notes",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_table(
        "transaction_notes",
        sa.Column("transaction_id", sa.String(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_table(
        "investment_goals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )


def downgrade() -> None:
    for table in (
        "investment_goals",
        "transaction_notes",
        "position_notes",
        "fundamentals_cache",
        "exchange_rate_snapshots",
        "target_allocations",
        "transactions",
        "position_snapshots",
    ):
        op.drop_table(table)
