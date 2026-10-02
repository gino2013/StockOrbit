import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.screening.moonshot import (
    GROSS_MARGIN_THRESHOLD,
    GROWTH_THRESHOLD,
    PEG_MAX,
    SMALL_CAP_THRESHOLD,
    market_screen_symbols,
    rank_moonshot_candidates,
    score_moonshot,
)


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

    # Ranking: highest score first. Ties preserve input order (issue #364) -
    # for the market-screen caller that input order IS market-cap-desc (from
    # Yahoo's screener), so this can't fall back to alphabetical or that
    # promise breaks silently.
    ranked = rank_moonshot_candidates({
        "ZZZ": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000, "pegRatio": 1.2},
        "AAA": {"grossMargins": 0.60, "revenueGrowth": 0.25, "marketCap": 2_000_000_000_000, "pegRatio": 1.5},
        "BBB": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000, "pegRatio": 1.2},
    })
    assert [r["symbol"] for r in ranked] == ["ZZZ", "BBB", "AAA"]
    assert ranked[0]["score"] == 4 and ranked[-1]["score"] == 3

    # market_screen_symbols (issue #356): delegates to the infrastructure
    # layer's yfinance EquityQuery wrapper, converting this module's decimal
    # thresholds (0.4) to the percentage scale Yahoo's screener expects (40).
    with patch("app.infrastructure.market_data.screen_equities") as mock_screen:
        mock_screen.return_value = [{"symbol": "INOD"}, {"symbol": "RDW"}, {"symbol": None}]
        symbols = market_screen_symbols(limit=15)
    assert symbols == ["INOD", "RDW"]  # a quote with no symbol is dropped, not crashed on
    call_kwargs = mock_screen.call_args.kwargs
    assert call_kwargs["count"] == 15
    filters = dict((f[0], f) for f in call_kwargs["filters"])
    assert filters["grossprofitmargin.lasttwelvemonths"] == (
        "grossprofitmargin.lasttwelvemonths", "gt", GROSS_MARGIN_THRESHOLD * 100,
    )
    assert filters["intradaymarketcap"] == ("intradaymarketcap", "lt", SMALL_CAP_THRESHOLD)
    assert filters["totalrevenues1yrgrowth.lasttwelvemonths"] == (
        "totalrevenues1yrgrowth.lasttwelvemonths", "gt", GROWTH_THRESHOLD * 100,
    )
    assert filters["pegratio_5y"] == ("pegratio_5y", "btwn", (0, PEG_MAX))


if __name__ == "__main__":
    demo()
    print("OK")
