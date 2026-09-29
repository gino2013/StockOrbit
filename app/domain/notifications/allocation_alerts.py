"""Which allocation-drift alerts should fire (or reset) right now
(issue #320). Pure - callers gather the alert rows and current/target
weights from the DB.

Unlike price_alerts.alerts_to_trigger, this also produces a reset list:
allocation drift is an ongoing state, not a one-time crossing, so once it
recovers back under the threshold the alert is reset (silently, no email)
so a future re-crossing notifies again instead of staying permanently
silenced.
"""


def alerts_to_check(
    alerts: list[dict], current_weights: dict[str, float], target_weights: dict[str, float]
) -> tuple[list[dict], list[dict]]:
    """Returns (to_trigger, to_reset). `to_trigger` entries carry the
    alert's own fields plus current_weight/target_weight/drift for the
    caller to build a message from."""
    to_trigger, to_reset = [], []
    for alert in alerts:
        current = current_weights.get(alert["symbol"], 0.0)
        target = target_weights.get(alert["symbol"], 0.0)
        drift = current - target
        over_threshold = abs(drift) > alert["threshold"]
        if over_threshold and not alert["triggered"]:
            to_trigger.append({**alert, "current_weight": current, "target_weight": target, "drift": drift})
        elif not over_threshold and alert["triggered"]:
            to_reset.append(alert)
    return to_trigger, to_reset
