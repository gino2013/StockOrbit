"""Dividend income summary from already-synced DIV transactions (see #11) -
no separate fetch needed, Firstrade's account history already includes them.
"""

from collections import defaultdict
from datetime import date, timedelta


def trailing_twelve_month_dividends(transactions: list[dict], as_of: date) -> list[dict]:
    """Per-symbol dividend total over the trailing 12 months, paired with
    current market value (if held) to estimate a trailing yield. Symbols no
    longer held still show their dividend total, just no yield %.
    """
    window_start = as_of - timedelta(days=365)
    totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t["trans_type"] != "DIV" or not t.get("symbol"):
            continue
        if window_start <= t["report_date"] <= as_of:
            totals[t["symbol"]] += t["amount"]
    return [{"symbol": symbol, "ttm_dividends": total} for symbol, total in totals.items()]


def with_yield(ttm_rows: list[dict], market_value_by_symbol: dict[str, float]) -> list[dict]:
    rows = []
    for row in ttm_rows:
        market_value = market_value_by_symbol.get(row["symbol"])
        yield_pct = (row["ttm_dividends"] / market_value) if market_value else None
        rows.append({**row, "market_value": market_value, "ttm_yield": yield_pct})
    return sorted(rows, key=lambda r: -r["ttm_dividends"])


def forecast_dividend_calendar(transactions: list[dict], as_of: date, months_ahead: int = 12) -> list[dict]:
    """Project the next `months_ahead` calendar months' likely dividend
    payments, per symbol, from the historical month-of-year pattern of past
    DIV transactions - e.g. a symbol that has always paid in March/June/
    Sept/Dec is assumed to keep doing so. Amount is the most recent actual
    payment seen in that calendar month (reflects current holding size
    better than an all-time average). This is a projection from history,
    not an official payment schedule - amounts/dates can and do change.
    """
    by_symbol_month: dict[tuple[str, int], list[tuple[date, float]]] = defaultdict(list)
    for t in transactions:
        if t["trans_type"] != "DIV" or not t.get("symbol"):
            continue
        by_symbol_month[(t["symbol"], t["report_date"].month)].append((t["report_date"], t["amount"]))

    forecast = []
    for i in range(months_ahead):
        target_month = (as_of.month - 1 + i) % 12 + 1
        target_year = as_of.year + (as_of.month - 1 + i) // 12
        for (symbol, month), payments in by_symbol_month.items():
            if month != target_month:
                continue
            latest_amount = max(payments, key=lambda p: p[0])[1]
            forecast.append({
                "year": target_year, "month": target_month, "symbol": symbol,
                "estimated_amount": latest_amount,
            })
    return sorted(forecast, key=lambda f: (f["year"], f["month"], f["symbol"]))
