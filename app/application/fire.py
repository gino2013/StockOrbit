"""FIRE-progress use case: current value + money-weighted return -> distance
from the 4%-rule FIRE number. Pure orchestration, same shape as
application/goals.py."""

from datetime import date

from app.domain.analytics.xirr import portfolio_cashflows, xirr
from app.domain.goals.fire import build_fire_progress


def fire_progress(
    *, annual_expenses: float, swr: float,
    snapshots: list[dict], transactions: list[dict], as_of: date,
) -> dict:
    current_value = sum(s["market_value"] for s in snapshots)
    current_return = xirr(portfolio_cashflows(transactions, current_value, as_of))
    return build_fire_progress(current_value, annual_expenses, swr, current_return, as_of)
