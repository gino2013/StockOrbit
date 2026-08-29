"""Period performance report: portfolio return vs a benchmark, plus the
period's transactions and realized gains - all reused from existing
modules (app/holdings_history.py, app/realized_gains.py), no new
calculation logic. Meant to be paired with issue #48's browser-print PDF
export for a shareable monthly/yearly summary.
"""

from datetime import date

from app.holdings_history import portfolio_value_history, weighted_return_series
from app.realized_gains import compute_realized_gains


def build_performance_report(
    snapshots: list[dict],
    transactions: list[dict],
    start: str,
    end: str,
    benchmark_weights: dict[str, float] | None = None,
) -> dict:
    holdings = {s["symbol"]: s["quantity"] for s in snapshots if s["symbol"] != "CASH"}
    if not holdings:
        raise ValueError("目前沒有持股，無法產生報告")

    value_series = portfolio_value_history(holdings, start, end)
    period_return = value_series.iloc[-1] / value_series.iloc[0] - 1

    benchmark_weights = benchmark_weights or {"SPY": 1.0}
    benchmark_series = weighted_return_series(benchmark_weights, start, end)
    benchmark_return = benchmark_series.iloc[-1] / benchmark_series.iloc[0] - 1

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    period_transactions = sorted(
        (t for t in transactions if start_date <= t["report_date"] <= end_date),
        key=lambda t: t["report_date"],
    )

    realized = compute_realized_gains(transactions)
    period_realized = [r for r in realized if start_date <= r["report_date"] <= end_date]
    realized_gain = sum(r["gain"] for r in period_realized)

    return {
        "start": start,
        "end": end,
        "start_value": float(value_series.iloc[0]),
        "end_value": float(value_series.iloc[-1]),
        "period_return": float(period_return),
        "benchmark_return": float(benchmark_return),
        "realized_gain": realized_gain,
        "realized_trade_count": len(period_realized),
        "transactions": period_transactions,
    }
