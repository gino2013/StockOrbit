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
