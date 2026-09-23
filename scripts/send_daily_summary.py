"""Scheduled daily summary email - see .github/workflows/daily-summary.yml
(issue #17). Same source data as the dashboard's "進階建議" card (allocation
drift, recent big swings, upcoming earnings), emailed via
app.infrastructure.mailer instead of requiring the user to open the site.

Requires SMTP_HOST (mailer.is_enabled()) - a no-op with a log line when
unset, same as verification/reset email, so an unconfigured deploy doesn't
error. Skips a user entirely (no email) when their digest is empty for the
day - see app.domain.notifications.daily_digest for why.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.infrastructure import mailer  # noqa: E402
from app.infrastructure.db import SessionLocal, User, init_db  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402
from app.domain.analytics.market_moves import price_swings  # noqa: E402
from app.domain.analytics.risk import compute_risk_metrics  # noqa: E402
from app.domain.notifications.daily_digest import build_daily_digest  # noqa: E402
from app.domain.portfolio.advice import build_advice  # noqa: E402


def verified_users() -> list[User]:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email_verified.is_(True)).all()
    finally:
        db.close()


def send_for_user(user: User) -> str:
    with Repositories(user_id=user.id) as repo:
        snapshots = repo.latest_snapshots()
        targets = repo.targets()
    if not snapshots:
        return "no snapshot, skipping"

    symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
    advice_notes = build_advice(snapshots, targets)["advice"]
    swings = price_swings(symbols)
    earnings_soon = [r for r in compute_risk_metrics(symbols) if r.get("earnings_soon")]

    digest = build_daily_digest(advice_notes, swings, earnings_soon)
    if digest is None:
        return "nothing to report, skipping"

    mailer.send(user.email, "StockOrbit 每日摘要", digest)
    return "sent"


def main():
    if not mailer.is_enabled():
        print("SMTP_HOST not set - nothing to do.")
        return
    init_db()
    for user in verified_users():
        try:
            status = send_for_user(user)
        except Exception as e:
            status = f"failed: {type(e).__name__}: {e}"
        print(f"{user.email}: {status}")


if __name__ == "__main__":
    main()
