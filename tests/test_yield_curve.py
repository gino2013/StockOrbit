import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import yield_curve as yc


def demo():
    dates = pd.bdate_range("2025-01-01", periods=400)
    # a deliberately inverted curve: short rate (^IRX) higher than long
    # (^TYX), flat over the whole window so "6 months ago" == "today"
    # exactly - makes the compare assertions exact, not approximate.
    prices = pd.DataFrame(
        {"^IRX": [5.0] * 400, "^FVX": [4.5] * 400, "^TNX": [4.2] * 400, "^TYX": [4.0] * 400},
        index=dates,
    )

    with patch.object(yc.market_data, "download_close", return_value=prices):
        result = yc.build_yield_curve()

    assert result["as_of"] == dates[-1].date().isoformat()
    assert len(result["current"]) == 4
    labels = [p["label"] for p in result["current"]]
    assert labels == ["13 週", "5 年", "10 年", "30 年"]
    assert result["current"][0]["yield_pct"] == 5.0  # ^IRX
    assert result["current"][-1]["yield_pct"] == 4.0  # ^TYX
    assert result["inverted"] is True  # short (5.0) > long (4.0)
    assert result["compare"] is None  # not requested

    # --- is_inverted directly ---
    assert yc.is_inverted([{"years": 0.25, "yield_pct": 5.0}, {"years": 30, "yield_pct": 4.0}]) is True
    assert yc.is_inverted([{"years": 0.25, "yield_pct": 3.0}, {"years": 30, "yield_pct": 4.0}]) is False
    assert yc.is_inverted([{"years": 10, "yield_pct": 4.0}]) is None  # fewer than 2 points -> unknown, not False

    # --- compare_months_ago: flat data -> the compare curve is identical
    # to today's (same values throughout the window). ---
    with patch.object(yc.market_data, "download_close", return_value=prices):
        with_compare = yc.build_yield_curve(compare_months_ago=6)
    assert with_compare["compare"] is not None
    assert with_compare["compare"]["values"][0]["yield_pct"] == 5.0
    assert with_compare["compare"]["as_of"] <= with_compare["as_of"]

    # --- a maturity missing from the download (e.g. Yahoo dropped one
    # symbol that day) is skipped, not zero-filled. ---
    partial = prices.drop(columns=["^TYX"])
    with patch.object(yc.market_data, "download_close", return_value=partial):
        partial_result = yc.build_yield_curve()
    assert len(partial_result["current"]) == 3
    assert "30 年" not in [p["label"] for p in partial_result["current"]]

    # --- no data at all -> empty result, not a crash. ---
    with patch.object(yc.market_data, "download_close", return_value=pd.DataFrame()):
        empty = yc.build_yield_curve()
    assert empty["current"] == []
    assert empty["inverted"] is None
    assert empty["as_of"] is None


if __name__ == "__main__":
    demo()
    print("OK")
