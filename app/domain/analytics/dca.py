"""DCA (dollar-cost averaging) vs lump-sum comparison, reusing
app/backtest.py's price-fetch and rebalance-date logic.

DCA invests a fixed amount at the start of each period (using the same
rebalance_dates() helper that already finds "first trading day of the
month/quarter"), buying into the target weights each time - shares
accumulate, nothing is sold. Lump-sum invests the same total amount (what
DCA would have contributed by the end) all at once on day 1, then holds
without rebalancing, via the existing simulate_rebalanced_portfolio(...,
"none", ...). No fees/taxes modeled, same as the rest of backtest.py.
"""

import pandas as pd
import yfinance as yf

from app.domain.analytics.backtest import rebalance_dates, simulate_rebalanced_portfolio


def simulate_dca_portfolio(
    prices: pd.DataFrame, weights: dict[str, float], contribution: float, frequency: str
) -> tuple[pd.Series, float]:
    symbols = list(prices.columns)
    contribution_dates = {prices.index[0], *rebalance_dates(prices.index, frequency)}
    shares = pd.Series(0.0, index=symbols)
    total_invested = 0.0

    values = []
    for date, row in prices.iterrows():
        if date in contribution_dates:
            for symbol in symbols:
                shares[symbol] += contribution * weights[symbol] / row[symbol]
            total_invested += contribution
        values.append(float((shares * row).sum()))
    return pd.Series(values, index=prices.index), total_invested


def run_dca_comparison(
    weights: dict[str, float], start: str, end: str, contribution: float, frequency: str = "M"
) -> dict:
    symbols = list(weights.keys())
    data = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    data = data.dropna(how="all").ffill().dropna()
    if len(data) < 2:
        raise ValueError("所選期間沒有足夠的歷史股價資料（例如日期落在未來，或區間內沒有交易日）")

    dca_series, total_invested = simulate_dca_portfolio(data[symbols], weights, contribution, frequency)
    lumpsum_series = simulate_rebalanced_portfolio(data[symbols], weights, "none", total_invested)

    return {
        "dates": data.index.strftime("%Y-%m-%d").tolist(),
        "dca_value": [round(v, 2) for v in dca_series.tolist()],
        "lumpsum_value": [round(v, 2) for v in lumpsum_series.tolist()],
        "total_invested": round(total_invested, 2),
        "dca_final_value": round(dca_series.iloc[-1], 2),
        "lumpsum_final_value": round(lumpsum_series.iloc[-1], 2),
        "dca_return": dca_series.iloc[-1] / total_invested - 1,
        "lumpsum_return": lumpsum_series.iloc[-1] / total_invested - 1,
    }
