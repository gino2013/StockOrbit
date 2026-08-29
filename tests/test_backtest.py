import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics.backtest import max_drawdown_details, rebalance_dates, simulate_rebalanced_portfolio


def demo():
    prices = pd.DataFrame(
        {"A": [10, 11, 12, 9, 10], "B": [20, 19, 18, 22, 24]},
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )

    no_rebalance = simulate_rebalanced_portfolio(prices, {"A": 0.5, "B": 0.5}, "none", 1000)
    assert len(no_rebalance) == 5
    assert abs(no_rebalance.iloc[0] - 1000) < 1e-6
    drawdown, peak, trough = max_drawdown_details(no_rebalance)
    assert drawdown <= 0
    assert peak <= trough

    monthly = simulate_rebalanced_portfolio(prices, {"A": 0.5, "B": 0.5}, "M", 1000)
    assert len(monthly) == 5
    assert abs(monthly.iloc[0] - 1000) < 1e-6

    # Regression: 2026-01-31 is a Saturday, so a calendar month-end label
    # would never match a real trading day. rebalance_dates must fall back
    # to the first *actual* trading day of February instead of silently
    # skipping January's rebalance.
    business_days = pd.date_range("2026-01-15", "2026-02-10", freq="B")
    dates = rebalance_dates(business_days, "M")
    assert len(dates) == 1
    assert dates[0] in business_days
    assert dates[0].month == 2

    assert rebalance_dates(business_days, "none") == []

    # "H" (half-year) has no pandas Period alias -- bucket by (year, half) manually.
    two_years = pd.bdate_range("2024-01-01", "2025-12-31")
    half_dates = rebalance_dates(two_years, "H")
    assert [d.date().isoformat() for d in half_dates] == ["2024-07-01", "2025-01-01", "2025-07-01"]


if __name__ == "__main__":
    demo()
    print("OK")
