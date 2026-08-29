"""DRIP (dividend reinvestment) vs cash-dividend comparison for a single
symbol, using yfinance's own historical per-share dividend data - not tied
to the user's personal buy/sell history (same "arbitrary symbol + date
range" shape as app/compound_curve.py), so it works for any symbol even
if never actually held.

Two scenarios starting from the same initial share count:
- cash: dividends collected as cash, left uninvested (0% return on cash)
- drip: dividends buy more shares of the same symbol on the ex-dividend
  date, at that day's closing price

No taxes/fees modeled, same simplification as the rest of the app.
"""

import yfinance as yf


def simulate_drip(symbol: str, start: str, end: str, initial_investment: float = 10000.0) -> dict:
    history = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False)
    history = history.dropna(subset=["Close"])
    if len(history) < 2:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")

    closes = history["Close"]
    dividends = history["Dividends"] if "Dividends" in history else closes * 0

    shares_cash = initial_investment / closes.iloc[0]
    shares_drip = shares_cash
    cash_collected = 0.0
    total_dividends_per_share = 0.0

    cash_value, drip_value = [], []
    for date, close in closes.items():
        div = dividends.get(date, 0.0)
        if div:
            cash_collected += shares_cash * div
            shares_drip += shares_drip * div / close
            total_dividends_per_share += div
        cash_value.append(shares_cash * close + cash_collected)
        drip_value.append(shares_drip * close)

    return {
        "dates": closes.index.strftime("%Y-%m-%d").tolist(),
        "cash_value": [round(v, 2) for v in cash_value],
        "drip_value": [round(v, 2) for v in drip_value],
        "cash_final_value": round(cash_value[-1], 2),
        "drip_final_value": round(drip_value[-1], 2),
        "cash_return": cash_value[-1] / initial_investment - 1,
        "drip_return": drip_value[-1] / initial_investment - 1,
        "total_dividends_collected": round(cash_collected, 2),
        "total_dividends_per_share": round(total_dividends_per_share, 4),
    }
