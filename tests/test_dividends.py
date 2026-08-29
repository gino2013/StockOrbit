import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.income.dividends import forecast_dividend_calendar, trailing_twelve_month_dividends, with_yield


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

    # QQQ has historically paid in July and October -> both should recur in
    # the next 12 months, using the *latest* amount seen for that month
    # (2026-07's 7.76, not 2025-10's stale 6.5, for the July slot).
    forecast = forecast_dividend_calendar(transactions, as_of=date(2026, 8, 27), months_ahead=12)
    by_symbol_month = {(f["symbol"], f["month"]): f for f in forecast}
    assert (2027, 7, "QQQ") == (
        by_symbol_month[("QQQ", 7)]["year"], by_symbol_month[("QQQ", 7)]["month"], "QQQ"
    )
    assert abs(by_symbol_month[("QQQ", 7)]["estimated_amount"] - 7.76) < 1e-9
    assert abs(by_symbol_month[("QQQ", 10)]["estimated_amount"] - 6.5) < 1e-9
    # VOO only ever paid in June -> only one forecast entry for VOO.
    assert sum(1 for f in forecast if f["symbol"] == "VOO") == 1
    # QQQ has historically paid in Jan/Jul/Oct -> exactly those 3 months,
    # and BOUGHT rows must never leak into the dividend forecast.
    assert sorted(f["month"] for f in forecast if f["symbol"] == "QQQ") == [1, 7, 10]


if __name__ == "__main__":
    demo()
    print("OK")
