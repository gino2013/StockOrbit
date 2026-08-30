"""Lump-sum entry-timing risk for a single symbol: scan its full price
history for every peak that was followed by a long stretch (months to
years) before the price recovered back to that peak. Each one is a point in
time where a one-shot buy would have sat underwater for a long time before
breaking even - a historical fact list, not a prediction of future risk.
"""

import yfinance as yf

MIN_DURATION_DAYS = 60  # below this it's just normal short-term volatility


def find_drawdown_periods(symbol: str, period: str = "max", min_duration_days: int = MIN_DURATION_DAYS) -> dict:
    history = yf.download(symbol, period=period, auto_adjust=True, progress=False)["Close"]
    if hasattr(history, "columns"):
        history = history.iloc[:, 0]
    history = history.dropna()
    if len(history) < 2:
        raise ValueError("沒有足夠的歷史股價資料")

    dates = history.index
    prices = history.values

    episodes = []
    peak_price = prices[0]
    peak_date = dates[0]
    trough_price = None
    trough_date = None

    def close_episode(end_date, recovered: bool):
        duration_days = (end_date - peak_date).days
        if duration_days < min_duration_days:
            return
        episodes.append(
            {
                "peak_date": peak_date.strftime("%Y-%m-%d"),
                "peak_price": float(peak_price),
                "trough_date": trough_date.strftime("%Y-%m-%d"),
                "trough_price": float(trough_price),
                "max_drawdown_pct": float(trough_price / peak_price - 1),
                "recovery_date": end_date.strftime("%Y-%m-%d") if recovered else None,
                "recovered": recovered,
                "duration_days": duration_days,
            }
        )

    for i in range(1, len(prices)):
        price, date = prices[i], dates[i]
        if price >= peak_price:
            if trough_date is not None:
                close_episode(date, recovered=True)
            peak_price = price
            peak_date = date
            trough_price = None
            trough_date = None
        elif trough_price is None or price < trough_price:
            trough_price = price
            trough_date = date

    if trough_date is not None:
        close_episode(dates[-1], recovered=False)

    # Episodes never overlap by construction (each new peak starts exactly
    # where the previous episode recovered, or later), so summing their
    # durations is a plain day count of "how many days in this whole history
    # were spent inside one of these long drawdowns" - a rough odds-of-a-
    # random-lump-sum-buy-date-landing-in-one-of-these estimate, not a
    # forecast of future risk.
    total_days = (dates[-1] - dates[0]).days
    days_in_drawdown = sum(ep["duration_days"] for ep in episodes)
    buy_in_crash_probability = days_in_drawdown / total_days if total_days else 0.0

    return {
        "symbol": symbol,
        "start_date": dates[0].strftime("%Y-%m-%d"),
        "end_date": dates[-1].strftime("%Y-%m-%d"),
        "min_duration_days": min_duration_days,
        "episodes": episodes,
        "total_days": total_days,
        "days_in_drawdown": days_in_drawdown,
        "buy_in_crash_probability": buy_in_crash_probability,
        # Full price series so the caller can chart the episodes in context
        # rather than just listing them as a table.
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "prices": [float(p) for p in prices],
    }
