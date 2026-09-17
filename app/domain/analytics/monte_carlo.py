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


def simulate_paths(
    current_value: float, daily_returns, months: int, n_simulations: int = 1000, seed: int = 42
) -> dict:
    """Bootstrap `n_simulations` paths `months` months forward, each
    simulated day resampled independently (with replacement) from the
    historical `daily_returns`. Returns the 10th/50th/90th percentile
    portfolio value at each month-end checkpoint (month 1..months) -
    empty lists (not a crash) when there's too little history or nothing to
    project from."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    if current_value <= 0 or months <= 0 or len(daily_returns) < _MIN_HISTORY_DAYS:
        return {"months": [], "p10": [], "p50": [], "p90": []}

    rng = np.random.default_rng(seed)
    days_per_month = TRADING_DAYS_PER_YEAR / 12
    total_days = round(months * days_per_month)

    sampled = rng.choice(daily_returns, size=(n_simulations, total_days), replace=True)
    cum_growth = np.cumprod(1 + sampled, axis=1)  # shape: (n_simulations, total_days)
    values = current_value * cum_growth

    checkpoint_days = sorted({min(total_days, round(m * days_per_month)) for m in range(1, months + 1)})
    p10 = [float(np.percentile(values[:, d - 1], 10)) for d in checkpoint_days]
    p50 = [float(np.percentile(values[:, d - 1], 50)) for d in checkpoint_days]
    p90 = [float(np.percentile(values[:, d - 1], 90)) for d in checkpoint_days]

    return {"months": list(range(1, len(checkpoint_days) + 1)), "p10": p10, "p50": p50, "p90": p90}


def build_monte_carlo_projection(
    symbols: list[str], weights: dict[str, float], current_value: float,
    months: int = 12, n_simulations: int = 1000, seed: int = 42,
) -> dict:
    returns = weighted_portfolio_returns(symbols, weights)
    return simulate_paths(current_value, returns.to_numpy(), months, n_simulations, seed)
