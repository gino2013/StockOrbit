"""Goal-progress use case: current value + money-weighted return -> progress
toward the target. Pure orchestration; the route supplies the goal row and
the raw snapshot/transaction data."""

from datetime import date

from app.domain.analytics.xirr import portfolio_cashflows, xirr
from app.domain.goals.goal_tracking import build_goal_progress


def goal_progress(
    *, target_amount: float, target_date: date,
    snapshots: list[dict], transactions: list[dict], as_of: date,
) -> dict:
    current_value = sum(s["market_value"] for s in snapshots)
    current_return = xirr(portfolio_cashflows(transactions, current_value, as_of))
    return build_goal_progress(current_value, target_amount, target_date, current_return, as_of)
