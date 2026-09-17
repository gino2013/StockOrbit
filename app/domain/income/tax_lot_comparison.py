"""Hypothetical "what if I sell N shares right now" comparison between two
lot-selection strategies - not a recommendation to actually use HIFO, and
not a claim Firstrade lets you pick lots on this app's behalf. Just shows
how much the realized gain/loss would differ depending on which shares get
sold, since that's a real, sizable tax difference many people don't realize
they could ask their broker for.
"""

FIFO = "fifo"  # oldest lot first - the IRS default, same convention realized_gains.py uses
HIFO = "hifo"  # highest-cost-basis lot first - minimizes realized gain / maximizes realized loss


def _consume(ordered_lots: list[dict], quantity: float, sale_price: float) -> dict:
    remaining = quantity
    cost = 0.0
    matched = 0.0
    for lot in ordered_lots:
        if remaining <= 1e-9:
            break
        take = min(lot["quantity"], remaining)
        cost += take * lot["price"]
        matched += take
        remaining -= take
    proceeds = matched * sale_price
    return {
        "matched_quantity": matched,
        "unmatched_quantity": remaining,
        "proceeds": proceeds,
        "cost_basis": cost,
        "gain": proceeds - cost,
    }


def compare_lot_selection(lots: list[dict], quantity: float, sale_price: float) -> dict:
    """`lots` is oldest-first (open_lots_by_symbol()'s own order) - used
    directly for FIFO, re-sorted by price descending for HIFO. A positive
    `unmatched_quantity` on either side means the request asked to sell more
    than is currently held."""
    fifo = _consume(lots, quantity, sale_price)
    hifo = _consume(sorted(lots, key=lambda lot: -lot["price"]), quantity, sale_price)
    return {FIFO: fifo, HIFO: hifo, "gain_difference": hifo["gain"] - fifo["gain"]}
