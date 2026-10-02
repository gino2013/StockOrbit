import sys
import time
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

# PEG is self-computed from trailingPE + the forwardEps-vs-trailingEps implied
# growth rate (issue #366), not read from a `pegRatio` field - these fixtures
# supply trailingEps/forwardEps/trailingPE directly instead of a pegRatio
# shortcut, so each one below is PE=24,EPS 2.0->2.4 (20% growth) -> PEG 1.2.


def demo():
    # Passes all 4: high gross margin, high growth, small market cap, sane PEG.
    strong = score_moonshot({
        "grossMargins": 0.55, "revenueGrowth": 0.30, "earningsGrowth": None,
        "marketCap": 2_000_000_000, "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert strong["score"] == 4
    assert all(c["passed"] for c in strong["criteria"])
    assert strong["flags"] == []
    assert strong["is_financial"] is False

    # Mega-cap, profitable, growing, but fails the small-cap criterion alone.
    megacap = score_moonshot({
        "grossMargins": 0.60, "revenueGrowth": 0.25,
        "marketCap": 2_000_000_000_000, "trailingPE": 30, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert megacap["score"] == 3
    by_key = {c["key"]: c for c in megacap["criteria"]}
    assert by_key["small_cap"]["passed"] is False
    assert by_key["profitability"]["passed"] is True

    # Missing data counts as failed, not skipped or passed.
    no_data = score_moonshot({})
    assert no_data["score"] == 0
    assert all(c["value"] is None and c["passed"] is False for c in no_data["criteria"])
    assert no_data["is_financial"] is False

    # revenueGrowth/earningsGrowth: either one clearing the bar is enough.
    only_earnings_growth = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.05, "earningsGrowth": 0.40,
        "marketCap": 1_000_000_000, "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert only_earnings_growth["score"] == 4

    # PEG outside the sane range (too expensive relative to its own implied
    # growth) fails valuation alone.
    rich_peg = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 100, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert rich_peg["score"] == 3
    assert rich_peg["criteria"][-1]["key"] == "valuation" and rich_peg["criteria"][-1]["passed"] is False

    # --- issue #366: PEG self-calc hard-fails on non-positive trailing EPS,
    # not "skip this dimension" - IRTC/LEGN/PRM (loss-making over the trailing
    # 12 months) must not be able to pass valuation just because some data
    # source's pegRatio field happened to still return a number.
    loss_making = score_moonshot({
        "grossMargins": 0.71, "revenueGrowth": 0.20, "marketCap": 3_000_000_000,
        "trailingPE": None, "trailingEps": -0.41, "forwardEps": 1.21,
    })
    by_key = {c["key"]: c for c in loss_making["criteria"]}
    assert by_key["valuation"]["value"] is None
    assert by_key["valuation"]["passed"] is False

    # --- issue #366: profit-quality flags. LIF/ONDS-style: operating margin
    # at or below zero gets flagged regardless of score.
    thin_or_negative_op_margin = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
        "operatingMargins": -0.02,
    })
    assert "營業利益為負或零" in thin_or_negative_op_margin["flags"]

    # HASI-style: operating margin positive but net income is way out of
    # proportion to it (tax benefit / non-operating gains inflating the
    # bottom line) - this flag fires independently of pass/fail.
    inflated_net_income = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
        "operatingMargins": 0.10, "totalRevenue": 100_000_000, "netIncomeToCommon": 50_000_000,
    })
    assert "淨利遠高於營業利益，可能有業外或稅務利益灌水" in inflated_net_income["flags"]
    # ...but a net income that's merely somewhat above operating income
    # (not 1.5x+) isn't flagged - this is a quality signal, not a trigger
    # on every company with any non-operating income at all.
    modest_net_income = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
        "operatingMargins": 0.10, "totalRevenue": 100_000_000, "netIncomeToCommon": 11_000_000,
    })
    assert "淨利遠高於營業利益，可能有業外或稅務利益灌水" not in modest_net_income["flags"]

    # --- issue #366: growth-source flag. forwardPE > trailingPE means the
    # market/analysts expect earnings to shrink, not grow - current YoY
    # growth passing the bar may not be sustained.
    decelerating = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4, "forwardPE": 25,
    })
    assert "預估本益比高於目前本益比，分析師預期獲利成長放緩" in decelerating["flags"]

    # --- issue #366: boundary flag - within 5% of a threshold gets flagged,
    # regardless of which side of the line it landed on.
    near_small_cap_boundary = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": SMALL_CAP_THRESHOLD * 0.98,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert any("邊界" in f for f in near_small_cap_boundary["flags"])
    far_from_boundary = score_moonshot({
        "grossMargins": 0.50, "revenueGrowth": 0.30, "marketCap": SMALL_CAP_THRESHOLD * 0.5,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert not any("邊界" in f for f in far_from_boundary["flags"])

    # --- issue #366: financial-sector branching. SLM/HASI-style: gross
    # margin reported near 100% (a meaningless number for a lender/REIT) ->
    # detected as financial even without an explicit sector field, and the
    # profitability dimension switches to ROE/P-B instead of gross margin.
    financial_via_margin = score_moonshot({
        "grossMargins": 1.0, "returnOnEquity": 0.15, "priceToBook": 1.5,
        "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert financial_via_margin["is_financial"] is True
    by_key = {c["key"]: c for c in financial_via_margin["criteria"]}
    assert by_key["profitability"]["value"] == 0.15  # ROE, not the 1.0 gross margin
    assert by_key["profitability"]["passed"] is True

    financial_via_sector = score_moonshot({
        "sector": "Financial Services", "grossMargins": 0.60,
        "returnOnEquity": 0.05, "priceToBook": 1.5,  # ROE too low -> fails even though gross margin would've passed
        "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 20, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert financial_via_sector["is_financial"] is True
    by_key = {c["key"]: c for c in financial_via_sector["criteria"]}
    assert by_key["profitability"]["passed"] is False  # ROE 5% < 12% threshold

    # A non-financial company's gross margin is untouched by any of this.
    non_financial = score_moonshot({
        "grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
        "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4,
    })
    assert non_financial["is_financial"] is False

    # Ranking: highest score first. Ties preserve input order (issue #364) -
    # for the market-screen caller that input order IS market-cap-desc (from
    # Yahoo's screener), so this can't fall back to alphabetical or that
    # promise breaks silently.
    ranked = rank_moonshot_candidates({
        "ZZZ": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000,
                "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4},
        "AAA": {"grossMargins": 0.60, "revenueGrowth": 0.25, "marketCap": 2_000_000_000_000,
                "trailingPE": 30, "trailingEps": 2.0, "forwardEps": 2.4},
        "BBB": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 2_000_000_000,
                "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4},
    })
    assert [r["symbol"] for r in ranked] == ["ZZZ", "BBB", "AAA"]
    assert ranked[0]["score"] == 4 and ranked[-1]["score"] == 3

    # --- issue #366: ticker liveness. A symbol with a stale regularMarketTime
    # (well past the ~5-trading-day window) is dropped entirely, not just
    # scored low - a delisted/merged company shouldn't show up as a
    # candidate at all. Reassigned tickers (same symbol, different company
    # post-merger, e.g. ARIS) are a reminder this check has to be about
    # "is this ticker actually quoting recently", not "do we recognize the
    # company name" - we have no way to check the latter anyway.
    now = time.time()
    fundamentals_with_staleness = {
        "FRESH": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
                  "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4,
                  "regularMarketTime": now - 3600},
        "STALE": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
                  "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4,
                  "regularMarketTime": now - 30 * 24 * 3600},
        # No regularMarketTime at all (e.g. cache row predating this field) -
        # NOT treated as confirmed-stale, so it isn't dropped. Excluding on
        # missing data here would also hide every other still-alive symbol
        # whose cache just hasn't been refreshed since this feature shipped.
        "UNKNOWN": {"grossMargins": 0.55, "revenueGrowth": 0.30, "marketCap": 1_000_000_000,
                    "trailingPE": 24, "trailingEps": 2.0, "forwardEps": 2.4},
    }
    ranked_with_staleness = rank_moonshot_candidates(fundamentals_with_staleness)
    assert {r["symbol"] for r in ranked_with_staleness} == {"FRESH", "UNKNOWN"}

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
