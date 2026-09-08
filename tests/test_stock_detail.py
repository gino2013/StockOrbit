import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import stock_detail


def demo():
    dates = pd.bdate_range("2026-01-01", periods=5)
    closes = pd.Series([100.0, 102.0, 98.0, 101.0, 110.0], index=dates)
    history_df = pd.DataFrame({"Close": closes})

    with patch.object(stock_detail.market_data, "ticker_history", return_value=history_df):
        history = stock_detail.price_history("AAA", "1y")
    assert len(history) == 5
    assert history[0]["close"] == 100.0
    assert history[-1]["close"] == 110.0

    try:
        stock_detail.price_history("AAA", "not-a-period")
        assert False, "expected ValueError"
    except ValueError:
        pass

    # a symbol that dividend-pays: change% measured against the first close
    # in the selected window, not against previousClose - matches the
    # Google Finance behaviour of the badge changing with the period tab.
    result = stock_detail.build_stock_detail(
        "AAA", {"currentPrice": 110.0, "dividendRate": 4.0, "trailingPE": 20.0}, history
    )
    assert result["change_abs"] == 10.0
    assert abs(result["change_pct"] - 0.1) < 1e-9
    assert result["dividend_quarterly"] == 1.0
    assert result["price"] == 110.0

    # no fundamentals at all (Yahoo blocked + no cache) -> price falls back
    # to the last history close, and every stat that has nothing behind it
    # is None rather than a crash.
    fallback = stock_detail.build_stock_detail("AAA", {}, history)
    assert fallback["price"] == 110.0
    assert fallback["trailing_pe"] is None
    assert fallback["dividend_quarterly"] is None

    # no history at all (bad symbol) -> no change%, no crash.
    empty = stock_detail.build_stock_detail("BAD", {}, [])
    assert empty["price"] is None
    assert empty["change_pct"] is None

    # Yahoo blocks quoteSummary (the Render issue) -> degrade to {}, not a crash;
    # the caller then shows "-" for every quote stat rather than stale/wrong data.
    with patch.object(stock_detail.market_data, "ticker_info", side_effect=RuntimeError("blocked")):
        assert stock_detail.fetch_quote("AAA") == {}


if __name__ == "__main__":
    demo()
    print("OK")
