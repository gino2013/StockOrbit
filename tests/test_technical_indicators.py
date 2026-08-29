import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app import technical_indicators as ti


def demo():
    # RSI sanity: an unbroken string of gains should push RSI near 100,
    # an unbroken string of losses should push it near 0.
    all_gains = pd.Series([100 + i for i in range(30)], dtype=float)
    rsi_up = ti.compute_rsi(all_gains)
    assert rsi_up.iloc[-1] > 95

    all_losses = pd.Series([100 - i for i in range(30)], dtype=float)
    rsi_down = ti.compute_rsi(all_losses)
    assert rsi_down.iloc[-1] < 5

    # golden cross: short MA was below long MA yesterday, above today.
    assert ti._ma_cross_state(101, 100, 99, 100) == "golden_cross"
    # death cross: short MA was above long MA yesterday, below today.
    assert ti._ma_cross_state(99, 100, 101, 100) == "death_cross"
    # steady state above/below, no cross today.
    assert ti._ma_cross_state(101, 100, 102, 100) == "above"
    assert ti._ma_cross_state(99, 100, 98, 100) == "below"

    # end-to-end against a synthetic price series with enough history for
    # the 200-day MA, rising steadily so short MA ends up above long MA.
    dates = pd.bdate_range("2024-01-01", periods=280)
    prices = pd.Series(range(280), index=dates, dtype=float) + 100
    fake_data = pd.DataFrame({"AAA": prices})

    with patch.object(ti.yf, "download", return_value={"Close": fake_data}):
        results = ti.compute_technical_indicators(["AAA"])
    assert len(results) == 1
    r = results[0]
    assert r["symbol"] == "AAA"
    assert r["current_price"] == prices.iloc[-1]
    assert r["ma_short"] > r["ma_long"]  # steadily rising -> short MA above long MA
    assert r["rsi"] > 50  # steadily rising -> RSI above midpoint
    assert "insufficient_history" not in r
    # regression: rsi_overbought/oversold must be plain Python bool, not
    # numpy.bool_ (numpy.bool_ isn't JSON-serializable -> 500 on the endpoint,
    # a bug real prices caught but this synthetic all-float series didn't).
    assert type(r["rsi_overbought"]) is bool
    assert type(r["rsi_oversold"]) is bool
    json.dumps(results)  # must not raise TypeError

    # too little history -> flagged rather than crashing or fabricating a reading.
    short_dates = pd.bdate_range("2024-01-01", periods=10)
    short_prices = pd.Series(range(10), index=short_dates, dtype=float) + 100
    short_data = pd.DataFrame({"BBB": short_prices})
    with patch.object(ti.yf, "download", return_value={"Close": short_data}):
        short_results = ti.compute_technical_indicators(["BBB"])
    assert short_results[0]["insufficient_history"] is True

    assert ti.compute_technical_indicators([]) == []


if __name__ == "__main__":
    demo()
    print("OK")
