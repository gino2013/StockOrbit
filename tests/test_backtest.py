import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.backtest import max_drawdown, simulate_rebalanced_portfolio


def demo():
    prices = pd.DataFrame(
        {"A": [10, 11, 12, 9, 10], "B": [20, 19, 18, 22, 24]},
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )

    no_rebalance = simulate_rebalanced_portfolio(prices, {"A": 0.5, "B": 0.5}, "none", 1000)
    assert len(no_rebalance) == 5
    assert abs(no_rebalance.iloc[0] - 1000) < 1e-6
    assert max_drawdown(no_rebalance) <= 0

    monthly = simulate_rebalanced_portfolio(prices, {"A": 0.5, "B": 0.5}, "M", 1000)
    assert len(monthly) == 5
    assert abs(monthly.iloc[0] - 1000) < 1e-6


if __name__ == "__main__":
    demo()
    print("OK")
