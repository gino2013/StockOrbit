"""Plain-text daily summary email body (issue #17): same underlying data as
the dashboard's "進階建議" card (allocation drift, recent big swings,
upcoming earnings), just assembled server-side instead of client-side so a
scheduled script can email it without a browser. Pure formatting - callers
gather the three inputs from the existing `advice`/`market_moves`/`risk`
modules.

Returns None (not an empty string) when there's nothing worth flagging, so
the caller can skip sending - a daily "everything's fine!" email nobody
reads is worse than no email.
"""

# The exact fallback string advice.build_advice() appends when its `notes`
# list would otherwise be empty - filtered out here so "nothing to flag"
# doesn't itself count as something to flag.
_NO_ADVICE_MESSAGE = "目前配置在門檻範圍內，沒有明顯建議調整項目。"


def build_daily_digest(advice_notes: list[str], swings: list[dict], earnings_soon: list[dict]) -> str | None:
    real_advice = [n for n in advice_notes if n != _NO_ADVICE_MESSAGE]
    if not real_advice and not swings and not earnings_soon:
        return None

    lines = []
    if real_advice:
        lines.append("【配置提醒】")
        lines.extend(f"- {n}" for n in real_advice)

    if swings:
        if lines:
            lines.append("")
        lines.append("【近期大漲大跌】")
        for s in swings:
            lines.append(f"- {s['symbol']}：{'，'.join(s['notes'])}")

    if earnings_soon:
        if lines:
            lines.append("")
        lines.append("【即將公布財報】")
        for e in earnings_soon:
            lines.append(f"- {e['symbol']}：{e['next_earnings_date']}")

    lines.append("")
    lines.append("純客觀資訊呈現，不是投資建議。詳情請至 StockOrbit 儀表板查看。")
    return "\n".join(lines)
