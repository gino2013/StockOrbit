"""Account value over time rebuilt from the real trade history (issue #400) -
unlike holdings_history (today's share counts priced into the past), this
replays every transaction day by day: shares held, average cost, and cash.

Pure: the caller fetches prices/splits (market_data.download_close_and_splits)
and passes them in, so the replay is testable without the network.

Conventions shared with the rest of the app: quantities are abs()'d, a
same-day BOUGHT is applied before a SOLD (realized_gains does the same).
Cash is the running sum of every transaction - trades, dividends, interest,
deposits alike - with the direction taken from trans_type (see apply()).
"""

import re

import pandas as pd

from app.domain.analytics.xirr import EXTERNAL_CASH_IN_TYPES, EXTERNAL_CASH_OUT_TYPES

_EPS = 1e-6
# Firstrade's DIV amount is gross; the non-resident withholding is only in
# the description, e.g. "... NON-RES TAX WITHHELD $2.09000" (issue #404).
_WITHHELD = re.compile(r"TAX WITHHELD \$([\d.]+)")


def _withheld(t: dict) -> float:
    m = _WITHHELD.search(t.get("description") or "")
    return float(m.group(1)) if m else 0.0


def _drop_dividend_mirrors(transactions: list[dict]) -> list[dict]:
    """Firstrade also lists each dividend as an OTHER row on the margin
    sub-account - same date, symbol and amount as the DIV row (issue #404).
    Counting both doubles the dividend in cash; drop the OTHER copy."""
    divs = {(t["report_date"], t.get("symbol"), t["amount"]) for t in transactions if t["trans_type"] == "DIV"}
    return [
        t for t in transactions
        if not (t["trans_type"] == "OTHER" and t.get("symbol")
                and (t["report_date"], t["symbol"], t["amount"]) in divs)
    ]


def split_factor(splits: pd.Series | None, on) -> float:
    """How many of today's shares one share held on `on` became: the
    product of every split ratio strictly after that date."""
    if splits is None:
        return 1.0
    later = splits[(splits.index > pd.Timestamp(on)) & (splits > 0)]
    return float(later.prod()) if len(later) else 1.0


def _sorted(transactions: list[dict]) -> list[dict]:
    return sorted(
        transactions,
        key=lambda t: (t["report_date"], 0 if t["trans_type"] == "BOUGHT" else 1),
    )


def build_account_timeline(
    transactions: list[dict],
    closes: pd.DataFrame,
    splits: pd.DataFrame,
    actual: dict[str, float],
) -> dict:
    """`closes`/`splits`: one column per traded symbol, DatetimeIndex of
    trading days from the first transaction to today. `actual`: latest
    snapshot {symbol: quantity}, plus "CASH" -> cash balance if known; only
    used to flag where the replay disagrees with reality."""
    txns = _sorted(_drop_dividend_mirrors(transactions))
    closes = closes.ffill()
    symbols = sorted({t["symbol"] for t in txns if t["trans_type"] in ("BOUGHT", "SOLD") and t.get("symbol")})

    shares = dict.fromkeys(symbols, 0.0)
    cost = dict.fromkeys(symbols, 0.0)
    cash = invested = 0.0
    markers: dict[tuple, list] = {}  # (chart date, side) -> items

    def apply(t, chart_date):
        nonlocal cash, invested
        amount = t["amount"] or 0.0
        typ = t["trans_type"]
        # Sign by type, not by `amount`: deposits show up with either sign
        # across sources (xirr.py abs()es them for the same reason).
        if typ in EXTERNAL_CASH_IN_TYPES:
            cash += abs(amount)
            invested += abs(amount)
        elif typ in EXTERNAL_CASH_OUT_TYPES:
            cash -= abs(amount)
            invested -= abs(amount)
        elif typ == "BOUGHT":
            cash -= abs(amount)
        elif typ == "SOLD":
            cash += abs(amount)
        elif typ == "DIV":
            cash += amount - _withheld(t)
        else:  # INTEREST / OTHER (fees, rebates, margin transfers) keep their own sign
            cash += amount
        if t["trans_type"] not in ("BOUGHT", "SOLD") or not t.get("symbol"):
            return
        sym = t["symbol"]
        f = split_factor(splits[sym] if sym in splits else None, t["report_date"])
        qty = abs(t["quantity"]) * f
        price = t["trade_price"] / f if f else t["trade_price"]
        item = {"symbol": sym, "quantity": round(qty, 4), "amount": round(abs(t["amount"] or qty * price), 2)}
        if t["trans_type"] == "BOUGHT":
            shares[sym] += qty
            cost[sym] += qty * price
            side = "buy"
        else:
            sold = min(qty, shares[sym])
            avg = cost[sym] / shares[sym] if shares[sym] > _EPS else 0.0
            item["realized_gain"] = round(sold * (price - avg), 2)
            cost[sym] -= sold * avg
            shares[sym] -= sold
            if shares[sym] <= _EPS:
                shares[sym], cost[sym] = 0.0, 0.0
            side = "sell"
        if chart_date is not None:
            markers.setdefault((chart_date, side), []).append(item)

    dates, total_value, invested_line, cash_line = [], [], [], []
    per_symbol = {s: {"market_value": [], "cost": []} for s in symbols}
    missing_prices: set[str] = set()
    i = 0
    for day in closes.index:
        label = day.strftime("%Y-%m-%d")
        while i < len(txns) and txns[i]["report_date"] <= day.date():
            apply(txns[i], label)
            i += 1
        holdings = 0.0
        for s in symbols:
            price = closes.at[day, s] if s in closes else float("nan")
            if pd.isna(price):
                if shares[s] > _EPS:
                    missing_prices.add(s)
                price = 0.0
            mv = shares[s] * price
            holdings += mv
            per_symbol[s]["market_value"].append(round(mv, 2))
            per_symbol[s]["cost"].append(round(cost[s], 2))
        dates.append(label)
        total_value.append(round(holdings + cash, 2))
        invested_line.append(round(invested, 2))
        cash_line.append(cash)
    # Trades dated after the last price row (e.g. today before the close)
    # still count toward the final state the warnings compare against.
    for t in txns[i:]:
        apply(t, None)

    mismatches = []
    for s in sorted(set(symbols) | {k for k in actual if k != "CASH"}):
        rebuilt, real = shares.get(s, 0.0), actual.get(s, 0.0)
        if abs(rebuilt - real) > 1e-3:
            mismatches.append({"symbol": s, "rebuilt": round(rebuilt, 4), "actual": round(real, 4)})
    real_cash = actual.get("CASH")
    cash_mismatch = (
        {"rebuilt": round(cash, 2), "actual": round(real_cash, 2)}
        if real_cash is not None and abs(cash - real_cash) > 1
        else None
    )

    last_mv = {s: per_symbol[s]["market_value"][-1] if dates else 0.0 for s in symbols}
    held = sorted((s for s in symbols if shares[s] > _EPS), key=lambda s: -last_mv[s])
    sold_out = [s for s in symbols if shares[s] <= _EPS]

    return {
        "dates": dates,
        "total_value": total_value,
        "invested": invested_line,
        "latest": {
            "holdings_value": round(sum(last_mv.values()), 2),
            "cash": round(cash_line[-1], 2) if cash_line else 0.0,
        },
        "markers": [
            {"date": d, "side": side, "items": items} for (d, side), items in sorted(markers.items())
        ],
        "symbols": held + sold_out,
        "sold_out": sold_out,
        "per_symbol": per_symbol,
        "warnings": {
            "share_mismatches": mismatches,
            "cash_mismatch": cash_mismatch,
            "negative_cash": any(c < -1 for c in cash_line),
            "missing_prices": sorted(missing_prices),
        },
    }
