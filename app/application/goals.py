"""Goal-progress use case: current value + money-weighted return -> progress
toward the target. Pure orchestration; the route supplies the goal row and
the raw snapshot/transaction data."""

from datetime import date

from app.domain.analytics.monte_carlo import probability_of_reaching_target
from app.domain.analytics.portfolio_returns import weighted_portfolio_returns
from app.domain.analytics.xirr import estimate_annual_contribution, portfolio_cashflows, xirr
from app.domain.goals.goal_tracking import build_goal_progress

_MAX_PROBABILITY_MONTHS = 600  # 50 years - matches goal_tracking's own long-horizon cap in spirit


def _months_until(target_date: date, as_of: date) -> int:
    days = (target_date - as_of).days
    return max(1, min(_MAX_PROBABILITY_MONTHS, round(days / (365.25 / 12))))


def goal_progress(
    *, target_amount: float, target_date: date,
    snapshots: list[dict], transactions: list[dict], as_of: date,
) -> dict:
    current_value = sum(s["market_value"] for s in snapshots)
    current_return = xirr(portfolio_cashflows(transactions, current_value, as_of))
    annual_contribution = estimate_annual_contribution(transactions, as_of)
    progress = build_goal_progress(
        current_value, target_amount, target_date, current_return, as_of, annual_contribution
    )

    # Bootstrap-simulated probability of hitting the target by the deadline
    # (issue #318) - a distribution instead of build_goal_progress's single
    # "on track or not" point estimate. Reuses the same weighted-returns
    # helper the Monte Carlo projection section already relies on.
    value_by_symbol: dict[str, float] = {}
    for s in snapshots:
        if s["symbol"] != "CASH":
            value_by_symbol[s["symbol"]] = value_by_symbol.get(s["symbol"], 0.0) + s["market_value"]
    symbols = list(value_by_symbol)
    weights = {s: v / current_value for s, v in value_by_symbol.items()} if current_value else {}
    daily_returns = weighted_portfolio_returns(symbols, weights).to_numpy() if symbols else []
    progress["monte_carlo_probability"] = probability_of_reaching_target(
        current_value, daily_returns, target_amount, _months_until(target_date, as_of),
        monthly_contribution=annual_contribution / 12,
    )
    return progress
