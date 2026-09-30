"""liabilities: fixed-payment loans (e.g. 信貸) used to fund investing

New table only (issue #326). Remaining balance is derived on read via
app/domain/liabilities/amortization.py, not stored.

Revision ID: 0013_liabilities
Revises: 0012_allocation_alerts
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_liabilities"
down_revision = "0012_allocation_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "liabilities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("principal", sa.Float(), nullable=False),
        sa.Column("annual_rate", sa.Float(), nullable=False),
        sa.Column("monthly_payment", sa.Float(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_liabilities_user_id", "liabilities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_liabilities_user_id", table_name="liabilities")
    op.drop_table("liabilities")
