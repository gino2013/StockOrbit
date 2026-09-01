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


if __name__ == "__main__":
    demo()
    print("OK")
