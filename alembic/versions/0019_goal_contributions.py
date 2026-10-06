"""investment_goals: add optional monthly/year-end contribution inputs

Goal tracking lets the user enter a 定期定額 (monthly) and 年終投入
(once a year, February) amount instead of relying on the contribution
estimated from past deposits (issue #372). NULL = not entered.

Revision ID: 0019_goal_contributions
Revises: 0018_profit_quality_cols
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_goal_contributions"
down_revision = "0018_profit_quality_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investment_goals", sa.Column("monthly_contribution", sa.Float()))
    op.add_column("investment_goals", sa.Column("year_end_contribution", sa.Float()))


def downgrade() -> None:
    op.drop_column("investment_goals", "year_end_contribution")
    op.drop_column("investment_goals", "monthly_contribution")
