"""Which price alerts should fire right now (issue #18). Pure - callers
gather the alert rows and current prices from the DB/yfinance.

An alert never fires twice for the same crossing: once triggered, the
caller is expected to persist `triggered=True` on that row, and this
function skips anything already marked triggered on its next run. There is
no auto re-arm (e.g. the price dips back below and crosses again) - that
would need a policy decision issue #18 doesn't make, so a triggered alert
just sits there until the user deletes and re-creates it.
"""


def alerts_to_trigger(alerts: list[dict], current_prices: dict[str, float]) -> list[dict]:
    result = []
    for alert in alerts:
        if alert["triggered"]:
            continue
        price = current_prices.get(alert["symbol"])
        if price is None:
            continue
        if alert["direction"] == "above" and price >= alert["target_price"]:
            result.append(alert)
        elif alert["direction"] == "below" and price <= alert["target_price"]:
            result.append(alert)
    return result
