import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics.risk import TRADING_DAYS_PER_YEAR, annualized_volatility, beta_vs_benchmark


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


if __name__ == "__main__":
    demo()
    print("OK")
