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

    fundamentals = {
        "marketCap": 5000.0, "trailingPE": 20.0, "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 90.0,
        "longName": "AAA Corp", "dividendRate": 4.0,
    }
    quote = {"longName": "AAA Corp (live)", "dividendRate": 4.0}
    ohlc = {"open": 108.0, "day_high": 111.0, "day_low": 107.0, "price": 110.0}

    # a symbol that dividend-pays: change% measured against the first close
    # in the selected window, not against previousClose - matches the
    # Google Finance behaviour of the badge changing with the period tab.
    # fundamentals (the cache-resilient source) wins over the uncached live
    # quote when both have a value.
    result = stock_detail.build_stock_detail("AAA", fundamentals, quote, ohlc, history)
    assert result["change_abs"] == 10.0
    assert abs(result["change_pct"] - 0.1) < 1e-9
    assert result["dividend_quarterly"] == 1.0
    assert result["price"] == 110.0
    assert result["market_cap"] == 5000.0
    assert result["open"] == 108.0
    assert result["name"] == "AAA Corp"

    # Yahoo blocks quoteSummary (the Render issue) but the unblocked
    # ticker_history endpoint still works -> price/open/day-range survive
    # from ohlc alone; only the quoteSummary-only stats go blank instead of
    # showing something misleading.
    blocked = stock_detail.build_stock_detail("AAA", {}, {}, ohlc, history)
    assert blocked["price"] == 110.0
    assert blocked["open"] == 108.0
    assert blocked["name"] == "AAA"
    assert blocked["market_cap"] is None
    assert blocked["dividend_quarterly"] is None

    # a symbol nobody holds (no fundamentals_cache row - that job only
    # covers held symbols) but the live quoteSummary call still worked ->
    # fetch_quote() fills the gap instead of showing "-" for no reason.
    uncached = stock_detail.build_stock_detail("AAA", {}, {"marketCap": 999.0, "dividendRate": 2.0}, ohlc, history)
    assert uncached["market_cap"] == 999.0
    assert uncached["dividend_quarterly"] == 0.5

    # an ETF: no marketCap anywhere (yfinance never sets it for ETFs), only
    # totalAssets (its AUM) - still shown in the same "市值" slot.
    etf = stock_detail.build_stock_detail("QQQ", {"totalAssets": 12345.0}, {}, ohlc, history)
    assert etf["market_cap"] == 12345.0

    # an ETF that clearly pays dividends (e.g. VOO) but yfinance leaves
    # dividendRate None anyway - trailingAnnualDividendRate (the actual
    # trailing-12-months total) must be used instead of showing "-".
    div_fallback = stock_detail.build_stock_detail(
        "VOO", {"trailingAnnualDividendRate": 5.44}, {}, ohlc, history
    )
    assert div_fallback["dividend_rate"] == 5.44
    assert abs(div_fallback["dividend_quarterly"] - 1.36) < 1e-9

    # everything blocked and no history at all (bad symbol) -> no change%, no crash.
    empty = stock_detail.build_stock_detail("BAD", {}, {}, {}, [])
    assert empty["price"] is None
    assert empty["change_pct"] is None

    with patch.object(stock_detail.market_data, "ticker_info", side_effect=RuntimeError("blocked")):
        assert stock_detail.fetch_quote("AAA") == {}
    with patch.object(stock_detail.market_data, "ticker_history", side_effect=RuntimeError("blocked")):
        assert stock_detail.today_ohlc("AAA") == {}


if __name__ == "__main__":
    demo()
    print("OK")
