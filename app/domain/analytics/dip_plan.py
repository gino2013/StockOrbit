"""Buy-the-dip plan (issue #439): a budget split into tiers that trigger at
set distances below the symbol's all-time high. Written down in advance so
a crash is a checklist, not a decision. Pure math on a close series."""

import pandas as pd

from app.domain.analytics.steady import forward_stats

DEFAULT_TIERS = [(-0.10, 0.25), (-0.20, 0.35), (-0.30, 0.40)]


def validate_tiers(tiers: list[tuple[float, float]]) -> str | None:
    """Error message, or None if the tiers make sense."""
    if not tiers:
        return "至少要有一個階段"
    if any(not -0.95 <= t < 0 for t, _ in tiers):
        return "觸發跌幅要介於 -95% 到 0% 之間"
    if any(b >= a for (a, _), (b, _) in zip(tiers, tiers[1:])):
        return "階段的跌幅要一階比一階深"
    if any(p <= 0 for _, p in tiers):
        return "每階投入比例要大於 0"
    if sum(p for _, p in tiers) > 1 + 1e-9:
        return "各階投入比例加起來不能超過 100%"
    return None


def dip_plan(closes: pd.Series, budget: float, tiers: list[tuple[float, float]],
             held_qty: float = 0.0, held_cost: float = 0.0) -> dict:
    closes = closes.dropna()
    high = float(closes.max())
    price = float(closes.iloc[-1])
    dd_series = closes / closes.cummax() - 1
    drawdown = price / high - 1
    rows = []
    for threshold, pct in tiers:
        trigger = high * (1 + threshold)
        amount = budget * pct
        rows.append({
            "threshold": threshold,
            "pct": pct,
            "trigger_price": trigger,
            "amount": amount,
            "shares": amount / trigger,
            "reached": drawdown <= threshold,
            # how much further it has to fall from today to get there
            "to_go": trigger / price - 1,
            "forward_1y": forward_stats(closes, dd_series <= threshold, 252),
        })
    new_amount = sum(r["amount"] for r in rows)
    new_shares = sum(r["shares"] for r in rows)
    return {
        "price": price,
        "high": high,
        "drawdown": drawdown,
        "tiers": rows,
        "unallocated": budget - new_amount,
        "avg_cost_now": held_cost / held_qty if held_qty else None,
        "avg_cost_after": (held_cost + new_amount) / (held_qty + new_shares) if held_qty + new_shares else None,
    }
