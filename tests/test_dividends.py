import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dividends import trailing_twelve_month_dividends, with_yield


def demo():
    as_of = date(2026, 8, 27)
    transactions = [
        {"trans_type": "DIV", "symbol": "QQQ", "report_date": date(2026, 7, 10), "amount": 7.76},
        {"trans_type": "DIV", "symbol": "QQQ", "report_date": date(2025, 10, 1), "amount": 6.5},
        # outside the trailing-12-month window -> excluded.
        {"trans_type": "DIV", "symbol": "QQQ", "report_date": date(2025, 1, 1), "amount": 100},
        {"trans_type": "DIV", "symbol": "VOO", "report_date": date(2026, 6, 1), "amount": 12.0},
        {"trans_type": "BOUGHT", "symbol": "QQQ", "report_date": date(2026, 7, 10), "amount": -1000},
    ]
    ttm = trailing_twelve_month_dividends(transactions, as_of)
    by_symbol = {r["symbol"]: r["ttm_dividends"] for r in ttm}
    assert abs(by_symbol["QQQ"] - 14.26) < 1e-6
    assert abs(by_symbol["VOO"] - 12.0) < 1e-6

    rows = with_yield(ttm, {"QQQ": 6800, "VOO": 11200})
    by_symbol2 = {r["symbol"]: r for r in rows}
    assert abs(by_symbol2["QQQ"]["ttm_yield"] - 14.26 / 6800) < 1e-9
    # sorted by dividend amount descending (QQQ's 14.26 > VOO's 12.0)
    assert rows[0]["symbol"] == "QQQ"

    # a symbol no longer held still shows its total, just no yield.
    rows2 = with_yield(ttm, {"VOO": 11200})
    by_symbol3 = {r["symbol"]: r for r in rows2}
    assert by_symbol3["QQQ"]["ttm_yield"] is None
    assert by_symbol3["QQQ"]["market_value"] is None


if __name__ == "__main__":
    demo()
    print("OK")
