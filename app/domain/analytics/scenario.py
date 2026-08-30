"""Market-drop scenario: "if the market fell X%, how much would my
portfolio estimate to fall" - pure arithmetic off existing beta data, not
a prediction of whether/when a drop happens.

Uses the simplified linear estimate `holding_change ≈ beta × market_change`
(risk.py's beta vs SPY). Real drawdowns don't track beta perfectly,
especially in extreme moves - this is a back-of-envelope estimate, not a
forecast. CASH is assumed beta 0 (unaffected).
"""

from collections import defaultdict

from app.domain.analytics.risk import compute_risk_metrics


def simulate_market_drop(snapshots: list[dict], market_change: float) -> dict:
    value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        value_by_symbol[s["symbol"]] += s["market_value"]
    total = sum(value_by_symbol.values())
    if not total:
        return {"market_change": market_change, "portfolio_change": 0.0, "items": []}

    symbols = [s for s in value_by_symbol if s != "CASH"]
    risk_items = {item["symbol"]: item for item in compute_risk_metrics(symbols)} if symbols else {}

    items = []
    estimated_total_change = 0.0
    uncovered_symbols = []
    for symbol, value in value_by_symbol.items():
        beta = 0.0 if symbol == "CASH" else risk_items.get(symbol, {}).get("beta")
        estimated_change = beta * market_change if beta is not None else None
        # No beta -> no basis to estimate this symbol's move, so it
        # contributes $0 to the total change (same as if it were flat) -
        # surfaced via uncovered_symbols so the caller can disclose that
        # this understates the estimate, rather than silently implying beta=0.
        estimated_value_change = value * estimated_change if estimated_change is not None else 0.0
        if estimated_change is None:
            uncovered_symbols.append(symbol)
        estimated_total_change += estimated_value_change
        items.append(
            {
                "symbol": symbol,
                "current_value": value,
                "beta": beta,
                "estimated_change": estimated_change,
                "estimated_value_change": estimated_value_change,
            }
        )

    items.sort(key=lambda r: -r["current_value"])
    return {
        "market_change": market_change,
        "portfolio_change": estimated_total_change / total,
        "portfolio_value_change": estimated_total_change,
        "items": items,
        "uncovered_symbols": uncovered_symbols,
    }
