"""Rule-based allocation advice. Not a financial model - just concentration
and drift-from-target heuristics computed off the latest holdings snapshot.
"""

from collections import defaultdict


def compute_allocation(snapshots: list[dict]) -> dict[str, float]:
    total = sum(s["market_value"] for s in snapshots) or 1
    by_symbol = defaultdict(float)
    for s in snapshots:
        by_symbol[s["symbol"]] += s["market_value"]
    return {symbol: value / total for symbol, value in by_symbol.items()}


def build_advice(
    snapshots: list[dict],
    targets: dict[str, float],
    concentration_threshold: float = 0.20,
    drift_threshold: float = 0.05,
    cash_threshold: float = 0.15,
    min_positions: int = 3,
    max_positions: int = 30,
    sector_concentration_threshold: float = 0.50,
    sector_allocation: dict[str, float] | None = None,
) -> dict:
    allocation = compute_allocation(snapshots)
    total_value = sum(s["market_value"] for s in snapshots)
    notes = []

    for symbol, weight in sorted(allocation.items(), key=lambda kv: -kv[1]):
        if symbol == "CASH":
            continue  # holding cash isn't a concentration risk
        if weight > concentration_threshold:
            notes.append(
                f"{symbol} 佔投資組合 {weight:.1%}，超過集中度門檻 "
                f"{concentration_threshold:.0%}，建議考慮減碼分散風險。"
            )

    for symbol, target in targets.items():
        current = allocation.get(symbol, 0)
        drift = current - target
        if abs(drift) > drift_threshold:
            action = "減碼" if drift > 0 else "加碼"
            notes.append(
                f"{symbol} 目前配置 {current:.1%}，目標 {target:.1%}，"
                f"偏離 {abs(drift):.1%}，建議{action}以回到目標配置。"
            )

    # Held but never given a target at all (distinct from "target is 0%") -
    # build_rebalance_plan() silently treats these as a full-sell candidate,
    # which is easy to not realize unless it's called out here.
    untargeted = sorted(
        symbol
        for symbol in allocation
        if symbol != "CASH" and symbol not in targets and allocation[symbol] > 0
    )
    if untargeted:
        notes.append(
            f"{'、'.join(untargeted)} 目前有持有但沒有設定目標配置，"
            "再平衡建議金額會把它們當成目標 0%（全數賣出），建議設定目標或確認這是你要的結果。"
        )

    cash_weight = allocation.get("CASH", 0)
    if cash_weight > cash_threshold:
        notes.append(
            f"現金佔投資組合 {cash_weight:.1%}，超過 {cash_threshold:.0%}，"
            "建議考慮部署到目標配置中的標的，避免現金拖累報酬。"
        )

    position_count = sum(1 for symbol in allocation if symbol != "CASH")
    if 0 < position_count < min_positions:
        notes.append(f"目前只有 {position_count} 檔持股，集中度風險較高，建議增加持股數量分散風險。")
    elif position_count > max_positions:
        notes.append(f"目前有 {position_count} 檔持股，數量偏多，可能難以有效追蹤管理，建議考慮精簡。")

    if sector_allocation:
        sector_total = sum(sector_allocation.values()) or 1
        for sector, value in sorted(sector_allocation.items(), key=lambda kv: -kv[1]):
            if sector in ("CASH", "ETF"):
                continue
            weight = value / sector_total
            if weight > sector_concentration_threshold:
                notes.append(
                    f"{sector} 類股佔投資組合 {weight:.1%}，超過產業集中度門檻 "
                    f"{sector_concentration_threshold:.0%}，建議留意產業分散。"
                )

    if not notes:
        notes.append("目前配置在門檻範圍內，沒有明顯建議調整項目。")

    return {"allocation": allocation, "total_value": total_value, "advice": notes}


def build_rebalance_plan(
    snapshots: list[dict],
    targets: dict[str, float],
    extra_cash: float = 0.0,
    include_cash: bool = False,
    keep: frozenset[str] = frozenset(),
) -> list[dict]:
    """For every symbol that's either currently held or has a target weight
    (excluding CASH, which is funding source/destination, not a position),
    work out how many dollars to buy or sell to hit the target allocation.
    A held symbol with no target is treated as target 0% (full sell) -
    it's not part of the plan, so rebalancing it out is the correct call.

    `extra_cash` folds new money (e.g. "只有一筆閒置現金" - issue #340) into
    the total before computing targets, so the plan lands exactly on target
    including the new cash - not just buy-only. `current_weight` still uses
    the pre-cash total (today's actual allocation), everything else uses
    the post-cash total.

    `include_cash` adds a CASH row for cash already held (issue #368). The
    total includes that cash and targets sum to 100%, so without the row
    the current weights don't add up and the cash is spent invisibly.

    `keep` (issues #370, #374): symbols left completely untouched - frozen at
    their current value, neither bought nor sold; everyone else splits the
    remaining total in proportion to their target weights, so the overall mix
    lands as close to target as the constraint allows.
    """
    total_value = sum(s["market_value"] for s in snapshots)
    new_total = total_value + extra_cash
    current_value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        if include_cash or s["symbol"] != "CASH":
            current_value_by_symbol[s["symbol"]] += s["market_value"]

    symbols = sorted(set(current_value_by_symbol) | set(targets))
    # Kept symbols are frozen at their current value (no buy, no sell); the
    # rest split what's left in proportion to their target weights.
    frozen = {x for x in symbols if x in keep}
    budget = new_total - sum(current_value_by_symbol.get(f, 0.0) for f in frozen)
    free_weight = sum(targets.get(x, 0.0) for x in symbols if x not in frozen)
    scale = budget / free_weight if free_weight else 0.0

    plan = []
    for symbol in symbols:
        current_value = current_value_by_symbol.get(symbol, 0.0)
        target_weight = targets.get(symbol, 0.0)
        target_value = current_value if symbol in frozen else target_weight * scale
        plan.append({
            "symbol": symbol,
            "current_value": current_value,
            "current_weight": (current_value / total_value) if total_value else 0.0,
            "target_weight": target_weight,
            "target_value": target_value,
            "diff": target_value - current_value,
        })
    return sorted(plan, key=lambda p: -abs(p["diff"]))
