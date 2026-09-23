import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.notifications.daily_digest import build_daily_digest

_NO_ADVICE = "目前配置在門檻範圍內，沒有明顯建議調整項目。"


def demo():
    # nothing worth flagging -> None, not an empty-but-truthy string.
    assert build_daily_digest([_NO_ADVICE], [], []) is None
    assert build_daily_digest([], [], []) is None

    # real advice note alone is enough to send.
    digest = build_daily_digest(["AAPL 佔投資組合 25.0%，超過集中度門檻 20%，建議考慮減碼分散風險。"], [], [])
    assert digest is not None
    assert "【配置提醒】" in digest
    assert "AAPL 佔投資組合 25.0%" in digest
    assert "【近期大漲大跌】" not in digest

    # the filler "all good" message must never leak into the digest even
    # when something else (a swing) does trigger a send.
    digest = build_daily_digest([_NO_ADVICE], [{"symbol": "NVDA", "notes": ["單日大漲 8.0%"]}], [])
    assert _NO_ADVICE not in digest
    assert "【近期大漲大跌】" in digest
    assert "NVDA：單日大漲 8.0%" in digest

    # all three sections render together, in order.
    digest = build_daily_digest(
        ["QQQ 目前配置 35.0%，目標 30.0%，偏離 5.0%，建議減碼以回到目標配置。"],
        [{"symbol": "NVDA", "notes": ["單日大漲 8.0%"]}],
        [{"symbol": "MSFT", "next_earnings_date": "2026-10-01"}],
    )
    assert digest.index("【配置提醒】") < digest.index("【近期大漲大跌】") < digest.index("【即將公布財報】")
    assert "MSFT：2026-10-01" in digest


if __name__ == "__main__":
    demo()
    print("OK")
