"""Style Box (Morningstar-style growth/value x large/mid/small grid):
classifies each held stock into one of 9 boxes from objective yfinance
fundamentals, then shows the market-value-weighted allocation across the
grid - an at-a-glance view of the portfolio's overall style tilt that no
single-stock number gives (issue #298).

Classification uses fixed, widely-cited cutoffs - not a percentile rank
against the portfolio's own holdings. A percentile within a typical 5-15
stock portfolio is unstable: an all-large-cap portfolio would get
artificially spread across small/mid/large just because the ranking has
to put something at each end.

- Size: market cap >= $10B Large, $2B-$10B Mid, < $2B Small.
- Style: trailingPE < 15 Value, 15-25 Blend, > 25 Growth. Falls back to
  priceToBook (same three-way split at 2/4) when PE is missing or <= 0 -
  a non-positive PE means the company lost money, which says nothing
  about how cheap/expensive it's priced.
- ETFs (quoteType == "ETF") hold many companies across styles at once, so
  one box for the whole fund would be misleading - listed separately as
  unclassified instead of forced into a cell.
- CASH and anything missing the fields it needs is also unclassified.

ponytail: fixed cutoffs, not percentile-vs-market-index - revisit if these
misclassify something obviously wrong (e.g. a well-known mega-cap showing
as Small).
"""

from collections import defaultdict

SIZE_LABELS = ["Large", "Mid", "Small"]
STYLE_LABELS = ["Value", "Blend", "Growth"]

_LARGE_CAP = 10_000_000_000
_MID_CAP = 2_000_000_000

_PE_VALUE = 15
_PE_GROWTH = 25
_PB_VALUE = 2
_PB_GROWTH = 4


def _classify_size(market_cap: float | None) -> str | None:
    if not market_cap or market_cap <= 0:
        return None
    if market_cap >= _LARGE_CAP:
        return "Large"
    if market_cap >= _MID_CAP:
        return "Mid"
    return "Small"


def _split(value: float, low: float, high: float) -> str:
    if value < low:
        return "Value"
    if value > high:
        return "Growth"
    return "Blend"


def _classify_style(trailing_pe: float | None, price_to_book: float | None) -> str | None:
    if trailing_pe and trailing_pe > 0:
        return _split(trailing_pe, _PE_VALUE, _PE_GROWTH)
    if price_to_book and price_to_book > 0:
        return _split(price_to_book, _PB_VALUE, _PB_GROWTH)
    return None


def classify_style_box(snapshots: list[dict], fundamentals: dict[str, dict]) -> dict:
    value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        if s["symbol"] != "CASH":
            value_by_symbol[s["symbol"]] += s["market_value"]
    total = sum(value_by_symbol.values())
    if not total:
        return {"grid": [], "items": [], "unclassified": [], "classified_weight": 0.0}

    grid_weight: dict[tuple[str, str], float] = defaultdict(float)
    items = []
    unclassified = []
    for symbol, market_value in value_by_symbol.items():
        f = fundamentals.get(symbol, {})
        weight = market_value / total
        if f.get("quoteType") == "ETF":
            unclassified.append({"symbol": symbol, "weight": weight, "reason": "ETF"})
            continue
        size = _classify_size(f.get("marketCap"))
        style = _classify_style(f.get("trailingPE"), f.get("priceToBook"))
        if size is None or style is None:
            unclassified.append({"symbol": symbol, "weight": weight, "reason": "缺資料"})
            continue
        grid_weight[(size, style)] += weight
        items.append({"symbol": symbol, "size": size, "style": style, "weight": weight})

    grid = [
        {"size": size, "style": style, "weight": grid_weight.get((size, style), 0.0)}
        for size in SIZE_LABELS
        for style in STYLE_LABELS
    ]
    return {
        "grid": grid,
        "items": sorted(items, key=lambda i: -i["weight"]),
        "unclassified": sorted(unclassified, key=lambda i: -i["weight"]),
        "classified_weight": sum(g["weight"] for g in grid),
    }
