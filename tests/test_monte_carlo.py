import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import numpy as np
import pandas as pd

from app.domain.analytics import monte_carlo as mc


def demo():
    # --- simulate_paths: zero-variance daily returns -> every simulated
    # path is identical, so p10/p50/p90 all collapse to the same exact
    # compounded value at every checkpoint (hand-checkable, no randomness
    # actually matters here).
    flat_returns = np.full(252, 0.0005)
    result = mc.simulate_paths(10000, flat_returns, months=3, n_simulations=200, seed=1)
    assert result["months"] == [1, 2, 3]
    for p10, p50, p90 in zip(result["p10"], result["p50"], result["p90"]):
        assert abs(p10 - p50) < 1e-6
        assert abs(p50 - p90) < 1e-6
    days_per_month = mc.TRADING_DAYS_PER_YEAR / 12
    expected_month1 = 10000 * (1.0005) ** round(days_per_month)
    assert abs(result["p50"][0] - expected_month1) < 1e-3

    # --- real variance -> the 10/90 band should widen over time (variance
    # of a compounded random walk grows with horizon), and percentiles must
    # stay ordered p10 <= p50 <= p90 at every single checkpoint.
    rng = np.random.default_rng(0)
    volatile_returns = rng.normal(0.0005, 0.02, size=252)
    wide = mc.simulate_paths(10000, volatile_returns, months=12, n_simulations=2000, seed=2)
    for p10, p50, p90 in zip(wide["p10"], wide["p50"], wide["p90"]):
        assert p10 <= p50 <= p90
    first_band = wide["p90"][0] - wide["p10"][0]
    last_band = wide["p90"][-1] - wide["p10"][-1]
    assert last_band > first_band

    # --- determinism: same seed -> identical output, every time. ---
    again = mc.simulate_paths(10000, volatile_returns, months=12, n_simulations=2000, seed=2)
    assert wide == again

    # --- edge cases: no crash, just an empty (unplottable) result. ---
    assert mc.simulate_paths(0, volatile_returns, months=12) == {"months": [], "p10": [], "p50": [], "p90": []}
    assert mc.simulate_paths(10000, volatile_returns, months=0) == {"months": [], "p10": [], "p50": [], "p90": []}
    assert mc.simulate_paths(10000, np.array([0.01, -0.01]), months=12) == {"months": [], "p10": [], "p50": [], "p90": []}

    # --- build_monte_carlo_projection: wires weighted_portfolio_returns()
    # into simulate_paths() end to end. ---
    dates = pd.bdate_range("2025-01-01", periods=100)
    synthetic_returns = pd.Series(rng.normal(0.0004, 0.01, size=100), index=dates)
    with patch.object(mc, "weighted_portfolio_returns", return_value=synthetic_returns):
        built = mc.build_monte_carlo_projection(["AAA", "BBB"], {"AAA": 0.6, "BBB": 0.4}, 5000, months=6)
    assert built["months"] == [1, 2, 3, 4, 5, 6]
    assert all(p10 <= p50 <= p90 for p10, p50, p90 in zip(built["p10"], built["p50"], built["p90"]))


if __name__ == "__main__":
    demo()
    print("OK")
