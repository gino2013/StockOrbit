import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from app import compounder_checklist as cc


def demo():
    fundamentals = {
        "profitMargins": 0.25,
        "debtToEquity": 50,
        "revenueGrowth": 0.1,
        "earningsGrowth": 0.08,
        "marketCap": 5_000_000_000,
    }
    # 6 years of steady +10% returns: low volatility, no erosion, all checks pass.
    steady_returns = [0.10] * 6

    with patch.object(cc, "compute_risk_metrics", return_value=[{"volatility_90d": 0.15}]), \
         patch.object(cc, "fetch_annual_returns", return_value=steady_returns):
        result = cc.build_compounder_checklist("AAA", fundamentals)

    by_label = {c["label"]: c for c in result["checks"]}
    assert result["symbol"] == "AAA"
    assert all(c["passed"] for c in result["checks"]), result["checks"]

    # A volatile stock with a real geometric/arithmetic gap should fail the
    # erosion check even though its arithmetic-average return looks fine.
    volatile_returns = [0.9, -0.6, 0.9, -0.6, 0.9, -0.6]
    with patch.object(cc, "compute_risk_metrics", return_value=[{"volatility_90d": 0.55}]), \
         patch.object(cc, "fetch_annual_returns", return_value=volatile_returns):
        result = cc.build_compounder_checklist("BBB", fundamentals)
    erosion_check = next(c for c in result["checks"] if "波動沒有嚴重侵蝕" in c["label"])
    assert erosion_check["passed"] is False

    # Missing fundamentals data shows up as "無資料", not a crash or a false pass.
    with patch.object(cc, "compute_risk_metrics", return_value=[]), \
         patch.object(cc, "fetch_annual_returns", return_value=[]):
        result = cc.build_compounder_checklist("CCC", {})
    profit_check = next(c for c in result["checks"] if "毛利率" in c["label"])
    assert profit_check["passed"] is False
    assert profit_check["value"] == "無資料"


if __name__ == "__main__":
    demo()
    print("OK")
