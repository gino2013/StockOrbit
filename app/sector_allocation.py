"""Sector-level portfolio breakdown, weighted by market value.

Reuses whatever sector data FundamentalsCache already has (kept fresh by
the scheduled GitHub Actions job, see #9) — no live fetch here, so this
renders on every page load like the rest of the snapshot-derived stats.
"""

from collections import defaultdict

CASH_BUCKET = "現金"
# ETFs/funds don't have a single-company "sector" on Yahoo Finance (what
# would GOOGL-vs-Technology even mean for a fund holding 500 companies?),
# so anything without sector data lands here. Named for what it actually is
# in practice, not a vague "其他" that reads like a data-quality problem.
UNKNOWN_BUCKET = "ETF／其他"


def bucket_for_symbol(symbol: str, sector_by_symbol: dict[str, str | None]) -> str:
    if symbol == "CASH":
        return CASH_BUCKET
    return sector_by_symbol.get(symbol) or UNKNOWN_BUCKET


def compute_sector_allocation(snapshots: list[dict], sector_by_symbol: dict[str, str | None]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for s in snapshots:
        totals[bucket_for_symbol(s["symbol"], sector_by_symbol)] += s["market_value"]
    return dict(totals)


def symbol_buckets(snapshots: list[dict], sector_by_symbol: dict[str, str | None]) -> dict[str, str]:
    """symbol -> the same bucket name compute_sector_allocation() grouped it
    into, so the per-symbol chart can color each slice to match its sector's
    slice in the sector chart."""
    return {s["symbol"]: bucket_for_symbol(s["symbol"], sector_by_symbol) for s in snapshots}
