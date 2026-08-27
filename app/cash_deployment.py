"""How to invest a lump of new cash toward closing the gap to target
allocation, without selling anything — a lighter alternative to the full
buy-and-sell rebalance plan for when you just have idle cash to put to work.
"""

from collections import defaultdict


def suggest_cash_deployment(snapshots: list[dict], targets: dict[str, float], cash_amount: float) -> list[dict]:
    if cash_amount <= 0 or not targets:
        return []

    current_value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        if s["symbol"] != "CASH":
            current_value_by_symbol[s["symbol"]] += s["market_value"]
    current_total = sum(current_value_by_symbol.values())
    new_total = current_total + cash_amount

    # How far below target each symbol sits, evaluated against the total
    # *after* this cash goes in — buying doesn't just fill today's gap, it
    # also grows the pie every other symbol's target share is measured
    # against. Symbols already at/above target get 0, never a sell.
    deficits = {}
    for symbol, target_weight in targets.items():
        target_value = target_weight * new_total
        deficits[symbol] = max(0.0, target_value - current_value_by_symbol.get(symbol, 0.0))

    total_deficit = sum(deficits.values())
    if total_deficit <= cash_amount:
        # Enough to close every gap exactly; split whatever's left over by
        # target weight so the full cash_amount is always allocated.
        leftover = cash_amount - total_deficit
        total_target_weight = sum(targets.values()) or 1
        buys = {
            symbol: deficits[symbol] + leftover * (targets[symbol] / total_target_weight)
            for symbol in targets
        }
    else:
        # Not enough to close every gap; prioritize the most-underweight
        # symbols by splitting proportionally to each one's deficit size.
        buys = {symbol: cash_amount * (deficit / total_deficit) for symbol, deficit in deficits.items()}

    plan = [
        {
            "symbol": symbol,
            "current_value": current_value_by_symbol.get(symbol, 0.0),
            "buy_amount": amount,
        }
        for symbol, amount in buys.items()
        if amount > 0.01
    ]
    return sorted(plan, key=lambda p: -p["buy_amount"])
