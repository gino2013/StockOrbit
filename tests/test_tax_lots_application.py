import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from app.application import tax_lots


def demo():
    transactions = [
        {"trans_type": "BOUGHT", "symbol": "AAPL", "report_date": date(2024, 1, 1), "quantity": 10, "trade_price": 100},
        {"trans_type": "BOUGHT", "symbol": "AAPL", "report_date": date(2025, 1, 1), "quantity": 10, "trade_price": 150},
    ]

    with patch.object(tax_lots, "today_ohlc", return_value={"price": 200.0}):
        result = tax_lots.tax_lot_report(transactions, "AAPL", 10)
    assert result["symbol"] == "AAPL"
    assert result["price"] == 200.0
    assert result["lots"] == [
        {"buy_date": "2024-01-01", "quantity": 10, "price": 100},
        {"buy_date": "2025-01-01", "quantity": 10, "price": 150},
    ]
    assert result["comparison"] is not None
    assert abs(result["comparison"]["fifo"]["cost_basis"] - 10 * 100) < 1e-9

    # a symbol with no open lots at all -> no live-price call made (nothing
    # to price), empty lots/comparison instead of a crash.
    with patch.object(tax_lots, "today_ohlc") as mocked:
        no_lots = tax_lots.tax_lot_report(transactions, "MSFT", 5)
    mocked.assert_not_called()
    assert no_lots["lots"] == []
    assert no_lots["comparison"] is None
    assert no_lots["price"] is None

    # live price fetch fails (Render/Yahoo block, matches today_ohlc's own
    # {} on failure) -> lots still shown, comparison just can't be priced.
    with patch.object(tax_lots, "today_ohlc", return_value={}):
        no_price = tax_lots.tax_lot_report(transactions, "AAPL", 10)
    assert no_price["lots"]
    assert no_price["price"] is None
    assert no_price["comparison"] is None


if __name__ == "__main__":
    demo()
    print("OK")
