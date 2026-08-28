import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.compound_curve import (
    _annual_returns_from_daily,
    arithmetic_mean_return,
    build_compound_curve,
    compound_path,
    geometric_mean_return,
    smooth_path,
)


def demo():
    # The +50%/-40% two-year example: real compounding ends at 90 (a -10%
    # total return), not the 110.25 an arithmetic-mean-based projection
    # would suggest. This is the whole point of the feature.
    returns = [0.5, -0.4]
    assert abs(compound_path(returns, 100)[-1] - 90) < 1e-9
    assert abs(arithmetic_mean_return(returns) - 0.05) < 1e-9

    geo = geometric_mean_return(returns)
    assert abs(geo - (-0.05131670194948623)) < 1e-9
    # by construction, compounding the geometric mean n times reproduces the
    # exact real ending value -- that's the defining property of CAGR.
    assert abs(smooth_path(geo, 2, 100)[-1] - 90) < 1e-6

    result = build_compound_curve(returns, future_periods=3, initial_value=100)
    assert result["historical_periods"] == 2
    assert result["future_periods"] == 3
    assert len(result["real_path"]) == 3  # initial + 2 years
    assert len(result["geometric_path"]) == 6  # initial + 2 historical + 3 future
    assert len(result["arithmetic_path"]) == 6

    # The geometric path only has to match the real path at the start and
    # end of the historical range (that's the defining property of CAGR) —
    # the middle diverges on purpose, since the real path jumped to 150
    # before crashing while the smooth curve never does either.
    assert abs(result["geometric_path"][0] - result["real_path"][0]) < 1e-6
    assert abs(result["geometric_path"][2] - result["real_path"][2]) < 1e-6
    # The arithmetic-mean path does NOT match the real ending value (it
    # overstates whenever returns vary), which is exactly the mistake this
    # feature exists to make visible.
    assert result["arithmetic_path"][2] > result["real_path"][2] + 1

    # a flat, unchanging return has no gap between the two averages at all.
    flat = [0.1, 0.1, 0.1]
    assert abs(geometric_mean_return(flat) - arithmetic_mean_return(flat)) < 1e-9

    # geometric_cumulative_return is the % implied by compounding the
    # geometric mean all the way through the future projection (not just
    # the historical range) -- e.g. "+X%" ready to show directly, so the
    # user doesn't have to mentally compound the annual rate themselves.
    assert abs(result["geometric_cumulative_return"] - (result["geometric_path"][-1] / 100 - 1)) < 1e-9
    assert abs(result["arithmetic_cumulative_return"] - (result["arithmetic_path"][-1] / 100 - 1)) < 1e-9
    # with future_periods=0, the geometric cumulative return over the
    # historical range alone must reproduce the real total return exactly.
    no_future = build_compound_curve(returns, future_periods=0, initial_value=100)
    assert abs(no_future["geometric_cumulative_return"] - (-0.10)) < 1e-6

    # _annual_returns_from_daily (the shared core of both fetch_annual_returns
    # and fetch_portfolio_annual_returns) on a synthetic series -- no network
    # call needed to verify the year-bucketing logic itself.
    dates = pd.date_range("2021-06-01", "2023-12-31", freq="D")
    prices = pd.Series(range(len(dates)), index=dates, dtype=float) + 100
    yearly_returns = _annual_returns_from_daily(prices, 2021, 2023)
    assert len(yearly_returns) == 3  # 2021 (partial), 2022, 2023

    # A request range starting before the series actually has data (e.g. a
    # young holding whose real history only starts in 2021, requested from
    # 2015) must not silently manufacture years with no underlying data --
    # the year filter just has nothing to match before 2021, so it returns
    # exactly the same 3 years rather than padding in bogus zero-return
    # years for 2015-2020. This is what lets fetch_portfolio_annual_returns
    # compute an honest actual_start_year instead of mislabeling the range.
    same_as_wider_request = _annual_returns_from_daily(prices, 2015, 2023)
    assert same_as_wider_request == yearly_returns


if __name__ == "__main__":
    demo()
    print("OK")
