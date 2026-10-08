import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.portfolio.note_metrics import build_note_metrics


def demo():
    snaps = [
        {"symbol": "NVDA", "quantity": 10.0, "cost_basis": 1766.5, "market_value": 2205.7},
        {"symbol": "VOO", "quantity": 2.0, "cost_basis": 1200.0, "market_value": 1400.0},
        {"symbol": "CASH", "quantity": 1.0, "cost_basis": 1000.0, "market_value": 1000.0},
    ]
    fund = {"NVDA": {"trailingPE": 45.0, "pegRatio": 0.6, "returnOnEquity": 1.17, "revenueGrowth": 1.05,
                     "targetMeanPrice": 323.0, "recommendationKey": "strong_buy", "beta": 2.21}}
    m = build_note_metrics(snaps, fund, {"NVDA": 0.10})
    assert "CASH" not in m
    nv = dict(m["NVDA"])
    assert nv["現價"] == "$220.57" and nv["持有均價"] == "$176.65（+24.9%）"
    assert nv["佔比"] == "47.9% / 目標 10%"  # 2205.7 / 4605.7, weight includes cash like the rebalance table
    assert nv["PE"] == "45.0" and nv["ROE"] == "117.0%" and nv["Beta"] == "2.21"
    assert nv["分析師目標價"] == "$323.00（+46.4%） strong_buy"
    # ETF with no fundamentals / no target: only price-based rows, nothing blank or crashing.
    vo = dict(m["VOO"])
    assert set(vo) == {"現價", "持有均價", "佔比"} and vo["佔比"] == "30.4%"
    # zero quantity / empty portfolio must not divide by zero.
    assert build_note_metrics([{"symbol": "X", "quantity": 0.0, "cost_basis": 0.0, "market_value": 0.0}], {}, {}) == {"X": []}


if __name__ == "__main__":
    demo()
    print("OK")
