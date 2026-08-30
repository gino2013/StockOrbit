"""tighten tenancy: user_id NOT NULL + fold into composite primary keys

`position_snapshots.user_id` becomes NOT NULL (its own `id` stays the sole
PK - each snapshot row is already independently unique). The other five
tenancy tables get `user_id` folded into their primary key, so two users
can hold a row with the same natural key (e.g. the same target symbol)
without colliding:

  target_allocations  symbol            -> (user_id, symbol)
  position_notes      symbol            -> (user_id, symbol)
  transaction_notes   transaction_id    -> (user_id, transaction_id)
  transactions        id                -> (user_id, id)
  investment_goals    id ("default")    -> user_id alone (id column dropped)

Re-backfills any leftover NULL user_id to the owner first (belt-and-
suspenders - migration 0003 already did this for every row that existed
at the time).

Revision ID: 0004_tenancy_pks
Revises: 0003_tenancy_cols
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_tenancy_pks"
down_revision = "0003_tenancy_cols"
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

# table -> (new primary-key columns, in order)
_NEW_PK = {
    "transactions": ["user_id", "id"],
    "target_allocations": ["user_id", "symbol"],
    "position_notes": ["user_id", "symbol"],
    "transaction_notes": ["user_id", "transaction_id"],
    "investment_goals": ["user_id"],
}


def upgrade() -> None:
    conn = op.get_bind()

    from app.interface.auth import ensure_owner

    owner_id = ensure_owner()
    for table in _TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET user_id = :oid WHERE user_id IS NULL"),
            {"oid": owner_id},
        )

    if conn.dialect.name == "sqlite":
        # render_as_batch (see alembic/env.py) recreates the whole table
        # under the hood - no need to know/drop the old PK constraint name.
        with op.batch_alter_table("position_snapshots") as b:
            b.alter_column("user_id", nullable=False)
        for table, pk_cols in _NEW_PK.items():
            with op.batch_alter_table(table, recreate="always") as b:
                b.alter_column("user_id", nullable=False)
                if table == "investment_goals":
                    b.drop_column("id")
                b.create_primary_key(f"pk_{table}", pk_cols)
    else:
        inspector = sa.inspect(conn)
        op.alter_column("position_snapshots", "user_id", nullable=False)
        for table, pk_cols in _NEW_PK.items():
            op.alter_column(table, "user_id", nullable=False)
            old_pk = inspector.get_pk_constraint(table)["name"]
            if old_pk:
                op.drop_constraint(old_pk, table, type_="primary")
            if table == "investment_goals":
                op.drop_column(table, "id")
            op.create_primary_key(f"pk_{table}", table, pk_cols)


def downgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name == "sqlite":
        with op.batch_alter_table("position_snapshots") as b:
            b.alter_column("user_id", nullable=True)
        for table in _NEW_PK:
            single_col = "symbol" if table in ("target_allocations", "position_notes") else (
                "transaction_id" if table == "transaction_notes" else "id"
            )
            with op.batch_alter_table(table, recreate="always") as b:
                if table == "investment_goals":
                    b.add_column(sa.Column("id", sa.String(), nullable=True))
                b.alter_column("user_id", nullable=True)
                b.create_primary_key(f"pk_{table}", ["id" if table == "investment_goals" else single_col])
    else:
        inspector = sa.inspect(conn)
        op.alter_column("position_snapshots", "user_id", nullable=True)
        for table in _NEW_PK:
            single_col = "symbol" if table in ("target_allocations", "position_notes") else (
                "transaction_id" if table == "transaction_notes" else "id"
            )
            old_pk = inspector.get_pk_constraint(table)["name"]
            if old_pk:
                op.drop_constraint(old_pk, table, type_="primary")
            if table == "investment_goals":
                op.add_column(table, sa.Column("id", sa.String(), nullable=True))
                op.create_primary_key(f"pk_{table}", table, ["id"])
            else:
                op.create_primary_key(f"pk_{table}", table, [single_col])
            op.alter_column(table, "user_id", nullable=True)
