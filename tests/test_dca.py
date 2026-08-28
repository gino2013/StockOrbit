import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app import dca


def demo():
    dates = pd.bdate_range("2025-01-01", periods=90)
    # steadily rising price -> DCA buys more shares early (cheap) than late
    # (expensive), so DCA should end up with a *different* total return than
    # lump-sum, which buys everything on day 1 at the cheapest price.
    prices = pd.DataFrame({"AAA": pd.Series(range(90), index=dates, dtype=float) + 100})

    dca_series, total_invested = dca.simulate_dca_portfolio(prices, {"AAA": 1.0}, contribution=100, frequency="M")
    assert total_invested > 0
    assert len(dca_series) == len(dates)
    # nothing invested before the first contribution date should be nonzero after it
    assert dca_series.iloc[0] > 0  # first trading day always contributes

    with patch.object(dca.yf, "download", return_value={"Close": prices}):
        result = dca.run_dca_comparison({"AAA": 1.0}, "2025-01-01", "2025-05-01", contribution=100, frequency="M")

    assert len(result["dates"]) == len(dates)
    assert result["total_invested"] == round(total_invested, 2)
    # lump-sum buys everything on day 1 (cheapest price in a rising market)
    # so it should end up strictly ahead of DCA here.
    assert result["lumpsum_return"] > result["dca_return"]

    # too little data -> a clear error, not a crash on missing rows.
    with patch.object(dca.yf, "download", return_value={"Close": prices.head(1)}):
        try:
            dca.run_dca_comparison({"AAA": 1.0}, "2025-01-01", "2025-01-02", contribution=100, frequency="M")
            assert False, "expected ValueError"
        except ValueError:
            pass


if __name__ == "__main__":
    demo()
    print("OK")
