"""Scheduled allocation-drift-alert check - see
.github/workflows/check-allocation-alerts.yml (issue #320). For every user
with an AllocationAlert, compares their current allocation (from the
latest snapshot) against their target allocation - no market-data fetch
needed at all, unlike price alerts, since this is purely a function of
already-stored snapshot/target data.

Alerts that newly cross their drift threshold get emailed and marked
triggered; alerts whose drift has recovered back under threshold get
silently reset (no email) so a future re-crossing notifies again - see
AllocationAlert's docstring (app/infrastructure/db.py) for why this can't
reuse PriceAlert's never-reset behavior.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.infrastructure import mailer  # noqa: E402
from app.infrastructure.db import AllocationAlert, SessionLocal, User, init_db  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402
from app.domain.notifications.allocation_alerts import alerts_to_check  # noqa: E402
from app.domain.portfolio.advice import compute_allocation  # noqa: E402


def check_for_user(db, user: User) -> str:
    rows = db.query(AllocationAlert).filter(AllocationAlert.user_id == user.id).all()
    if not rows:
        return "no alerts"

    with Repositories(user_id=user.id) as repo:
        snapshots = repo.latest_snapshots()
        targets = repo.targets()
    if not snapshots:
        return "no snapshot, skipping"

    current_weights = compute_allocation(snapshots)
    alerts = [{"id": r.id, "symbol": r.symbol, "threshold": r.threshold, "triggered": r.triggered} for r in rows]
    to_trigger, to_reset = alerts_to_check(alerts, current_weights, targets)

    by_id = {r.id: r for r in rows}
    for t in to_trigger:
        row = by_id[t["id"]]
        row.triggered = True
        row.triggered_at = datetime.now(timezone.utc)
        direction_text = "超配" if t["drift"] > 0 else "低配"
        mailer.send(
            user.email,
            f"StockOrbit 配置偏離提醒：{row.symbol}",
            f"{row.symbol} 目前佔比 {t['current_weight']:.1%}，目標 {t['target_weight']:.1%}，"
            f"{direction_text} {abs(t['drift']):.1%}，超過你設定的門檻 {row.threshold:.1%}。\n\n"
            "純資訊提醒，不是投資建議。偏離回到門檻內後會自動重置，之後再超標會重新通知。",
        )
    for r in to_reset:
        by_id[r["id"]].triggered = False
        by_id[r["id"]].triggered_at = None

    db.commit()
    return f"{len(to_trigger)} triggered, {len(to_reset)} reset (of {len(rows)} alert(s))"


def main():
    if not mailer.is_enabled():
        print("SMTP_HOST not set - nothing to do.")
        return
    init_db()
    db = SessionLocal()
    try:
        users = db.query(User).join(AllocationAlert, AllocationAlert.user_id == User.id).distinct().all()
        if not users:
            print("No users with allocation alerts.")
            return
        for user in users:
            status = check_for_user(db, user)
            print(f"{user.email}: {status}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
