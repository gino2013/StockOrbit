"""target_allocations: sort_order for drag-to-reorder (issue #336)

Additive column, backfilled per-user from the existing (alphabetical, since
there was no stored order before this) row set so drag-reorder starts from
something stable instead of NULLs/all-zero.

Revision ID: 0014_target_sort_order
Revises: 0013_liabilities
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_target_sort_order"
down_revision = "0013_liabilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "target_allocations",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT user_id, symbol FROM target_allocations ORDER BY user_id, symbol")
    ).fetchall()
    next_order: dict[str, int] = {}
    for user_id, symbol in rows:
        idx = next_order.get(user_id, 0)
        conn.execute(
            sa.text(
                "UPDATE target_allocations SET sort_order = :o WHERE user_id = :u AND symbol = :s"
            ),
            {"o": idx, "u": user_id, "s": symbol},
        )
        next_order[user_id] = idx + 1


def downgrade() -> None:
    op.drop_column("target_allocations", "sort_order")
