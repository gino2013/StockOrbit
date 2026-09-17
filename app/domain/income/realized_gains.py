"""FIFO realized-gain calculation from BOUGHT/SOLD transaction history.

FIFO (first lot bought is the first lot sold) is the IRS default method for
individual investors who haven't elected otherwise, so it's a reasonable
default here too - not a tax-advice claim, just the calculation convention.
"""

from collections import defaultdict, deque


def _match_fifo(transactions: list[dict]) -> tuple[list[dict], dict[str, deque]]:
    """Shared matching pass behind compute_realized_gains() and
    open_lots_by_symbol() - one FIFO sweep produces both "what was already
    realized" and "what's left over" (the deques are mutated in place as
    lots get consumed, so whatever remains at the end is what's still
    held)."""
    trades = [t for t in transactions if t["trans_type"] in ("BOUGHT", "SOLD") and t.get("symbol")]
    # Secondary key: a BOUGHT sorts before a SOLD on the same date, so a
    # same-day round trip matches its own purchase rather than older lots
    # (or going unmatched when there are none). report_date has no time.
    trades.sort(key=lambda t: (t["report_date"], 0 if t["trans_type"] == "BOUGHT" else 1))

    lots: dict[str, deque] = defaultdict(deque)  # symbol -> deque of [qty_remaining, price, buy_date]
    realized = []
    for t in trades:
        symbol = t["symbol"]
        qty = abs(t["quantity"])
        price = t["trade_price"]
        if t["trans_type"] == "BOUGHT":
            lots[symbol].append([qty, price, t["report_date"]])
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
        # Only count proceeds for the shares we could FIFO-match. With
        # `remaining == 0` (the normal case) this is just qty * price;
        # when we sold more than our BOUGHT history covers, the unmatched
        # shares drop out of proceeds too, so `gain` stays a like-for-like
        # matched figure instead of full proceeds minus a partial cost.
        matched_qty = qty - remaining
        proceeds = matched_qty * price
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
    return realized, lots


def compute_realized_gains(transactions: list[dict]) -> list[dict]:
    """One row per SOLD transaction with its FIFO-matched cost basis and gain,
    sorted by date. `unmatched_quantity` > 0 means we sold more than our
    BOUGHT history accounts for (e.g. a lot bought before our history starts)
    - that portion is dropped from *both* cost basis and proceeds, so the
    row's `gain` reflects only the shares we could actually cost, not a
    guessed figure and not full proceeds against a partial cost.
    """
    realized, _ = _match_fifo(transactions)
    return realized


def open_lots_by_symbol(transactions: list[dict]) -> dict[str, list[dict]]:
    """Currently-held lots (FIFO-remaining, oldest first) per symbol, as of
    the end of the given transaction history - the batches a "sell N
    shares" decision would actually be choosing between (issue #295).
    Symbols fully sold out (or never bought) don't appear."""
    _, lots = _match_fifo(transactions)
    return {
        symbol: [{"buy_date": buy_date, "quantity": qty, "price": price} for qty, price, buy_date in lot_deque]
        for symbol, lot_deque in lots.items()
        if lot_deque
    }


def summarize_realized_gains(realized: list[dict], year: int | None = None) -> dict:
    rows = [r for r in realized if year is None or r["report_date"].year == year]
    return {
        "total_gain": sum(r["gain"] for r in rows),
        "total_proceeds": sum(r["proceeds"] for r in rows),
        "trade_count": len(rows),
        "has_unmatched": any(r["unmatched_quantity"] > 1e-6 for r in rows),
    }
