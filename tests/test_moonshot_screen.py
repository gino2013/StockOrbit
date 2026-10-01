import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.screening.moonshot import rank_moonshot_candidates, score_moonshot


def demo():
    # Passes all 4: high gross margin, high growth, small market cap, sane PEG.
    strong = score_moonshot({
        "grossMargins": 0.55, "revenueGrowth": 0.30, "earningsGrowth": None,
        "marketCap": 2_000_000_000, "pegRatio": 1.2,
    })
    assert strong["score"] == 4
    assert all(c["passed"] for c in strong["criteria"])

    # Mega-cap, profitable, growing, but fails the small-cap criterion alone.
    megacap = score_moonshot({
        "grossMargins": 0.60, "revenueGrowth": 0.25,
        "marketCap": 2_000_000_000_000, "pegRatio": 1.5,
    })
    assert megacap["score"] == 3
    by_key = {c["key"]: c for c in megacap["criteria"]}
    assert by_key["small_cap"]["passed"] is False
    assert by_key["profitability"]["passed"] is True

    # Missing data counts as failed, not skipped or passed.
    no_data = score_moonshot({})
    assert no_data["score"] == 0
    assert all(c["value"] is None and c["passed"] is False for c in no_data["criteria"])

    # revenueGrowth/earningsGrowth: either one clearing the bar is enough.
    only_earnings_growth = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.05, "earningsGrowth": 0.40,
        "marketCap": 1_000_000_000, "pegRatio": 1.0,
    })
    assert only_earnings_growth["score"] == 4

    # PEG outside the sane range (too expensive relative to its own growth,
    # or a nonsensical negative PEG from negative earnings) fails valuation.
    rich_peg = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000, "pegRatio": 5.0,
    })
    assert rich_peg["score"] == 3

    # Ranking: highest score first, ties broken alphabetically by symbol.
    ranked = rank_moonshot_candidates({"ZZZ": strong, "AAA": megacap, "BBB": strong})
    # (rank_moonshot_candidates takes fundamentals dicts, not pre-scored
    # results - reuse the same fundamentals that produced `strong`/`megacap`.)
    ranked = rank_moonshot_candidates({
        "ZZZ": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000, "pegRatio": 1.2},
        "AAA": {"grossMargins": 0.60, "revenueGrowth": 0.25, "marketCap": 2_000_000_000_000, "pegRatio": 1.5},
        "BBB": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000, "pegRatio": 1.2},
    })
    assert [r["symbol"] for r in ranked] == ["BBB", "ZZZ", "AAA"]
    assert ranked[0]["score"] == 4 and ranked[-1]["score"] == 3


if __name__ == "__main__":
    demo()
    print("OK")
