"""Sector-level portfolio breakdown, weighted by market value.

Reuses whatever sector/quoteType data FundamentalsCache already has (kept
fresh by the scheduled GitHub Actions job, see #9) — no live fetch here, so
this renders on every page load like the rest of the snapshot-derived stats.
"""

from collections import defaultdict

CASH_BUCKET = "CASH"
ETF_BUCKET = "ETF"


def bucket_for_symbol(symbol: str, info_by_symbol: dict[str, dict]) -> str:
    """CASH and confirmed ETFs (Yahoo's quoteType) each get one shared
    bucket; a real company uses its sector. Anything else — no sector, not
    confirmed to be an ETF (e.g. cache miss, an asset type we don't
    recognize) — gets its own bucket named after itself rather than being
    dumped into a vague "other" that mixes unrelated things together.
    """
    if symbol == "CASH":
        return CASH_BUCKET
    info = info_by_symbol.get(symbol) or {}
    if info.get("quoteType") == "ETF":
        return ETF_BUCKET
    return info.get("sector") or symbol


def compute_sector_allocation(snapshots: list[dict], info_by_symbol: dict[str, dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for s in snapshots:
        totals[bucket_for_symbol(s["symbol"], info_by_symbol)] += s["market_value"]
    return dict(totals)


def symbol_buckets(snapshots: list[dict], info_by_symbol: dict[str, dict]) -> dict[str, str]:
    """symbol -> the same bucket name compute_sector_allocation() grouped it
    into, so the per-symbol chart can color each slice to match its sector's
    slice in the sector chart."""
    return {s["symbol"]: bucket_for_symbol(s["symbol"], info_by_symbol) for s in snapshots}
