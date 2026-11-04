import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import steady


def demo():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    # high 100 -> drop to 70 (-30%) -> back to 100 on day 4 -> new high 120 -> now 90 (-25%)
    closes = pd.Series([100, 80, 70, 100, 110, 120, 110, 100, 95, 90], index=idx, dtype=float)
    # first hit of -25% was day 2 (70); back to 100 on day 3 -> 1 calendar day.
    # bouncing around the threshold inside one drawdown still counts once.
    assert steady.past_recoveries(closes, -0.25) == [1]
    bouncy = pd.Series([100, 70, 80, 70, 100, 120, 90], index=idx[:7], dtype=float)
    assert steady.past_recoveries(bouncy, -0.25) == [3]
    # today deeper than anything before -> no precedent; current drawdown never counts.
    assert steady.past_recoveries(closes, -0.35) == []

    with patch.object(steady, "MIN_SAMPLES", 1), patch.object(steady, "FORWARD", [("1d", 1)]):
        r = steady.analyze(closes)
    assert abs(r["drawdown"] - (90 / 120 - 1)) < 1e-9 and r["high"] == 120
    assert r["past_drops"] == 1 and r["recovery_median_days"] == 1
    # days at least 25% down with a next day: day 2 (70 -> 100).
    assert r["forward"]["1d"] == {"samples": 1, "median": 100 / 70 - 1, "win_rate": 1.0}
    assert steady.analyze(closes)["forward"]["1y"] is None  # too few samples

    # report: market row first, holdings carry cost and unrealized; missing data -> error row.
    frame = pd.DataFrame({"^GSPC": closes, "AAA": closes})
    holdings = [
        {"symbol": "AAA", "quantity": 10, "market_value": 900, "cost_basis": 1000},
        {"symbol": "ZZZ", "quantity": 1, "market_value": 100, "cost_basis": 50},
        {"symbol": "OLD", "quantity": 0, "market_value": 0, "cost_basis": 0},
        {"symbol": "CASH", "quantity": 500, "market_value": 500, "cost_basis": 500},
    ]
    with patch.object(steady.market_data, "download_close", return_value=frame) as dl:
        rep = steady.steady_report(holdings)
    assert dl.call_args.args[0] == ["^GSPC", "AAA", "ZZZ"]
    assert rep["market"]["symbol"] == "^GSPC" and rep["market"]["past_drops"] == 1
    aaa, zzz = rep["holdings"]
    assert aaa["avg_cost"] == 100 and abs(aaa["unrealized"] + 0.1) < 1e-9
    assert zzz["error"] and zzz["unrealized"] == 1.0
    assert abs(rep["portfolio_unrealized"] - (1000 / 1050 - 1)) < 1e-9
    print("ok")


if __name__ == "__main__":
    demo()
