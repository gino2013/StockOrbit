"""CSV export of the current holdings + advice snapshot, for keeping a
dated record or sharing outside the app. Plain rows, no styling — a
spreadsheet app is the intended consumer, not a human reading raw text.
"""

import csv
import io
from datetime import date


def build_holdings_csv(
    snapshots: list[dict],
    allocation: dict[str, float],
    targets: dict[str, float],
    advice_notes: list[str],
    as_of: date,
) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["StockOrbit 持股匯出", as_of.isoformat()])
    writer.writerow([])
    writer.writerow(["代號", "股數", "買入均價", "現價", "市值", "目前佔比", "目標佔比"])
    for s in snapshots:
        avg_cost = (s["cost_basis"] / s["quantity"]) if s["quantity"] else 0
        symbol = s["symbol"]
        writer.writerow([
            symbol,
            s["quantity"],
            round(avg_cost, 2),
            s["price"],
            round(s["market_value"], 2),
            f"{allocation.get(symbol, 0) * 100:.1f}%",
            f"{targets[symbol] * 100:.0f}%" if symbol in targets else "",
        ])

    writer.writerow([])
    writer.writerow(["建議"])
    for note in advice_notes:
        writer.writerow([note])

    return buf.getvalue()


def build_transactions_csv(transactions: list[dict], realized: list[dict], as_of: date) -> str:
    """Full transaction history (issue #11's Transaction table) plus FIFO
    realized-gain detail (app/realized_gains.py), as two sections of one
    CSV — same shape as build_holdings_csv's advice-notes section below
    the main table."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["StockOrbit 交易紀錄匯出", as_of.isoformat()])
    writer.writerow([])
    writer.writerow(["日期", "類型", "代號", "股數", "價格", "金額"])
    for t in sorted(transactions, key=lambda t: t["report_date"]):
        writer.writerow([
            t["report_date"].isoformat(),
            t["trans_type"],
            t.get("symbol") or "",
            t["quantity"],
            t["trade_price"],
            round(t["amount"], 2),
        ])

    writer.writerow([])
    writer.writerow(["已實現損益明細（FIFO）"])
    writer.writerow(["日期", "代號", "股數", "賣出金額", "成本", "損益", "未匹配股數"])
    for r in realized:
        writer.writerow([
            r["report_date"].isoformat(),
            r["symbol"],
            r["quantity"],
            round(r["proceeds"], 2),
            round(r["cost_basis"], 2),
            round(r["gain"], 2),
            r["unmatched_quantity"],
        ])

    return buf.getvalue()
