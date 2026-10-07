"""transactions: drop same-day/settled duplicate trade rows

Firstrade returned the same fill twice under different content hashes (see
Repositories.trade_already_recorded, issue #376), double-counting realized
gains. Keep the earliest-fetched row per (user, account, date, side, symbol,
quantity, trade_price) and delete the rest. Rows with notes keep the note's
original transaction_id only if that row is the one kept.

Revision ID: 0020_dedupe_settled_trades
Revises: 0019_goal_contributions
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_dedupe_settled_trades"
down_revision = "0019_goal_contributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT user_id, id, account_number, report_date, trans_type, symbol, quantity, trade_price "
        "FROM transactions WHERE trans_type IN ('BOUGHT', 'SOLD') ORDER BY fetched_at, id"
    )).fetchall()
    seen: set[tuple] = set()
    for user_id, tid, *key in rows:
        k = (user_id, *key)
        if k in seen:
            conn.execute(
                sa.text("DELETE FROM transactions WHERE user_id = :u AND id = :i"), {"u": user_id, "i": tid}
            )
        else:
            seen.add(k)


def downgrade() -> None:
    pass  # deleted duplicates aren't recoverable, and weren't wanted
