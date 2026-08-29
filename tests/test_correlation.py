import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import correlation as corr_mod


def demo():
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    daily_returns = pd.Series([0.01 if i % 2 == 0 else -0.005 for i in range(60)], index=dates)
    a = 100 * (1 + daily_returns).cumprod()
    b = a * 2  # scaling doesn't change returns -> perfectly correlated with a
    c = 100 * (1 - daily_returns).cumprod()  # exactly opposite returns each day -> perfectly anti-correlated
    prices = pd.DataFrame({"AAA": a, "BBB": b, "CCC": c})

    with patch.object(corr_mod.yf, "download", return_value={"Close": prices}):
        result = corr_mod.compute_correlation_matrix(["AAA", "BBB", "CCC", "CASH"])

    assert result["symbols"] == ["AAA", "BBB", "CCC"]  # CASH excluded
    matrix = result["matrix"]
    for i in range(3):
        assert abs(matrix[i][i] - 1.0) < 1e-9  # diagonal is always 1
    ai, bi, ci = 0, 1, 2
    assert abs(matrix[ai][bi] - 1.0) < 1e-6  # AAA vs BBB: perfectly correlated
    assert abs(matrix[ai][ci] - (-1.0)) < 1e-6  # AAA vs CCC: perfectly anti-correlated
    assert matrix[ai][bi] == matrix[bi][ai]  # symmetric

    # fewer than 2 symbols -> empty matrix, not a crash.
    assert corr_mod.compute_correlation_matrix(["AAA"]) == {"symbols": ["AAA"], "matrix": []}


if __name__ == "__main__":
    demo()
    print("OK")
