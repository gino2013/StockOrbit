"""new moonshot_evaluation table

千倍股評估（issue #408）：每次評估一筆，不覆蓋。

Revision ID: 0023_moonshot_evaluation
Revises: 0022_liability_term
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_moonshot_evaluation"
down_revision = "0022_liability_term"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The scheduled scripts (and scripts/moonshot_eval.py) call init_db() -
    # create_all - against the same DB, and may run with this code before
    # the deploy that applies this migration; then the table is already there.
    if sa.inspect(op.get_bind()).has_table("moonshot_evaluation"):
        return
    op.create_table(
        "moonshot_evaluation",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_moonshot_evaluation_symbol", "moonshot_evaluation", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_moonshot_evaluation_symbol", table_name="moonshot_evaluation")
    op.drop_table("moonshot_evaluation")
