import csv
import io
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.export import build_holdings_csv, build_transactions_csv


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

    transactions = [
        {"report_date": date(2026, 1, 5), "trans_type": "BOUGHT", "symbol": "AAPL", "quantity": 10, "trade_price": 100.0, "amount": -1000.0},
        {"report_date": date(2026, 3, 1), "trans_type": "SOLD", "symbol": "AAPL", "quantity": -4, "trade_price": 150.0, "amount": 600.0},
        {"report_date": date(2026, 1, 1), "trans_type": "DEPOSIT", "symbol": None, "quantity": 0, "trade_price": 0, "amount": 2000.0},
    ]
    realized = [
        {"report_date": date(2026, 3, 1), "symbol": "AAPL", "quantity": 4, "proceeds": 600.0, "cost_basis": 400.0, "gain": 200.0, "unmatched_quantity": 0},
    ]
    tx_csv = build_transactions_csv(transactions, realized, as_of=date(2026, 8, 27))
    tx_rows = list(csv.reader(io.StringIO(tx_csv)))

    assert tx_rows[0] == ["StockOrbit 交易紀錄匯出", "2026-08-27"]
    tx_header_idx = tx_rows.index(["日期", "類型", "代號", "股數", "價格", "金額"])
    # sorted by date -> the 2026-01-01 deposit comes first even though it was last in the input list
    assert tx_rows[tx_header_idx + 1][0] == "2026-01-01"
    assert tx_rows[tx_header_idx + 1][2] == ""  # no symbol for a deposit -> blank, not "None"

    realized_idx = tx_rows.index(["已實現損益明細（FIFO）"])
    realized_header = tx_rows[realized_idx + 1]
    assert realized_header == ["日期", "代號", "股數", "賣出金額", "成本", "損益", "未匹配股數"]
    realized_row = tx_rows[realized_idx + 2]
    assert realized_row[1] == "AAPL"
    assert realized_row[5] == "200.0"  # gain


if __name__ == "__main__":
    demo()
    print("OK")
