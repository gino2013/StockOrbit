"""Simplified risk-parity allocation suggestion: weight each held symbol
inversely to its historical volatility (from risk.py) instead of by market
value, so a volatile symbol gets suggested a smaller share, and a calmer
one a bigger share. This is one of many valid ways to build a "risk parity"
portfolio, not the only correct answer - just historical volatility fed
back into a 1/vol weighting, not investment advice.

CASH has no volatility to weight by, so its current weight is left as-is
and the risk-parity weights are only redistributed across the non-cash
holdings, scaled to fill the remaining (1 - cash_weight) share.
"""

from collections import defaultdict

from app.risk import compute_risk_metrics


def suggest_risk_parity(snapshots: list[dict]) -> list[dict]:
    value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        value_by_symbol[s["symbol"]] += s["market_value"]
    total = sum(value_by_symbol.values())
    if not total:
        return []

    cash_weight = value_by_symbol.get("CASH", 0.0) / total
    symbols = [s for s in value_by_symbol if s != "CASH"]
    if not symbols:
        return []

    risk_items = {item["symbol"]: item for item in compute_risk_metrics(symbols)}
    inv_vol = {}
    for symbol in symbols:
        vol = risk_items.get(symbol, {}).get("volatility_90d")
        if vol:
            inv_vol[symbol] = 1 / vol

    inv_vol_total = sum(inv_vol.values())
    non_cash_share = 1 - cash_weight

    result = []
    for symbol in symbols:
        suggested = (
            non_cash_share * (inv_vol[symbol] / inv_vol_total) if symbol in inv_vol and inv_vol_total else None
        )
        result.append(
            {
                "symbol": symbol,
                "current_weight": value_by_symbol[symbol] / total,
                "volatility_90d": risk_items.get(symbol, {}).get("volatility_90d"),
                "suggested_weight": suggested,
            }
        )
    return sorted(result, key=lambda r: -r["current_weight"])
