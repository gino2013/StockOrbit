"""Brinson performance attribution: how much of the return gap between
your current portfolio and your own target allocation (`TargetAllocation`)
comes from being over/underweight a symbol, vs from picking different
stocks (issue #291).

The classic Brinson model splits a portfolio's return gap against a
benchmark into Allocation / Selection / Interaction effects, where
Selection effect captures picking better-performing stocks than the
benchmark's *different* stock picks in the same sector. Here there is no
separate benchmark universe of picks - the "benchmark" is your own target
weights over the exact same symbols you actually hold. That collapses the
model in a specific, provable way: a symbol's return is the same number
whether it's weighted by wi (current) or wbi (target), so ri == rbi for
every symbol, which makes Selection effect and Interaction effect exactly
zero (not "usually small" - identically zero, by construction) and puts
the entire return gap into Allocation effect. This is a legitimate answer
to "is deviating from my own target plan helping or hurting", not the
sector-rotation story institutional Brinson tells against a market index.
This resolves the benchmark-definition question the issue raised before
allowing implementation.

- wi  = current weight (market value / total, CASH excluded)
- wbi = target weight (TargetAllocation; a symbol with no target = 0;
        a target symbol not currently held = 0 current weight)
- ri = rbi = the symbol's own price return over the period
- Allocation effect = sum (wi - wbi) * rbi
- Selection effect  = sum wbi * (ri - rbi)          = 0
- Interaction       = sum (wi - wbi) * (ri - rbi)   = 0
"""

from app.domain.analytics.holdings_history import close_prices


def compute_attribution(snapshots: list[dict], targets: dict[str, float], start: str, end: str) -> dict:
    value_by_symbol: dict[str, float] = {}
    for s in snapshots:
        if s["symbol"] != "CASH":
            value_by_symbol[s["symbol"]] = value_by_symbol.get(s["symbol"], 0.0) + s["market_value"]
    total = sum(value_by_symbol.values())
    if not total:
        return {
            "items": [],
            "allocation_effect": 0.0,
            "selection_effect": 0.0,
            "interaction_effect": 0.0,
            "total_effect": 0.0,
        }

    symbols = sorted(set(value_by_symbol) | set(targets))
    prices = close_prices(symbols, start, end)

    items = []
    allocation_effect = 0.0
    for symbol in symbols:
        wi = value_by_symbol.get(symbol, 0.0) / total
        wbi = targets.get(symbol, 0.0)
        ri = float(prices[symbol].iloc[-1] / prices[symbol].iloc[0] - 1)
        contribution = (wi - wbi) * ri
        allocation_effect += contribution
        items.append(
            {
                "symbol": symbol,
                "current_weight": wi,
                "target_weight": wbi,
                "return": ri,
                "allocation_contribution": contribution,
            }
        )

    return {
        "items": sorted(items, key=lambda i: -abs(i["allocation_contribution"])),
        "allocation_effect": allocation_effect,
        "selection_effect": 0.0,
        "interaction_effect": 0.0,
        "total_effect": allocation_effect,
    }
