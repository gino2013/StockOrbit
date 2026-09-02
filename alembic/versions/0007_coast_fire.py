"""fire_settings: add optional Coast FIRE inputs

retirement_date/expected_real_return are nullable - existing rows (FIRE
progress already configured, Coast FIRE not) are untouched; both null
means "Coast FIRE not set up yet".

Revision ID: 0007_coast_fire
Revises: 0006_fire_settings
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_coast_fire"
down_revision = "0006_fire_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fire_settings", sa.Column("retirement_date", sa.Date()))
    op.add_column("fire_settings", sa.Column("expected_real_return", sa.Float()))


def downgrade() -> None:
    op.drop_column("fire_settings", "expected_real_return")
    op.drop_column("fire_settings", "retirement_date")
