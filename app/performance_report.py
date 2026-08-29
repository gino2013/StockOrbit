"""Period performance report: portfolio return vs a benchmark, plus the
period's transactions and realized gains - all reused from existing
modules (app/holdings_history.py, app/realized_gains.py, app/xirr.py), no
new pricing logic. Meant to be paired with issue #48's browser-print PDF
export for a shareable monthly/yearly summary.
"""

from datetime import date

from app.holdings_history import close_prices, portfolio_value_history, weighted_return_series
from app.realized_gains import compute_realized_gains
from app.xirr import xirr

_TRADE_TYPES = ("BOUGHT", "SOLD")


def _holdings_as_of(transactions: list[dict], as_of: date) -> dict[str, float]:
    """Share count per symbol implied by BOUGHT/SOLD history up to (incl.)
    `as_of`. SOLD rows carry a negative quantity, so a plain sum works."""
    holdings: dict[str, float] = {}
    for t in transactions:
        if t["trans_type"] in _TRADE_TYPES and t["report_date"] <= as_of:
            holdings[t["symbol"]] = holdings.get(t["symbol"], 0.0) + t["quantity"]
    return {s: q for s, q in holdings.items() if abs(q) > 1e-9}


def _signed_cashflow(t: dict) -> float:
    """Actual net cash of a trade (negative = bought, positive = sold).
    Firstrade's `amount` already carries the sign and includes fees; fall
    back to quantity*price when a row is missing it."""
    return t["amount"] if t.get("amount") else -t["quantity"] * t["trade_price"]


def _period_money_weighted(transactions: list[dict], start: str, end: str) -> tuple[float | None, float | None]:
    """(period_xirr, period_pnl) - opening = holdings on `start` priced at
    `start`, then every BOUGHT/SOLD inside the window at its real date, then
    closing = holdings on `end` priced at `end`. Respects *when* you actually
    bought in, unlike period_return which assumes today's shares held all
    along. Returns (None, None) if it can't be reconstructed."""
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    open_h = _holdings_as_of(transactions, start_date)
    close_h = _holdings_as_of(transactions, end_date)
    symbols = sorted(set(open_h) | set(close_h))
    if not symbols:
        return None, None
    try:
        px = close_prices(symbols, start, end)
    except (ValueError, KeyError):
        return None, None
    opening = float(sum(q * px[s].iloc[0] for s, q in open_h.items()))
    closing = float(sum(q * px[s].iloc[-1] for s, q in close_h.items()))
    if opening <= 0:
        return None, None

    window_flows = [
        (t["report_date"], _signed_cashflow(t))
        for t in transactions
        if t["trans_type"] in _TRADE_TYPES and start_date <= t["report_date"] <= end_date
    ]
    flows = [(start_date, -opening), *window_flows, (end_date, closing)]
    pnl = closing - opening + sum(a for _, a in window_flows)
    return xirr(flows), pnl


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

    total_cost = sum(s.get("cost_basis", 0) or 0 for s in snapshots)
    total_value = sum(s.get("market_value", 0) or 0 for s in snapshots)
    since_purchase_return = (total_value - total_cost) / total_cost if total_cost else None

    period_xirr, period_pnl = _period_money_weighted(transactions, start, end)

    return {
        "start": start,
        "end": end,
        "start_value": float(value_series.iloc[0]),
        "end_value": float(value_series.iloc[-1]),
        "period_return": float(period_return),
        "benchmark_return": float(benchmark_return),
        "since_purchase_return": since_purchase_return,
        "period_xirr": period_xirr,
        "period_pnl": period_pnl,
        "realized_gain": realized_gain,
        "realized_trade_count": len(period_realized),
        "transactions": period_transactions,
    }
