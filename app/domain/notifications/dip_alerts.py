"""Crash email for the buy-the-dip plan (issue #441). Pure - the scheduled
script gathers prices / plan rows / holdings and persists `alert_level`.

`alert_level` is how many tiers this drawdown has already been emailed
about. A deeper tier than that -> one email; the same tier again -> nothing.
Once the price climbs back within half of the first tier (e.g. -5% for a
-10% first tier) the drawdown counts as over and the level resets to 0, so
the next crash emails again.
"""


def _days(d: int) -> str:
    return f"{d / 365:.1f} 年" if d >= 365 else f"{d} 天"


def next_alert(drawdown: float, tiers: list[tuple[float, float]], alert_level: int) -> tuple[int, bool]:
    """(new alert_level, send an email now?)"""
    reached = sum(1 for threshold, _ in tiers if drawdown <= threshold)
    if reached > alert_level:
        return reached, True
    if alert_level and drawdown > tiers[0][0] / 2:
        return 0, False
    return alert_level, False


def email_body(symbol: str, plan: dict, analysis: dict, portfolio_unrealized: float | None, site_url: str) -> str:
    """`plan`: dip_plan() result. `analysis`: steady.analyze() of the symbol."""
    reached = [t for t in plan["tiers"] if t["reached"]]
    tier = reached[-1]
    lines = [
        f"{symbol} 目前 ${plan['price']:,.2f}，離歷史高點 ${plan['high']:,.2f} 已經 {plan['drawdown']:+.1%}，"
        f"跌破你分批加碼計畫的第 {len(reached)} 階（{tier['threshold']:+.0%}）。",
        "",
        "照你事先寫好的計畫：",
        f"・這一階投入 ${tier['amount']:,.0f}（約 {tier['shares']:.2f} 股，觸發價 ${tier['trigger_price']:,.2f}）",
        f"・到目前為止累計應投入 ${sum(t['amount'] for t in reached):,.0f}（之前買過的不用重複買）",
    ]
    nxt = next((t for t in plan["tiers"] if not t["reached"]), None)
    if nxt:
        lines.append(f"・下一階在 {nxt['threshold']:+.0%}（${nxt['trigger_price']:,.2f}），還要再跌 {-nxt['to_go']:.1%}")
    lines += ["", f"歷史上的 {symbol}（資料從 {analysis['since'][:4]} 年起）："]
    if analysis["past_drops"]:
        lines.append(f"・跌到這個深度 {analysis['past_drops']} 次，每次都回到了前高；一半在 {_days(analysis['recovery_median_days'])}內，最久 {_days(analysis['recovery_max_days'])}。")
    else:
        lines.append("・這次比資料裡任何一次都深，沒有前例可參考。先確認現金跟負債安全。")
    for label, name in (("1y", "1 年"), ("3y", "3 年")):
        f = analysis["forward"].get(label)
        if f:
            lines.append(f"・在至少跌這麼深的日子買進，{name}後報酬中位數 {f['median']:+.1%}（{f['win_rate']:.0%} 的機率是賺的）。")
    lines.append(f"・史上最深一次是 {analysis['max_drawdown']:+.1%}（{analysis['max_drawdown_peak'][:4]}–{analysis['max_drawdown_trough'][:4]}）。")
    if portfolio_unrealized is not None:
        lines += ["", f"你的持股整體相對成本 {portfolio_unrealized:+.1%}。"]
    lines += [
        "",
        "慌的時候先問自己：這筆錢 3～5 年內會用到嗎？當初買的理由還成立嗎？有沒有借錢或融資？",
        f"完整數字：{site_url}#section-steady",
        "",
        "這是你自己設定的分批加碼計畫寄出的提醒。歷史不代表未來，不是投資建議。同一波下跌每一階只會通知一次；要關掉請到「分批加碼計畫」取消勾選。",
    ]
    return "\n".join(lines)
