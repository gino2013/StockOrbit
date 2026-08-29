import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import performance_report as pr


def demo():
    snapshots = [
        {"symbol": "AAA", "quantity": 10, "market_value": 1200, "cost_basis": 1000},
        {"symbol": "CASH", "quantity": 1, "market_value": 100, "cost_basis": 100},
    ]
    dates = pd.bdate_range("2026-01-01", periods=20)
    portfolio_series = pd.Series(range(20), index=dates, dtype=float) + 1000  # 1000 -> 1019
    benchmark_series = pd.Series(range(20), index=dates, dtype=float) / 2 + 1000  # 1000 -> 1009.5
    # per-symbol prices for the period-XIRR reconstruction: AAA 100 -> 130.
    aaa_prices = pd.DataFrame({"AAA": [100.0, 130.0]}, index=[dates[0], dates[-1]])

    transactions = [
        {"symbol": "AAA", "trans_type": "BOUGHT", "report_date": date(2026, 1, 5), "quantity": 5, "trade_price": 100.0, "amount": -500.0},
        {"symbol": "AAA", "trans_type": "SOLD", "report_date": date(2026, 1, 10), "quantity": -2, "trade_price": 120.0, "amount": 240.0},
        # outside the report window -> excluded from both transactions and realized gains.
        {"symbol": "AAA", "trans_type": "BOUGHT", "report_date": date(2025, 1, 1), "quantity": 3, "trade_price": 90.0, "amount": -270.0},
    ]

    with patch.object(pr, "portfolio_value_history", return_value=portfolio_series), \
         patch.object(pr, "weighted_return_series", return_value=benchmark_series), \
         patch.object(pr, "close_prices", return_value=aaa_prices):
        result = pr.build_performance_report(
            snapshots, transactions, "2026-01-01", "2026-01-30", benchmark_weights={"SPY": 1.0}
        )

    assert abs(result["period_return"] - (1019 / 1000 - 1)) < 1e-9
    assert abs(result["benchmark_return"] - (1009.5 / 1000 - 1)) < 1e-9
    # only the two 2026 transactions fall in the report window.
    assert len(result["transactions"]) == 2
    assert all(t["report_date"] >= date(2026, 1, 1) for t in result["transactions"])
    # FIFO consumes the earliest lot first: the 2025 buy of 3@90 (even
    # though it's outside the report window, it's still in cost-basis
    # history) -> 2 sold @120 costs 2*90=180, proceeds 2*120=240, gain 60.
    assert abs(result["realized_gain"] - 60.0) < 1e-6
    assert result["realized_trade_count"] == 1

    # since-purchase return: (1300 market value - 1100 cost) / 1100.
    assert abs(result["since_purchase_return"] - 200 / 1100) < 1e-9
    # period money-weighted: opening = 3 shares (held on 2026-01-01) * 100 = 300,
    # closing = 6 shares (after the window's +5/-2) * 130 = 780, window trade
    # cash -500 (buy) +240 (sell). PnL = 780 - 300 - 500 + 240 = 220.
    assert abs(result["period_pnl"] - 220.0) < 1e-6
    assert result["period_xirr"] is not None and result["period_xirr"] > 0

    # no holdings -> a clear error, not a crash on an empty weights dict.
    try:
        pr.build_performance_report([{"symbol": "CASH", "quantity": 1, "market_value": 100}], [], "2026-01-01", "2026-01-30")
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    demo()
    print("OK")
