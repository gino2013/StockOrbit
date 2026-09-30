"""How to invest a lump of new cash toward closing the gap to target
allocation, without selling anything except positions explicitly zeroed out
- a lighter alternative to the full buy-and-sell rebalance plan for when you
just have idle cash to put to work.
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

    # A target set to exactly 0 means "get out of this position" (issue
    # #336 followup) - sell it entirely and fold the proceeds into the pool
    # being deployed, rather than just excluding it from buys like every
    # other already-at-target symbol. Doesn't change new_total: the sold
    # value moves into other symbols, it doesn't leave the tracked total.
    zero_target_symbols = {symbol for symbol, weight in targets.items() if weight == 0}
    sell_proceeds = sum(current_value_by_symbol.get(symbol, 0.0) for symbol in zero_target_symbols)
    deployable = cash_amount + sell_proceeds
    buy_targets = {symbol: weight for symbol, weight in targets.items() if weight > 0}

    # How far below target each symbol sits, evaluated against the total
    # *after* this cash goes in - buying doesn't just fill today's gap, it
    # also grows the pie every other symbol's target share is measured
    # against. Symbols already at/above target get 0, never a sell.
    deficits = {}
    for symbol, target_weight in buy_targets.items():
        target_value = target_weight * new_total
        deficits[symbol] = max(0.0, target_value - current_value_by_symbol.get(symbol, 0.0))

    total_deficit = sum(deficits.values())
    if total_deficit <= deployable:
        # Enough to close every gap exactly; split whatever's left over by
        # target weight so the full deployable amount is always allocated.
        leftover = deployable - total_deficit
        total_target_weight = sum(buy_targets.values()) or 1
        buys = {
            symbol: deficits[symbol] + leftover * (buy_targets[symbol] / total_target_weight)
            for symbol in buy_targets
        }
    else:
        # Not enough to close every gap; prioritize the most-underweight
        # symbols by splitting proportionally to each one's deficit size.
        buys = {symbol: deployable * (deficit / total_deficit) for symbol, deficit in deficits.items()}

    # Every targeted symbol is included - even a $0 buy - because growing
    # new_total dilutes everyone's weight a little, not just the symbols
    # that got cash. The resulting new_weight lets the caller see exactly
    # how close (or not) this gets to target, rather than assuming a
    # buy-only pass lands exactly on it.
    plan = []
    for symbol, target_weight in targets.items():
        current_value = current_value_by_symbol.get(symbol, 0.0)
        buy_amount = -current_value if symbol in zero_target_symbols else buys.get(symbol, 0.0)
        new_value = current_value + buy_amount
        plan.append(
            {
                "symbol": symbol,
                "current_value": current_value,
                "current_weight": (current_value / current_total) if current_total else 0.0,
                "buy_amount": buy_amount,
                "new_value": new_value,
                "new_weight": (new_value / new_total) if new_total else 0.0,
                "target_weight": target_weight,
            }
        )
    return sorted(plan, key=lambda p: -p["buy_amount"])
