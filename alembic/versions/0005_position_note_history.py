"""position_note_history: append-only log of every position-note save

New table only - position_notes itself is unchanged (still holds just the
current text). Every future upsert_note() call also inserts a row here,
so past versions stay visible instead of being silently overwritten.

Revision ID: 0005_note_history
Revises: 0004_tenancy_pks
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_note_history"
down_revision = "0004_tenancy_pks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_note_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("saved_at", sa.DateTime()),
    )
    op.create_index("ix_position_note_history_user_id", "position_note_history", ["user_id"])
    op.create_index("ix_position_note_history_symbol", "position_note_history", ["symbol"])
    op.create_index("ix_position_note_history_saved_at", "position_note_history", ["saved_at"])


def downgrade() -> None:
    op.drop_index("ix_position_note_history_saved_at", table_name="position_note_history")
    op.drop_index("ix_position_note_history_symbol", table_name="position_note_history")
    op.drop_index("ix_position_note_history_user_id", table_name="position_note_history")
    op.drop_table("position_note_history")
