import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app import drip


def demo():
    dates = pd.bdate_range("2025-01-01", periods=10)
    # flat for the first half, then rises - isolates the compounding effect:
    # shares bought with the reinvested dividend only pay off once the price
    # actually goes up afterward.
    closes = pd.Series([100.0] * 5 + [110.0] * 5, index=dates)
    dividends = pd.Series([0.0] * 10, index=dates)
    dividends.iloc[4] = 2.0  # a single $2/share dividend right before the price rise
    history = pd.DataFrame({"Close": closes, "Dividends": dividends})

    class FakeTicker:
        def history(self, start, end, auto_adjust):
            return history

    with patch.object(drip.yf, "Ticker", return_value=FakeTicker()):
        result = drip.simulate_drip("AAA", "2025-01-01", "2025-01-15", initial_investment=1000.0)

    # cash scenario: original share count never changes, dividend cash sits idle earning nothing.
    shares = 1000.0 / 100.0
    expected_cash_final = shares * 110.0 + shares * 2.0
    assert abs(result["cash_final_value"] - expected_cash_final) < 1e-6

    # drip scenario buys extra shares with the dividend *before* the price rise,
    # so those extra shares also benefit from the rise - drip must end up ahead.
    assert result["drip_final_value"] > result["cash_final_value"]
    assert abs(result["total_dividends_per_share"] - 2.0) < 1e-9

    # too little data -> a clear error, not a crash.
    class EmptyTicker:
        def history(self, start, end, auto_adjust):
            return history.head(1)

    with patch.object(drip.yf, "Ticker", return_value=EmptyTicker()):
        try:
            drip.simulate_drip("AAA", "2025-01-01", "2025-01-02")
            assert False, "expected ValueError"
        except ValueError:
            pass


if __name__ == "__main__":
    demo()
    print("OK")
