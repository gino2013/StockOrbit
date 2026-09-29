import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import numpy as np

from app.application import goals


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 6000.0},
        {"symbol": "VOO", "market_value": 4000.0},
        {"symbol": "CASH", "market_value": 500.0},
    ]
    transactions = [
        {"trans_type": "DEPOSIT", "symbol": None, "report_date": date(2025, 1, 1), "quantity": 0, "trade_price": 0, "amount": -10000.0},
    ]
    as_of = date(2026, 1, 1)

    with patch.object(goals, "weighted_portfolio_returns", return_value=_fake_returns()):
        result = goals.goal_progress(
            target_amount=100000.0, target_date=date(2036, 1, 1),
            snapshots=snapshots, transactions=transactions, as_of=as_of,
        )

    # existing build_goal_progress fields still come through untouched.
    assert result["current_value"] == 10500.0
    assert result["target_amount"] == 100000.0
    # new field: a probability in [0, 1], not the old on_track boolean.
    assert result["monte_carlo_probability"] is not None
    assert 0.0 <= result["monte_carlo_probability"] <= 1.0

    # CASH must not be treated as a symbol to fetch/weight returns for.
    with patch.object(goals, "weighted_portfolio_returns", return_value=_fake_returns()) as mocked:
        goals.goal_progress(
            target_amount=100000.0, target_date=date(2036, 1, 1),
            snapshots=snapshots, transactions=transactions, as_of=as_of,
        )
    called_symbols = mocked.call_args[0][0]
    assert "CASH" not in called_symbols
    assert set(called_symbols) == {"AAPL", "VOO"}

    # no holdings at all -> current_value 0, probability None (nothing to
    # simulate from), not a crash.
    with patch.object(goals, "weighted_portfolio_returns") as mocked:
        empty = goals.goal_progress(
            target_amount=100000.0, target_date=date(2036, 1, 1),
            snapshots=[], transactions=[], as_of=as_of,
        )
    mocked.assert_not_called()
    assert empty["monte_carlo_probability"] is None


def _fake_returns():
    import pandas as pd

    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-01-01", periods=100)
    return pd.Series(rng.normal(0.0005, 0.01, size=100), index=dates)


if __name__ == "__main__":
    demo()
    print("OK")
