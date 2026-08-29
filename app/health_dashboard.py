"""Single-card rollup of risk/concentration indicators that otherwise live
scattered across several sections (risk, correlation, risk-parity). No new
calculation logic - just aggregates the existing functions' output into a
handful of headline numbers. Objective data only, no verdict.
"""

from collections import defaultdict

from app.correlation import compute_correlation_matrix
from app.risk import compute_risk_metrics


def build_health_overview(snapshots: list[dict]) -> dict:
    value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        value_by_symbol[s["symbol"]] += s["market_value"]
    total = sum(value_by_symbol.values())
    symbols = [s for s in value_by_symbol if s != "CASH"]

    max_concentration = max((value_by_symbol[s] / total for s in symbols), default=0.0) if total else 0.0

    corr = compute_correlation_matrix(symbols) if len(symbols) >= 2 else {"symbols": [], "matrix": []}
    off_diagonal = [
        corr["matrix"][i][j] for i in range(len(corr["symbols"])) for j in range(len(corr["symbols"])) if i != j
    ]
    avg_correlation = sum(off_diagonal) / len(off_diagonal) if off_diagonal else None

    risk_items = {item["symbol"]: item for item in compute_risk_metrics(symbols)} if symbols else {}
    beta_terms = [
        (value_by_symbol[s] / total) * risk_items[s]["beta"]
        for s in symbols
        if total and s in risk_items and risk_items[s]["beta"] is not None
    ]
    portfolio_beta = sum(beta_terms) if beta_terms else None

    return {
        "position_count": len(symbols),
        "max_concentration": max_concentration,
        "avg_correlation": avg_correlation,
        "portfolio_beta": portfolio_beta,
    }
