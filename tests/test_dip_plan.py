import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

import pandas as pd

from app.domain.analytics import dip_plan as dp
from app.domain.analytics import steady


def demo():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    closes = pd.Series([100, 120, 110, 100, 102], index=idx, dtype=float)  # high 120, now 102 (-15%)
    with patch.object(steady, "MIN_SAMPLES", 1):
        r = dp.dip_plan(closes, 1000, [(-0.10, 0.25), (-0.20, 0.35), (-0.30, 0.40)], held_qty=10, held_cost=1000)
    assert r["high"] == 120 and abs(r["drawdown"] + 0.15) < 1e-9
    t1, t2, t3 = r["tiers"]
    assert t1["reached"] and not t2["reached"] and not t3["reached"]
    assert t1["trigger_price"] == 108 and t1["amount"] == 250 and abs(t1["shares"] - 250 / 108) < 1e-9
    assert abs(t2["to_go"] - (96 / 102 - 1)) < 1e-9  # 120 x 0.8 = 96
    # -10% days with a next... none have a 252-day forward window here -> None
    assert t1["forward_1y"] is None
    assert r["unallocated"] == 0 and r["avg_cost_now"] == 100
    shares = 250 / 108 + 350 / 96 + 400 / 84
    assert abs(r["avg_cost_after"] - 2000 / (10 + shares)) < 1e-9
    # nothing held yet: avg cost after is just the plan's own average price
    r0 = dp.dip_plan(closes, 1000, [(-0.10, 0.5)])
    assert r0["avg_cost_now"] is None and abs(r0["avg_cost_after"] - 108) < 1e-9 and r0["unallocated"] == 500

    assert dp.validate_tiers(dp.DEFAULT_TIERS) is None
    assert dp.validate_tiers([]) is not None
    assert dp.validate_tiers([(-0.2, 0.5), (-0.1, 0.5)]) is not None  # not getting deeper
    assert dp.validate_tiers([(0.1, 0.5)]) is not None  # positive threshold
    assert dp.validate_tiers([(-0.1, 0.6), (-0.2, 0.6)]) is not None  # over 100%
    assert dp.validate_tiers([(-0.1, 0)]) is not None
    print("ok")


if __name__ == "__main__":
    demo()
