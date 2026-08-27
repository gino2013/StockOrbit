"""Sector-level portfolio breakdown, weighted by market value.

Reuses whatever sector data FundamentalsCache already has (kept fresh by
the scheduled GitHub Actions job, see #9) — no live fetch here, so this
renders on every page load like the rest of the snapshot-derived stats.
"""

from collections import defaultdict

CASH_BUCKET = "現金"
UNKNOWN_BUCKET = "其他"


def compute_sector_allocation(snapshots: list[dict], sector_by_symbol: dict[str, str | None]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for s in snapshots:
        if s["symbol"] == "CASH":
            bucket = CASH_BUCKET
        else:
            bucket = sector_by_symbol.get(s["symbol"]) or UNKNOWN_BUCKET
        totals[bucket] += s["market_value"]
    return dict(totals)
