import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.screening.moonshot_eval import (
    build_evaluation,
    data_confidence,
    revenue_cagr_3y_pct,
    roic_pct,
    validate_judgment,
)

NAN = float("nan")

JUDGMENT = {
    "schools": {
        "phelps_mayer": {"score": 3, "reason": "市值已大"},
        "fisher": {"score": 5, "reason": "研發強"},
        "lynch": {"score": 4, "reason": "PEG 合理", "category": "快速成長型"},
        "buffett_munger": {"score": 4, "reason": "生態系", "moat_type": ["轉換成本"]},
    },
    "risks": ["競爭", "客戶集中", "景氣循環"],
    "summary": "成長快但估值不低。",
}


def demo():
    # NVDA FY2026 numbers: tax 21383/141450 = 15.1%, invested 11040+157293-10605
    assert roic_pct(130387, 21383, 141450, 11040, 157293, 10605) == 70.2
    # tax benefit (negative rate) -> 21% fallback; missing debt/cash count as 0
    assert roic_pct(100, -10, 50, None, 1000, None) == 7.9
    assert roic_pct(100, 0, 100, 0, -50, 0) is None  # negative invested capital
    assert roic_pct(NAN, 0, 100, 0, 100, 0) is None

    assert revenue_cagr_3y_pct([800, 400, 200, 100, NAN]) == 100.0
    assert revenue_cagr_3y_pct([800, 400, 200]) is None  # under 4 years
    assert revenue_cagr_3y_pct([800, 400, 200, 0]) is None

    assert data_confidence({"a": 1, "b": 2, "c": 3, "d": 4}) == "high"
    assert data_confidence({"a": 1, "b": None, "c": 3, "d": 4}) == "medium"
    assert data_confidence({"a": None, "b": None, "c": 3, "d": 4}) == "low"

    assert validate_judgment(JUDGMENT) == []
    bad = copy.deepcopy(JUDGMENT)
    bad["schools"]["fisher"]["score"] = 6
    bad["schools"]["lynch"]["category"] = "成長型"
    bad["risks"] = bad["risks"][:2]
    bad["summary"] = "字" * 101
    assert len(validate_judgment(bad)) == 4
    bool_score = copy.deepcopy(JUDGMENT)
    bool_score["schools"]["fisher"]["score"] = True
    assert validate_judgment(bool_score)
    missing_school = copy.deepcopy(JUDGMENT)
    del missing_school["schools"]["fisher"]
    assert validate_judgment(missing_school)

    # total and confidence come from code even if the judgment claims otherwise
    inputs = {"symbol": "NVDA", "company_name": "NVIDIA", "key_metrics": {
        "market_cap_usd": 1e12, "roic_pct": 70.9, "revenue_growth_3y_pct": None, "insider_ownership_pct": 4.0}}
    e = build_evaluation({**JUDGMENT, "total_score": 20, "data_confidence": "high"}, inputs)
    assert e["total_score"] == 16 and e["data_confidence"] == "medium"
    assert e["key_metrics"] is inputs["key_metrics"]


if __name__ == "__main__":
    demo()
    print("OK")
