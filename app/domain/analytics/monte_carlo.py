"""Monte Carlo projection via bootstrap resampling of historical daily
returns - answers "what's the plausible range of outcomes" instead of
pace_projection's single "if this exact rate holds" path. Resampling real
historical days (with replacement) rather than assuming a normal
distribution keeps fat-tail risk in the simulation instead of averaging it
away. Still not a forecast - a very small history sample gets resampled
over and over, so it inherits whatever bias/luck was in that window.
"""

import numpy as np

from app.domain.analytics.portfolio_returns import weighted_portfolio_returns

TRADING_DAYS_PER_YEAR = 252
_MIN_HISTORY_DAYS = 30


def _bootstrap_values(
    current_value: float, daily_returns: np.ndarray, total_days: int, n_simulations: int, seed: int,
    monthly_contribution: float = 0.0, days_per_month: float = TRADING_DAYS_PER_YEAR / 12,
    lump_contributions: dict[int, float] | None = None,
) -> np.ndarray | None:
    """(n_simulations, total_days) matrix of simulated portfolio values,
    each day independently bootstrap-resampled (with replacement) from
    `daily_returns`. None when there's too little history to resample
    from - shared by simulate_paths() and probability_of_reaching_target()
    so both draw from the exact same resampling mechanics.

    `monthly_contribution`, when set, lands at each month-boundary day
    before that day's growth is applied - the same "lump sum now, deposits
    arriving on schedule" shape as goal_tracking._value_after_months, just
    simulated path-by-path instead of one deterministic rate. That
    interaction (a deposit compounds along with the rest afterward) is why
    this can't stay a single vectorized cumprod once contributions are
    involved - it becomes a day-by-day recurrence.
    """
    daily_returns = np.asarray(daily_returns, dtype=float)
    if current_value <= 0 or total_days <= 0 or len(daily_returns) < _MIN_HISTORY_DAYS:
        return None

    rng = np.random.default_rng(seed)
    sampled = rng.choice(daily_returns, size=(n_simulations, total_days), replace=True)

    lumps = lump_contributions or {}
    if not monthly_contribution and not lumps:
        return current_value * np.cumprod(1 + sampled, axis=1)

    total_months = int(total_days / days_per_month) + 2
    month_boundary_days = {round(m * days_per_month) for m in range(1, total_months)}
    values = np.full(n_simulations, current_value, dtype=float)
    path = np.empty((n_simulations, total_days), dtype=float)
    for d in range(total_days):
        if d in month_boundary_days:
            values = values + monthly_contribution
        values = values + lumps.get(d, 0.0)
        values = values * (1 + sampled[:, d])
        path[:, d] = values
    return path


def simulate_paths(
    current_value: float, daily_returns, months: int, n_simulations: int = 1000, seed: int = 42
) -> dict:
    """Bootstrap `n_simulations` paths `months` months forward. Returns the
    10th/50th/90th percentile portfolio value at each month-end checkpoint
    (month 1..months) - empty lists (not a crash) when there's too little
    history or nothing to project from."""
    if current_value <= 0 or months <= 0:
        return {"months": [], "p10": [], "p50": [], "p90": []}

    days_per_month = TRADING_DAYS_PER_YEAR / 12
    total_days = round(months * days_per_month)
    values = _bootstrap_values(current_value, daily_returns, total_days, n_simulations, seed)
    if values is None:
        return {"months": [], "p10": [], "p50": [], "p90": []}

    checkpoint_days = sorted({min(total_days, round(m * days_per_month)) for m in range(1, months + 1)})
    p10 = [float(np.percentile(values[:, d - 1], 10)) for d in checkpoint_days]
    p50 = [float(np.percentile(values[:, d - 1], 50)) for d in checkpoint_days]
    p90 = [float(np.percentile(values[:, d - 1], 90)) for d in checkpoint_days]

    return {"months": list(range(1, len(checkpoint_days) + 1)), "p10": p10, "p50": p50, "p90": p90}


def probability_of_reaching_target(
    current_value: float, daily_returns, target_amount: float, months: int,
    n_simulations: int = 1000, seed: int = 42, monthly_contribution: float = 0.0,
    lump_contributions: dict[int, float] | None = None,
) -> float | None:
    """Fraction of bootstrap-simulated paths whose value at `months` months
    out is >= target_amount - "given how bumpy your actual historical
    returns have been (and how much you've kept adding), what are the odds
    you're at the target by then", instead of goal_tracking's single
    point-estimate pace projection. `lump_contributions` maps a trading-day
    offset to a one-off deposit (e.g. 年終投入). None when there's too little history
    to simulate from."""
    if current_value <= 0 or months <= 0 or target_amount <= 0:
        return None

    days_per_month = TRADING_DAYS_PER_YEAR / 12
    total_days = round(months * days_per_month)
    values = _bootstrap_values(
        current_value, daily_returns, total_days, n_simulations, seed, monthly_contribution, days_per_month,
        lump_contributions,
    )
    if values is None:
        return None

    return float(np.mean(values[:, -1] >= target_amount))


def build_monte_carlo_projection(
    symbols: list[str], weights: dict[str, float], current_value: float,
    months: int = 12, n_simulations: int = 1000, seed: int = 42,
) -> dict:
    returns = weighted_portfolio_returns(symbols, weights)
    return simulate_paths(current_value, returns.to_numpy(), months, n_simulations, seed)
