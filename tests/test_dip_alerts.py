import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.notifications.dip_alerts import email_body, next_alert

TIERS = [(-0.10, 0.25), (-0.20, 0.35), (-0.30, 0.40)]


def demo():
    assert next_alert(-0.05, TIERS, 0) == (0, False)   # nothing reached
    assert next_alert(-0.12, TIERS, 0) == (1, True)    # first tier -> email
    assert next_alert(-0.15, TIERS, 1) == (1, False)   # same tier again -> quiet
    assert next_alert(-0.08, TIERS, 1) == (1, False)   # bounced, still below -5%
    assert next_alert(-0.25, TIERS, 1) == (2, True)    # deeper tier -> email
    assert next_alert(-0.35, TIERS, 0) == (3, True)    # gap down past all three: one email
    assert next_alert(-0.04, TIERS, 2) == (0, False)   # recovered within -5% -> reset
    assert next_alert(-0.11, TIERS, 0) == (1, True)    # next crash emails again

    plan = {"price": 640.0, "high": 760.0, "drawdown": 640 / 760 - 1, "tiers": [
        {"threshold": -0.1, "amount": 1250, "shares": 1.83, "trigger_price": 684, "reached": True, "to_go": 0.07},
        {"threshold": -0.2, "amount": 1750, "shares": 2.88, "trigger_price": 608, "reached": False, "to_go": -0.05},
    ]}
    analysis = {"since": "1999-03-10", "past_drops": 7, "recovery_median_days": 116, "recovery_max_days": 5400,
                "forward": {"1y": {"median": 0.14, "win_rate": 0.76}, "3y": None},
                "max_drawdown": -0.83, "max_drawdown_peak": "2000-03-10", "max_drawdown_trough": "2002-10-09"}
    body = email_body("QQQ", plan, analysis, -0.02, "https://example.test/")
    assert "第 1 階" in body and "$1,250" in body and "還要再跌 5.0%" in body
    assert "7 次" in body and "116 天內" in body and "最久 14.8 年" in body and "+14.0%" in body and "3 年後" not in body and "-83.0%" in body
    assert "-2.0%" in body and "https://example.test/#section-steady" in body
    print("ok")


if __name__ == "__main__":
    demo()
