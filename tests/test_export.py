import csv
import io
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.export import build_holdings_csv


def demo():
    snapshots = [
        {"symbol": "AAPL", "quantity": 10, "cost_basis": 1000, "price": 120, "market_value": 1200},
        {"symbol": "CASH", "quantity": 1, "cost_basis": 50, "price": 50, "market_value": 50},
    ]
    allocation = {"AAPL": 1200 / 1250, "CASH": 50 / 1250}
    targets = {"AAPL": 1.0}
    advice_notes = ["AAPL 佔投資組合 96.0%，建議考慮減碼分散風險。"]

    csv_text = build_holdings_csv(snapshots, allocation, targets, advice_notes, as_of=date(2026, 8, 27))
    rows = list(csv.reader(io.StringIO(csv_text)))

    assert rows[0] == ["StockOrbit 持股匯出", "2026-08-27"]
    header_idx = rows.index(["代號", "股數", "買入均價", "現價", "市值", "目前佔比", "目標佔比"])
    aapl_row = rows[header_idx + 1]
    assert aapl_row[0] == "AAPL"
    assert aapl_row[1] == "10"
    assert aapl_row[2] == "100.0"  # avg cost = 1000/10
    assert aapl_row[6] == "100%"  # has a target
    cash_row = rows[header_idx + 2]
    assert cash_row[0] == "CASH"
    assert cash_row[6] == ""  # no target set -> blank, not "0%"

    advice_idx = rows.index(["建議"])
    assert rows[advice_idx + 1] == [advice_notes[0]]


if __name__ == "__main__":
    demo()
    print("OK")
