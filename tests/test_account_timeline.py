import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.domain.analytics.account_timeline import build_account_timeline, split_factor


def t(d, typ, amount, symbol=None, qty=0.0, price=0.0):
    return {"report_date": d, "trans_type": typ, "amount": amount,
            "symbol": symbol, "quantity": qty, "trade_price": price}


def demo():
    days = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])

    # 10:1 split on 01-07: pre-split buy of 1 share @ $1000 is 10 shares @ $100
    # today; yfinance's split-adjusted close is already in today's units.
    splits = pd.DataFrame({"NVDA": [0.0, 0.0, 10.0, 0.0], "AAPL": 0.0}, index=days)
    closes = pd.DataFrame({"NVDA": [100.0, 110.0, 120.0, 130.0], "AAPL": [200.0, 200.0, 210.0, 220.0]}, index=days)
    assert split_factor(splits["NVDA"], date(2026, 1, 5)) == 10.0
    assert split_factor(splits["NVDA"], date(2026, 1, 7)) == 1.0

    txns = [
        t(date(2026, 1, 3), "DEPOSIT", 5000.0),                          # weekend -> applied on 01-05
        t(date(2026, 1, 5), "BOUGHT", -1000.0, "NVDA", 1, 1000.0),
        t(date(2026, 1, 5), "BOUGHT", -2000.0, "AAPL", 10, 200.0),
        t(date(2026, 1, 6), "BOUGHT", -1000.0, "AAPL", 5, 200.0),
        t(date(2026, 1, 7), "SOLD", 1050.0, "AAPL", -5, 210.0),         # avg cost 200 -> +50
        t(date(2026, 1, 7), "DIV", 10.0, "AAPL"),
        t(date(2026, 1, 8), "SOLD", 2200.0, "AAPL", 10, 220.0),         # sells out
    ]
    r = build_account_timeline(txns, closes, splits, {"NVDA": 10, "CASH": 4260.0})

    assert r["dates"][0] == "2026-01-05"
    # 01-05: cash 5000-3000=2000, NVDA 10*100, AAPL 10*200
    assert r["total_value"][0] == 2000 + 1000 + 2000
    assert r["invested"] == [5000.0] * 4
    nvda = r["per_symbol"]["NVDA"]
    assert nvda["market_value"] == [1000.0, 1100.0, 1200.0, 1300.0]
    assert nvda["cost"] == [1000.0] * 4

    aapl = r["per_symbol"]["AAPL"]
    assert aapl["cost"] == [2000.0, 3000.0, 2000.0, 0.0]  # avg cost; sold out -> 0
    assert aapl["market_value"][-1] == 0.0

    sells = [m for m in r["markers"] if m["side"] == "sell"]
    assert sells[0]["date"] == "2026-01-07" and sells[0]["items"][0]["realized_gain"] == 50.0
    assert sells[1]["items"][0]["realized_gain"] == 200.0
    buys = [m for m in r["markers"] if m["side"] == "buy"]
    assert len(buys[0]["items"]) == 2  # same-day buys merged into one marker
    assert buys[0]["items"][0]["quantity"] == 10  # split-adjusted

    # final cash: 5000-1000-2000-1000+1050+10+2200 = 4260 -> matches, no warning
    assert r["latest"]["cash"] == 4260.0
    assert r["latest"]["holdings_value"] == 1300.0
    assert r["symbols"] == ["NVDA", "AAPL"] and r["sold_out"] == ["AAPL"]
    w = r["warnings"]
    assert w["share_mismatches"] == [] and w["cash_mismatch"] is None and not w["negative_cash"]

    # Missing deposit + a holding transferred in -> all three warnings fire.
    r2 = build_account_timeline(
        [t(date(2026, 1, 5), "BOUGHT", -1000.0, "NVDA", 1, 1000.0)], closes, splits,
        {"NVDA": 10, "VOO": 3, "CASH": 0.0},
    )
    w2 = r2["warnings"]
    assert w2["negative_cash"]
    assert w2["cash_mismatch"] == {"rebuilt": -1000.0, "actual": 0.0}
    assert w2["share_mismatches"] == [{"symbol": "VOO", "rebuilt": 0.0, "actual": 3}]

    # Deposit recorded with a negative amount (seed / some sources) still adds cash.
    r3 = build_account_timeline([t(date(2026, 1, 5), "DEPOSIT", -500.0)], closes, splits, {})
    assert r3["total_value"][0] == 500.0 and r3["invested"][0] == 500.0

    # Issue #404: DIV is gross with the withholding only in the description,
    # plus Firstrade's OTHER mirror of the same dividend on the margin side.
    div = t(date(2026, 1, 6), "DIV", 6.96, "MSFT")
    div["description"] = "MICROSOFT CORP CASH DIV ON 7.64539 SHS NON-RES TAX WITHHELD $2.09000"
    mirror = t(date(2026, 1, 6), "OTHER", 6.96, "MSFT")
    rebate = t(date(2026, 1, 6), "OTHER", 25.0)  # wire rebate: real cash, no symbol
    r4 = build_account_timeline(
        [t(date(2026, 1, 5), "DEPOSIT", 100.0), div, mirror, rebate], closes, splits, {"CASH": 129.87}
    )
    assert abs(r4["latest"]["cash"] - (100 + 6.96 - 2.09 + 25)) < 1e-9
    assert r4["warnings"]["cash_mismatch"] is None


if __name__ == "__main__":
    demo()
    print("OK")
