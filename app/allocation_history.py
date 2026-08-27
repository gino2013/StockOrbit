"""Allocation-percentage time series from the append-only PositionSnapshot
history already being recorded on every refresh — no new data collection,
just a different view of what's already stored.
"""

from collections import defaultdict


def allocation_history(snapshot_rows: list[dict]) -> list[dict]:
    """snapshot_rows: flat list of {snapshot_at, symbol, market_value} across
    all historical snapshots. Returns one row per snapshot_at:
    {snapshot_at, weights: {symbol: weight}}, sorted chronologically.
    """
    by_time: dict = defaultdict(list)
    for row in snapshot_rows:
        by_time[row["snapshot_at"]].append(row)

    result = []
    for snapshot_at in sorted(by_time):
        rows = by_time[snapshot_at]
        total = sum(r["market_value"] for r in rows) or 1
        weights = {r["symbol"]: r["market_value"] / total for r in rows}
        result.append({"snapshot_at": snapshot_at, "weights": weights})
    return result


def chart_series(history: list[dict]) -> dict:
    """Shape convenient for a Chart.js stacked area chart: one aligned series
    per symbol (0 for time points where it wasn't held), rather than sparse
    per-snapshot dicts the chart would have to fill in itself.
    """
    labels = [h["snapshot_at"].isoformat() for h in history]
    symbols = sorted({symbol for h in history for symbol in h["weights"]})
    series = {symbol: [h["weights"].get(symbol, 0) * 100 for h in history] for symbol in symbols}
    return {"labels": labels, "series": series}
