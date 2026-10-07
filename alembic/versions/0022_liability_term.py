"""liabilities: add term_months

Loan length as entered (issue #388); NULL = derive from the payment.

Revision ID: 0022_liability_term
Revises: 0021_liability_currency
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_liability_term"
down_revision = "0021_liability_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("liabilities", sa.Column("term_months", sa.Integer()))


def downgrade() -> None:
    op.drop_column("liabilities", "term_months")
