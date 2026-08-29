"""FIFO realized-gain calculation from BOUGHT/SOLD transaction history.

FIFO (first lot bought is the first lot sold) is the IRS default method for
individual investors who haven't elected otherwise, so it's a reasonable
default here too - not a tax-advice claim, just the calculation convention.
"""

from collections import defaultdict, deque


def compute_realized_gains(transactions: list[dict]) -> list[dict]:
    """One row per SOLD transaction with its FIFO-matched cost basis and gain,
    sorted by date. `unmatched_quantity` > 0 means we sold more than our
    BOUGHT history accounts for (e.g. a lot bought before our history starts)
    - that portion's cost basis is left out rather than guessed at, so the
    gain for that row is understated, not fabricated.
    """
    trades = [t for t in transactions if t["trans_type"] in ("BOUGHT", "SOLD") and t.get("symbol")]
    trades.sort(key=lambda t: t["report_date"])

    lots: dict[str, deque] = defaultdict(deque)  # symbol -> deque of [qty_remaining, price]
    realized = []
    for t in trades:
        symbol = t["symbol"]
        qty = abs(t["quantity"])
        price = t["trade_price"]
        if t["trans_type"] == "BOUGHT":
            lots[symbol].append([qty, price])
            continue

        remaining = qty
        cost = 0.0
        while remaining > 1e-9 and lots[symbol]:
            lot = lots[symbol][0]
            take = min(lot[0], remaining)
            cost += take * lot[1]
            lot[0] -= take
            remaining -= take
            if lot[0] <= 1e-9:
                lots[symbol].popleft()
        proceeds = qty * price
        realized.append(
            {
                "symbol": symbol,
                "report_date": t["report_date"],
                "quantity": qty,
                "proceeds": proceeds,
                "cost_basis": cost,
                "gain": proceeds - cost,
                "unmatched_quantity": remaining,
            }
        )
    return realized


def summarize_realized_gains(realized: list[dict], year: int | None = None) -> dict:
    rows = [r for r in realized if year is None or r["report_date"].year == year]
    return {
        "total_gain": sum(r["gain"] for r in rows),
        "total_proceeds": sum(r["proceeds"] for r in rows),
        "trade_count": len(rows),
        "has_unmatched": any(r["unmatched_quantity"] > 1e-6 for r in rows),
    }
