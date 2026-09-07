import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.analytics.pace_projection import project_at_pace


def demo():
    results = project_at_pace(10000.0, 0.20)  # +20%/year pace
    assert len(results) == 8
    labels = [r["label"] for r in results]
    assert labels == ["1 個月後", "1 季後", "半年後", "1 年後", "3 年後", "5 年後", "10 年後", "20 年後"]
    assert [r["long_term"] for r in results] == [False, False, False, False, True, True, True, True]

    one_year = results[3]
    assert abs(one_year["projected_value"] - 12000.0) < 1e-6
    assert abs(one_year["change"] - 2000.0) < 1e-6
    assert abs(one_year["change_pct"] - 0.20) < 1e-9
    assert one_year["extreme"] is False  # +20% is unremarkable

    twenty_year = results[-1]
    assert abs(twenty_year["projected_value"] - 10000.0 * 1.2**20) < 1e-6
    assert twenty_year["extreme"] is True  # (1.2)^20 - 1 ≈ +3734%, past the +1000% threshold

    # each checkpoint should compound to strictly more than the last for a
    # positive rate.
    values = [r["projected_value"] for r in results]
    assert values == sorted(values)
    assert values[0] > 10000.0

    # negative rate should still project a proportional decline, not crash.
    down = project_at_pace(10000.0, -0.10)
    assert down[-1]["projected_value"] < 10000.0
    assert down[-1]["change"] < 0

    # non-positive current value -> nothing sensible to project.
    assert project_at_pace(0.0, 0.20) == []
    assert project_at_pace(-100.0, 0.20) == []

    # annual_contribution defaults to 0 and reproduces the old lump-sum
    # numbers (monthly compounding still lands on the annual figure).
    assert abs(project_at_pace(10000.0, 0.20, 0.0)[3]["projected_value"] - 12000.0) < 1e-6

    # a positive contribution lifts every checkpoint above the no-contrib one.
    base = project_at_pace(10000.0, 0.20)
    with_contrib = project_at_pace(10000.0, 0.20, 1200.0)
    assert all(w["projected_value"] > b["projected_value"] for w, b in zip(with_contrib, base))
    # 1-year: 10000 grown at 20% (12000) + a $100/mo ordinary annuity.
    mr = 1.20 ** (1 / 12) - 1
    annuity_1y = 100 * ((1 + mr) ** 12 - 1) / mr
    assert abs(with_contrib[3]["projected_value"] - (12000.0 + annuity_1y)) < 1e-6

    # contributions work even at a zero return - pure deposits accumulate.
    flat = project_at_pace(10000.0, 0.0, 1200.0)
    assert abs(flat[3]["projected_value"] - (10000.0 + 1200.0)) < 1e-6


if __name__ == "__main__":
    demo()
    print("OK")
