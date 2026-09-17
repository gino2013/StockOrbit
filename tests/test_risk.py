import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics import risk
from app.domain.analytics.risk import (
    TRADING_DAYS_PER_YEAR,
    annualized_volatility,
    beta_vs_benchmark,
    calmar_ratio,
    downside_deviation,
    fetch_next_earnings_date,
    sharpe_ratio,
    sortino_ratio,
)


def demo():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02, 0.01, 0.0, -0.015, 0.03])
    vol = annualized_volatility(returns, window=8)
    assert abs(vol - returns.std() * TRADING_DAYS_PER_YEAR**0.5) < 1e-9

    # not enough data points in the window -> no reading rather than a bogus one.
    assert annualized_volatility(returns.head(1), window=8) is None

    # a benchmark scaled by exactly 2x has beta == 2.0 against it.
    benchmark_returns = pd.Series([0.01, -0.02, 0.005, 0.03, -0.01] * 8)
    symbol_returns = benchmark_returns * 2
    beta = beta_vs_benchmark(symbol_returns, benchmark_returns)
    assert abs(beta - 2.0) < 1e-9

    # too few overlapping points -> no reading.
    assert beta_vs_benchmark(symbol_returns.head(5), benchmark_returns.head(5)) is None

    # --- fetch_next_earnings_date: Yahoo's calendar often lists the last
    # *reported* earnings date next to the upcoming one; min() would pick
    # the stale past date, so past dates are filtered out first. ---
    past = date.today() - timedelta(days=30)
    soon = date.today() + timedelta(days=10)
    later = date.today() + timedelta(days=100)
    with patch.object(risk.market_data, "earnings_calendar", return_value={"Earnings Date": [past, later, soon]}):
        d, ok = fetch_next_earnings_date("AAA")
    assert d == soon and ok is True  # soonest *future* date, not `past`

    # all dates in the past -> no upcoming earnings, but the fetch succeeded.
    with patch.object(risk.market_data, "earnings_calendar", return_value={"Earnings Date": [past]}):
        d, ok = fetch_next_earnings_date("AAA")
    assert d is None and ok is True

    # --- Sharpe / Sortino / Calmar (issue #289) ---
    # Sharpe: (annual_return - rf) / annual_vol, straight from the formula.
    assert abs(sharpe_ratio(0.12, 0.20, risk_free_rate=0.04) - (0.12 - 0.04) / 0.20) < 1e-9
    assert sharpe_ratio(None, 0.20) is None  # no return figure -> no ratio
    assert sharpe_ratio(0.12, None) is None  # no vol figure -> no ratio
    assert sharpe_ratio(0.12, 0.0) is None  # zero vol would divide by zero

    # downside_deviation only counts days below the risk-free daily rate -
    # an all-positive-and-above-target series has no downside days at all.
    calm_mixed = pd.Series([0.001] * 300 + [-0.02, -0.03, -0.01, -0.025])
    dd = downside_deviation(calm_mixed, risk_free_rate=0.04)
    assert dd is not None and dd > 0
    all_up = pd.Series([0.01] * 50)
    assert downside_deviation(all_up, risk_free_rate=0.0) is None

    sortino = sortino_ratio(0.12, calm_mixed, risk_free_rate=0.04)
    assert sortino is not None
    assert sortino_ratio(None, calm_mixed) is None
    assert sortino_ratio(0.12, all_up, risk_free_rate=0.0) is None  # no downside days -> no ratio

    # Calmar: annual_return / |max_drawdown| - drawdown is the module's
    # existing negative-fraction convention (see max_drawdown_details).
    assert abs(calmar_ratio(0.12, -0.30) - 0.12 / 0.30) < 1e-9
    assert calmar_ratio(0.12, 0.0) is None  # no drawdown at all -> divide by zero avoided
    assert calmar_ratio(None, -0.30) is None


if __name__ == "__main__":
    demo()
    print("OK")
