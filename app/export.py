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
