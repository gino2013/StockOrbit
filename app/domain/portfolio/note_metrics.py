"""Live numbers shown above each position note (issue #392). Notes are
free text, so the PE / target price / "現價 +x%" written into them is a
snapshot that goes stale; this builds the *current* figures from the latest
snapshot + the fundamentals cache without touching the note itself.
Fields that are missing (an ETF has no PE) are simply left out.
"""


def build_note_metrics(
    snapshots: list[dict], fundamentals: dict[str, dict], targets: dict[str, float],
) -> dict[str, list[tuple[str, str]]]:
    """{symbol: [(label, text), ...]} for every non-CASH holding."""
    total = sum(s["market_value"] for s in snapshots)
    out: dict[str, list[tuple[str, str]]] = {}
    for s in snapshots:
        sym = s["symbol"]
        if sym == "CASH":
            continue
        f = fundamentals.get(sym, {})
        qty = s["quantity"]
        items: list[tuple[str, str]] = []
        if qty:
            price, avg = s["market_value"] / qty, s["cost_basis"] / qty
            items.append(("現價", f"${price:,.2f}"))
            if avg > 0:
                items.append(("持有均價", f"${avg:,.2f}（{price / avg - 1:+.1%}）"))
        if total:
            weight = f"{s['market_value'] / total:.1%}"
            items.append(("佔比", weight + (f" / 目標 {targets[sym]:.0%}" if sym in targets else "")))
        if f.get("trailingPE"):
            items.append(("PE", f"{f['trailingPE']:.1f}"))
        if f.get("pegRatio"):
            items.append(("PEG", f"{f['pegRatio']:.1f}"))
        if f.get("returnOnEquity") is not None:
            items.append(("ROE", f"{f['returnOnEquity']:.1%}"))
        if f.get("revenueGrowth") is not None:
            items.append(("營收成長", f"{f['revenueGrowth']:.1%}"))
        if f.get("targetMeanPrice") and qty:
            tp = f["targetMeanPrice"]
            rec = f" {f['recommendationKey']}" if f.get("recommendationKey") else ""
            items.append(("分析師目標價", f"${tp:,.2f}（{tp / (s['market_value'] / qty) - 1:+.1%}）{rec}"))
        if f.get("beta"):
            items.append(("Beta", f"{f['beta']:.2f}"))
        out[sym] = items
    return out
