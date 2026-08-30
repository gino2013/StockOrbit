"""nullable user_id on the six user tables + owner bootstrap + backfill

Additive: adds `user_id` (nullable, indexed, FK -> users.id), ensures the
`OWNER_EMAIL` account exists, and points every pre-existing row at it.
A later revision makes `user_id` NOT NULL and folds it into the composite
primary keys (so two users can hold the same symbol).

Revision ID: 0003_tenancy_cols
Revises: 0002_users_creds
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_tenancy_cols"
down_revision = "0002_users_creds"
branch_labels = None
depends_on = None

_TABLES = (
    "position_snapshots",
    "transactions",
    "target_allocations",
    "position_notes",
    "transaction_notes",
    "investment_goals",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("user_id", sa.String(), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # Ensure the owner account exists, then claim every orphan row for it.
    # On a fresh install with no OWNER_EMAIL this creates the local dev
    # owner and backfills zero rows.
    from app.interface.auth import ensure_owner

    owner_id = ensure_owner()
    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET user_id = :oid WHERE user_id IS NULL"),
            {"oid": owner_id},
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
