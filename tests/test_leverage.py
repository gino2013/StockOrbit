import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.liabilities.leverage import leverage_spread, weighted_average_rate


def demo():
    # --- single loan: weighted average is just its own rate. ---
    assert weighted_average_rate([(100000.0, 0.03)]) == 0.03

    # --- two loans: balance-weighted, not a plain average of the rates
    # (plain average would be 4%, but the bigger/cheaper loan should pull
    # the weighted average down toward 3%). ---
    result = weighted_average_rate([(300000.0, 0.03), (100000.0, 0.05)])
    expected = (300000 * 0.03 + 100000 * 0.05) / 400000
    assert abs(result - expected) < 1e-9
    assert result < 0.04  # confirms it's balance-weighted, not a plain average

    # --- a paid-off loan (balance 0) drops out of the average entirely,
    # not dragged down/up by its original rate. ---
    result = weighted_average_rate([(0.0, 0.10), (100000.0, 0.03)])
    assert result == 0.03

    # --- nothing owed at all -> None, not a divide-by-zero crash. ---
    assert weighted_average_rate([]) is None
    assert weighted_average_rate([(0.0, 0.05)]) is None

    # --- spread: portfolio beating the cost of borrowing is a positive
    # number, portfolio losing to it is negative. ---
    assert abs(leverage_spread(0.08, 0.03) - 0.05) < 1e-9  # XIRR 8%, loan 3% -> +5pp, leverage helped
    assert abs(leverage_spread(0.01, 0.03) - (-0.02)) < 1e-9  # XIRR 1%, loan 3% -> -2pp, leverage cost more

    # --- missing either input -> None, not a crash or a misleading 0. ---
    assert leverage_spread(None, 0.03) is None
    assert leverage_spread(0.08, None) is None
    assert leverage_spread(None, None) is None


if __name__ == "__main__":
    demo()
    print("OK")
