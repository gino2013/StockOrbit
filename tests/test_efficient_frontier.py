import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import numpy as np
import pandas as pd

from app.domain.analytics import efficient_frontier as ef


def demo():
    # AAA compounds at a flat +0.1%/day, BBB at a flat +0.2%/day - zero
    # variance/covariance by construction, so every random weight mix has
    # volatility ~0 and a return that's a linear blend of the two, letting
    # the math be hand-checked exactly instead of just "looks plausible".
    n = 60
    aaa = 100 * (1.001) ** np.arange(n)
    bbb = 100 * (1.002) ** np.arange(n)
    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb})

    with patch.object(ef.market_data, "download_close", return_value=prices):
        result = ef.build_efficient_frontier(["AAA", "BBB"], {"AAA": 100.0}, n_portfolios=500, seed=1)

    assert result["symbols"] == ["AAA", "BBB"]
    assert len(result["points"]) == 500
    for p in result["points"]:
        assert abs(p["volatility"]) < 1e-6  # zero-variance construction -> zero portfolio vol regardless of weights
        # every blend's return sits between the two pure-asset returns.
        assert 0.001 * 252 - 1e-6 <= p["return"] <= 0.002 * 252 + 1e-6

    # current_weights = 100% AAA (BBB implicitly 0) -> current point's
    # return should equal AAA's own annualized return exactly.
    assert result["current"] is not None
    assert abs(result["current"]["return"] - 0.001 * 252) < 1e-6
    assert abs(result["current"]["volatility"]) < 1e-6

    # deterministic seed -> same seed reproduces the same random cloud.
    with patch.object(ef.market_data, "download_close", return_value=prices):
        result2 = ef.build_efficient_frontier(["AAA", "BBB"], {"AAA": 100.0}, n_portfolios=500, seed=1)
    assert result["points"] == result2["points"]

    # current_weights summing to 0 (e.g. nothing held in these symbols,
    # only cash) -> no current point, not a divide-by-zero.
    with patch.object(ef.market_data, "download_close", return_value=prices):
        no_current = ef.build_efficient_frontier(["AAA", "BBB"], {}, n_portfolios=10, seed=1)
    assert no_current["current"] is None

    # fewer than 2 symbols -> refuses rather than a degenerate single point.
    try:
        ef.build_efficient_frontier(["AAA"], {"AAA": 1.0})
        assert False, "expected ValueError"
    except ValueError:
        pass

    # not enough shared price history -> refuses rather than a noisy read.
    with patch.object(ef.market_data, "download_close", return_value=prices.head(5)):
        try:
            ef.build_efficient_frontier(["AAA", "BBB"], {"AAA": 1.0})
            assert False, "expected ValueError"
        except ValueError:
            pass


if __name__ == "__main__":
    demo()
    print("OK")
