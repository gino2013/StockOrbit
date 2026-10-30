import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import entry_check as ec


def demo():
    # position inside the window's range: top / bottom / middle.
    closes = pd.Series([10.0, 20.0, 15.0])
    stats = ec.window_stats(closes, 3)
    assert stats["position"] == 0.5 and stats["zone"] == "mid"
    assert abs(stats["from_high"] - (-0.25)) < 1e-9
    assert ec.window_stats(pd.Series([10.0, 15.0, 20.0]), 3)["zone"] == "high"
    assert ec.window_stats(pd.Series([20.0, 15.0, 10.0]), 3)["zone"] == "low"
    # a fill above the window's closes clamps to the top.
    assert ec.window_stats(closes, 3, price=25.0)["position"] == 1.0
    # flat window doesn't divide by zero.
    assert ec.window_stats(pd.Series([5.0, 5.0]), 2)["position"] == 0.5

    # score: +/-1 per 1M/3M/1Y zone, RSI extreme, similar-setup edge;
    # 5Y (4th window) doesn't vote.
    w = lambda z: {"zone": z, "label": "x"}
    sim = lambda win, base: {"win_rate": win, "baseline_win_rate": base}
    assert ec.entry_score([w("high")] * 4, 50, None)[0] == -3
    assert ec.entry_score([w("mid"), w("mid"), w("mid"), w("high")], 50, None)[0] == 0
    score, reasons = ec.entry_score([w("low"), w("low"), w("mid")], 25, sim(0.91, 0.71))
    assert score == 4 and len(reasons) == 4
    assert ec.entry_score([w("mid")], 75, sim(0.60, 0.70))[0] == -2
    assert ec.entry_score([w("mid")], None, sim(0.73, 0.70))[0] == 0  # under 5pp edge
    # stars: boundaries of the score -> 1..5 mapping; verdict follows stars.
    assert [ec.stars(x) for x in (5, 4, 3, 2, 1, 0, -1, -2, -3, -4, -5)] == [5, 5, 4, 4, 3, 3, 3, 2, 2, 1, 1]
    assert [ec.verdict(x) for x in (1, 2, 3, 4, 5)] == ["high", "high", "mid", "low", "low"]

    # end-to-end: a steady uptrend ends at the top of every window, and
    # every past forward-3M return was positive.
    dates = pd.bdate_range("2016-01-01", periods=1400)
    prices = pd.Series([100 * 1.001 ** i for i in range(1400)], index=dates)
    with patch.object(ec.market_data, "ticker_history", return_value=pd.DataFrame({"Close": prices})):
        result = ec.check_entry("AAA")
    assert [x["label"] for x in result["windows"]] == ["1 個月", "3 個月", "1 年", "5 年"]
    assert all(x["zone"] == "high" for x in result["windows"])
    assert result["verdict"] == "high"
    assert result["score"] == -4 and result["stars"] == 1  # 3 windows high + RSI overbought
    assert result["similar"]["win_rate"] == 1.0
    assert result["similar"]["baseline_win_rate"] == 1.0

    # replaying a past buy: only prices up to that day, actual fill price
    # used for the position, plus return since then.
    from datetime import date
    buy_day = dates[700].date()
    with patch.object(ec.market_data, "ticker_history", return_value=pd.DataFrame({"Close": prices})):
        past = ec.check_entry("AAA", as_of=buy_day, buy_price=float(prices.iloc[700]) * 0.5)
    assert past["as_of"] == buy_day.isoformat()
    assert all(x["position"] == 0 for x in past["windows"])  # below every range, clamped
    assert [x["label"] for x in past["windows"]] == ["1 個月", "3 個月", "1 年"]  # no 5Y of data yet
    assert abs(past["since_buy"]["return"] - (prices.iloc[-1] / (prices.iloc[700] * 0.5) - 1)) < 1e-9
    assert "since_buy" not in result

    txs = [
        {"symbol": "AAA", "trans_type": "BOUGHT", "report_date": date(2026, 1, 2), "trade_price": 10, "quantity": 1},
        {"symbol": "BBB", "trans_type": "BOUGHT", "report_date": date(2026, 3, 1), "trade_price": 20, "quantity": 2},
        {"symbol": "AAA", "trans_type": "SOLD", "report_date": date(2026, 4, 1), "trade_price": 30, "quantity": 1},
        {"symbol": None, "trans_type": "BOUGHT", "report_date": date(2026, 5, 1), "trade_price": 1, "quantity": 1},
    ]
    assert [b["symbol"] for b in ec.recent_buys(txs)] == ["BBB", "AAA"]
    assert ec.recent_buys(txs, limit=1)[0]["date"] == "2026-03-01"

    # too little history -> error, short history -> only the windows that fit.
    with patch.object(ec.market_data, "ticker_history", return_value=pd.DataFrame({"Close": prices[:10]})):
        try:
            ec.check_entry("BBB")
            assert False, "expected ValueError"
        except ValueError:
            pass
    with patch.object(ec.market_data, "ticker_history", return_value=pd.DataFrame({"Close": prices[:100]})):
        result = ec.check_entry("CCC")
    assert [x["label"] for x in result["windows"]] == ["1 個月", "3 個月"]
    assert result["similar"] is None  # no 200-day MA yet

    print("test_entry_check OK")


if __name__ == "__main__":
    demo()
