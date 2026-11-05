"""Stay-the-course check for a market drop (issue #417): for the reference
markets (QQQ, QLD, S&P 500) and each holding, how far it sits below its all-time high today, and what
history says about every past time it was at least that far down - forward
1Y / 3Y returns and how long it took to get back to the old high. Facts
from the price history, shown as-is even when they don't reassure; not a
prediction or investment advice.
"""

import pandas as pd

from app.infrastructure import market_data

# Reference markets, main one first (issue #429): the owner holds mostly QQQ/QLD.
MARKETS = {"QQQ": "QQQ（那斯達克 100）", "QLD": "QLD（2 倍 QQQ）", "^GSPC": "S&P 500"}
FORWARD = [("1y", 252), ("3y", 756)]
MIN_SAMPLES = 20  # fewer forward-return days than this says nothing


def forward_stats(closes: pd.Series, mask: pd.Series, days: int) -> dict | None:
    fwd = (closes.shift(-days) / closes - 1)[mask].dropna()
    if len(fwd) < MIN_SAMPLES:
        return None
    return {"samples": len(fwd), "median": float(fwd.median()), "win_rate": float((fwd > 0).mean())}


def past_recoveries(closes: pd.Series, depth: float) -> list[int]:
    """Calendar days from first hitting `depth` below the old high to closing
    back at that high, once per past drawdown. Only drawdowns that ended
    before the latest high count, so every one of them recovered."""
    peak = closes.cummax()
    dd = closes / peak - 1
    last_high = dd[dd >= 0].index[-1]
    episode = (dd >= 0).cumsum()
    days = []
    for _, group in dd[(dd <= depth) & (dd.index < last_high)].groupby(episode):
        hit = group.index[0]
        back = closes[(closes.index > hit) & (closes >= peak[hit])].index[0]
        days.append((back - hit).days)
    return days


def analyze(closes: pd.Series) -> dict:
    closes = closes.dropna()
    peak = closes.cummax()
    dd = closes / peak - 1
    today = float(dd.iloc[-1])
    mask = dd <= today
    recoveries = past_recoveries(closes, today) if today < 0 else []
    return {
        "price": float(closes.iloc[-1]),
        "high": float(peak.iloc[-1]),
        "drawdown": today,
        "since": closes.index[0].strftime("%Y-%m-%d"),
        "forward": {label: forward_stats(closes, mask, days) for label, days in FORWARD},
        "past_drops": len(recoveries),
        "recovery_median_days": int(pd.Series(recoveries).median()) if recoveries else None,
        "recovery_max_days": max(recoveries) if recoveries else None,
    }


def steady_report(holdings: list[dict]) -> dict:
    """`holdings`: latest_snapshots rows (symbol / quantity / market_value / cost_basis)."""
    # "CASH" is the synthetic cash-balance row; Yahoo has an unrelated CASH ticker.
    held = [h for h in holdings if h["quantity"] > 0 and h["symbol"] != "CASH"]
    symbols = list(dict.fromkeys([*MARKETS, *(h["symbol"] for h in held)]))
    data = market_data.download_close(symbols, period="max")
    if isinstance(data, pd.Series):
        data = data.to_frame(symbols[0])

    def row(symbol: str) -> dict:
        closes = data[symbol].dropna() if symbol in data else pd.Series(dtype=float)
        if len(closes) < 2:
            return {"symbol": symbol, "error": "沒有股價資料"}
        return {"symbol": symbol, **analyze(closes)}

    rows = []
    cost = value = 0.0
    for h in held:
        r = row(h["symbol"])
        # Same price as the row's 現價 (issue #421); snapshot value only when Yahoo has none.
        mv = r["price"] * h["quantity"] if "price" in r else h["market_value"]
        r["avg_cost"] = h["cost_basis"] / h["quantity"] if h["cost_basis"] else None
        r["unrealized"] = mv / h["cost_basis"] - 1 if h["cost_basis"] else None
        rows.append(r)
        cost += h["cost_basis"]
        value += mv
    return {
        "markets": [{**row(sym), "name": name} for sym, name in MARKETS.items()],
        "holdings": rows,
        "portfolio_unrealized": value / cost - 1 if cost else None,
    }
