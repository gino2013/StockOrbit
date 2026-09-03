"""Single-card rollup of risk/concentration indicators that otherwise live
scattered across several sections (risk, correlation, risk-parity). No new
calculation logic - just aggregates the same underlying data into a handful
of headline numbers. Objective data only, no verdict.

Deliberately does ONE shared price download and computes correlation/beta
directly with pandas, rather than calling compute_correlation_matrix() +
compute_risk_metrics() (which each do their own separate price download, and
the latter also fetches each symbol's next-earnings-date via a blocking
per-symbol Yahoo calendar call this overview never uses) - that redundant
network round-tripping was the actual reason this endpoint felt slow.
"""

from collections import defaultdict

from app.infrastructure import market_data

from app.domain.analytics.risk import beta_vs_benchmark

_BENCHMARK = "SPY"


def build_health_overview(snapshots: list[dict]) -> dict:
    value_by_symbol: dict[str, float] = defaultdict(float)
    for s in snapshots:
        value_by_symbol[s["symbol"]] += s["market_value"]
    total = sum(value_by_symbol.values())
    symbols = [s for s in value_by_symbol if s != "CASH"]

    max_concentration = max((value_by_symbol[s] / total for s in symbols), default=0.0) if total else 0.0

    avg_correlation = None
    portfolio_beta = None
    if symbols:
        tickers = list(dict.fromkeys(symbols + [_BENCHMARK]))
        prices = market_data.download_close(tickers, period="1y")
        prices = prices.dropna(how="all").ffill()
        returns = prices.pct_change()

        if len(symbols) >= 2:
            corr = returns[symbols].corr()
            n = len(symbols)
            off_diagonal_sum = corr.to_numpy().sum() - n  # subtract the n ones on the diagonal
            avg_correlation = float(off_diagonal_sum / (n * n - n))

        if _BENCHMARK in returns:
            benchmark_returns = returns[_BENCHMARK].dropna()
            # Divide by (total - the value of holdings we couldn't compute a
            # beta for), not by `total`: a holding too new to have 30 days of
            # overlap otherwise contributes 0 to the sum and silently drags
            # the weighted average down, as if it had zero market risk.
            # Cash *does* stay in the denominator - its ~0 beta genuinely
            # dampens the portfolio's, that's not an error.
            weighted, unmeasurable_value = 0.0, 0.0
            for symbol in symbols:
                beta = (
                    beta_vs_benchmark(returns[symbol].dropna(), benchmark_returns)
                    if symbol in returns
                    else None
                )
                if beta is None:
                    unmeasurable_value += value_by_symbol[symbol]
                else:
                    weighted += value_by_symbol[symbol] * beta
            measurable_base = total - unmeasurable_value
            portfolio_beta = weighted / measurable_base if measurable_base else None

    return {
        "position_count": len(symbols),
        "max_concentration": max_concentration,
        "avg_correlation": avg_correlation,
        "portfolio_beta": portfolio_beta,
    }
