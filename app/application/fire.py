"""FIRE-progress use case: current value + money-weighted return -> distance
from the 4%-rule FIRE number. Pure orchestration, same shape as
application/goals.py."""

from datetime import date

from app.domain.analytics.xirr import portfolio_cashflows, xirr
from app.domain.goals.fire import build_fire_progress
from app.domain.income.dividends import trailing_twelve_month_dividends


def fire_progress(
    *, annual_expenses: float, swr: float,
    snapshots: list[dict], transactions: list[dict], as_of: date,
    retirement_date: date | None = None, expected_real_return: float | None = None,
) -> dict:
    current_value = sum(s["market_value"] for s in snapshots)
    current_return = xirr(portfolio_cashflows(transactions, current_value, as_of))
    ttm_dividends = sum(row["ttm_dividends"] for row in trailing_twelve_month_dividends(transactions, as_of))
    return build_fire_progress(
        current_value, annual_expenses, swr, current_return, as_of,
        retirement_date=retirement_date, expected_real_return=expected_real_return,
        ttm_dividends=ttm_dividends,
    )
