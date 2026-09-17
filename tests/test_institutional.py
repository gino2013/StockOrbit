import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch

import pandas as pd

from app.infrastructure import institutional


def demo():
    institutional_df = pd.DataFrame([
        {"Date Reported": datetime(2026, 6, 30), "Holder": "Blackrock Inc.", "pctHeld": 0.08, "Shares": 100, "Value": 1000, "pctChange": 0.01},
    ])
    insider_df = pd.DataFrame([
        {"Shares": 500, "Value": 1000.0, "Insider": "SOMEONE", "Position": "CFO", "Text": "Sale at price 10.", "Start Date": datetime(2026, 9, 1), "Ownership": "D"},
    ])
    major_df = pd.DataFrame({"Value": {"insidersPercentHeld": 0.02, "institutionsPercentHeld": 0.6}})

    fake_ticker = MagicMock()
    fake_ticker.institutional_holders = institutional_df
    fake_ticker.major_holders = major_df
    fake_ticker.insider_transactions = insider_df

    with patch.object(institutional.yf, "Ticker", return_value=fake_ticker):
        result = institutional.fetch_institutional_data("AAPL")

    assert result["institutional_holders"] == [
        {"holder": "Blackrock Inc.", "pct_held": 0.08, "shares": 100, "value": 1000, "date_reported": "2026-06-30"}
    ]
    assert result["insider_transactions"] == [
        {"insider": "SOMEONE", "position": "CFO", "text": "Sale at price 10.", "shares": 500, "start_date": "2026-09-01"}
    ]
    assert result["insiders_pct_held"] == 0.02
    assert result["institutions_pct_held"] == 0.6

    # empty frames (e.g. an ETF, or Yahoo genuinely has nothing) -> empty
    # lists / None, not a crash.
    empty_ticker = MagicMock()
    empty_ticker.institutional_holders = pd.DataFrame()
    empty_ticker.major_holders = pd.DataFrame()
    empty_ticker.insider_transactions = pd.DataFrame()
    with patch.object(institutional.yf, "Ticker", return_value=empty_ticker):
        empty_result = institutional.fetch_institutional_data("QQQ")
    assert empty_result["institutional_holders"] == []
    assert empty_result["insider_transactions"] == []
    assert empty_result["insiders_pct_held"] is None
    assert empty_result["institutions_pct_held"] is None

    # the fetch itself raises (network error, Render's Yahoo block, etc.)
    # -> same empty shape, not a propagated exception.
    with patch.object(institutional.yf, "Ticker", side_effect=RuntimeError("blocked")):
        failed = institutional.fetch_institutional_data("AAPL")
    assert failed["institutional_holders"] == []
    assert failed["institutions_pct_held"] is None

    # more than _MAX_INSIDER_ROWS transactions -> capped, most recent list
    # position first (this function doesn't re-sort, it trusts yfinance's
    # own order and just truncates it).
    many_insiders = pd.DataFrame([
        {"Shares": i, "Value": 1.0, "Insider": f"P{i}", "Position": "X", "Text": "", "Start Date": datetime(2026, 1, i % 28 + 1), "Ownership": "D"}
        for i in range(1, 20)
    ])
    many_ticker = MagicMock()
    many_ticker.institutional_holders = pd.DataFrame()
    many_ticker.major_holders = pd.DataFrame()
    many_ticker.insider_transactions = many_insiders
    with patch.object(institutional.yf, "Ticker", return_value=many_ticker):
        capped = institutional.fetch_institutional_data("AAPL")
    assert len(capped["insider_transactions"]) == institutional._MAX_INSIDER_ROWS


if __name__ == "__main__":
    demo()
    print("OK")
