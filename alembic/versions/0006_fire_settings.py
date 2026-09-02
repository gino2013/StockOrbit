"""fire_settings: FIRE (financial independence) inputs, one row per user

Same shape as investment_goals - user_id is the primary key directly, no
history kept. swr is the safe withdrawal rate (0.04 = the 4% rule); the
FIRE number is annual_expenses / swr, computed on read, not stored.

Revision ID: 0006_fire_settings
Revises: 0005_note_history
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_fire_settings"
down_revision = "0005_note_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_settings",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("annual_expenses", sa.Float(), nullable=False),
        sa.Column("swr", sa.Float(), nullable=False, server_default="0.04"),
        sa.Column("updated_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("fire_settings")
