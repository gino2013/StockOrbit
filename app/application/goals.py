"""Goal-progress use case: current value + money-weighted return -> progress
toward the target. Pure orchestration; the route supplies the goal row and
the raw snapshot/transaction data."""

from datetime import date

from app.domain.analytics.monte_carlo import TRADING_DAYS_PER_YEAR, probability_of_reaching_target
from app.domain.analytics.portfolio_returns import weighted_portfolio_returns
from app.domain.analytics.xirr import estimate_annual_contribution, portfolio_cashflows, xirr
from app.domain.goals.goal_tracking import YEAR_END_BONUS_MONTH, build_goal_progress

_MAX_PROBABILITY_MONTHS = 600  # 50 years - matches goal_tracking's own long-horizon cap in spirit


def _months_until(target_date: date, as_of: date) -> int:
    days = (target_date - as_of).days
    return max(1, min(_MAX_PROBABILITY_MONTHS, round(days / (365.25 / 12))))


def _year_end_trading_days(amount: float, as_of: date, target_date: date) -> dict[int, float]:
    """{trading-day offset: amount} for each 年終 deposit (1st of
    YEAR_END_BONUS_MONTH) strictly after `as_of` and up to `target_date`."""
    lumps: dict[int, float] = {}
    if not amount:
        return lumps
    for year in range(as_of.year, target_date.year + 1):
        d = date(year, YEAR_END_BONUS_MONTH, 1)
        if as_of < d <= target_date:
            lumps[round((d - as_of).days / 365.25 * TRADING_DAYS_PER_YEAR)] = amount
    return lumps


def goal_progress(
    *, target_amount: float, target_date: date,
    snapshots: list[dict], transactions: list[dict], as_of: date,
    monthly_contribution: float | None = None, year_end_contribution: float | None = None,
) -> dict:
    current_value = sum(s["market_value"] for s in snapshots)
    current_return = xirr(portfolio_cashflows(transactions, current_value, as_of))
    # Either input filled in -> the investor's own plan replaces the
    # historical estimate (blank one counts as 0), so nothing double-counts.
    user_planned = monthly_contribution is not None or year_end_contribution is not None
    year_end = year_end_contribution or 0.0
    if user_planned:
        annual_contribution = (monthly_contribution or 0.0) * 12
    else:
        annual_contribution = estimate_annual_contribution(transactions, as_of)
    progress = build_goal_progress(
        current_value, target_amount, target_date, current_return, as_of, annual_contribution, year_end
    )
    progress["monthly_contribution"] = monthly_contribution
    progress["contribution_source"] = "manual" if user_planned else "estimated"

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
        lump_contributions=_year_end_trading_days(year_end, as_of, target_date),
    )
    return progress
