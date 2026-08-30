"""users + firstrade_credentials (multi-user step 1)

Additive only - the user_id columns on the existing tables and the owner
backfill come in a later revision.

Revision ID: 0002_users_creds
Revises: 0001_baseline
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_users_creds"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "firstrade_credentials",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("username_enc", sa.Text(), nullable=False),
        sa.Column("password_enc", sa.Text(), nullable=False),
        sa.Column("mfa_secret_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_sync_at", sa.DateTime()),
        sa.Column("last_sync_error", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("firstrade_credentials")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
