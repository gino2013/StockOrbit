"""Pearson correlation matrix of daily returns across held/target symbols.

Sector labels are nominal - two symbols in different sectors can still move
almost in lockstep (e.g. both riding the same macro/large-cap-tech wave).
This surfaces the actual statistical co-movement instead, as a plain N×N
matrix. Objective data only: no "reduce X" conclusion, and the caller-facing
disclaimer that high correlation isn't necessarily same-sector and doesn't
by itself mean diversification failed.
"""

from app.infrastructure import market_data


def compute_correlation_matrix(symbols: list[str], period: str = "1y") -> dict:
    symbols = [s for s in dict.fromkeys(symbols) if s != "CASH"]
    if len(symbols) < 2:
        return {"symbols": symbols, "matrix": []}

    prices = market_data.download_close(symbols, period=period)
    prices = prices.dropna(how="all").ffill()
    returns = prices.pct_change().dropna(how="all")
    corr = returns.corr()

    ordered = [s for s in symbols if s in corr.columns]
    matrix = [[float(corr.loc[a, b]) for b in ordered] for a in ordered]
    return {"symbols": ordered, "matrix": matrix}
