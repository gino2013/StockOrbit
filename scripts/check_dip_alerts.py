"""Scheduled crash email for buy-the-dip plans - see
.github/workflows/check-dip-alerts.yml (issue #441). For every plan with
alerts on, fetches each distinct symbol's history once, works out whether a
deeper tier was crossed (app.domain.notifications.dip_alerts.next_alert),
emails the owner, and persists alert_level. Same mailer as the other alerts.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pandas as pd  # noqa: E402

from app.domain.analytics.dip_plan import dip_plan  # noqa: E402
from app.domain.analytics.steady import analyze  # noqa: E402
from app.domain.notifications.dip_alerts import email_body, next_alert  # noqa: E402
from app.infrastructure import mailer  # noqa: E402
from app.infrastructure.db import DipPlan, SessionLocal, User, run_pending_migrations  # noqa: E402
from app.infrastructure.market_data import download_close  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402

APP_URL = os.environ.get("APP_URL", "https://stockorbit-lm36.onrender.com/")


def history(symbol: str) -> pd.Series | None:
    data = download_close(symbol, period="max")
    if isinstance(data, pd.DataFrame):
        data = data[symbol] if symbol in data else data.iloc[:, 0]
    data = data.dropna() if data is not None else None
    return data if data is not None and len(data) >= 2 else None


def main():
    if not mailer.is_enabled():
        print("SMTP_HOST not set - nothing to do.")
        return
    run_pending_migrations()  # job may run before the deploy that adds the alert columns
    db = SessionLocal()
    try:
        plans = db.query(DipPlan).filter(DipPlan.alert_enabled.is_(True)).all()
        if not plans:
            print("No dip plans with alerts on.")
            return
        closes = {s: history(s) for s in sorted({p.symbol for p in plans})}
        users = {u.id: u for u in db.query(User).filter(User.id.in_({p.user_id for p in plans})).all()}
        for plan in plans:
            series, user = closes.get(plan.symbol), users.get(plan.user_id)
            if series is None or user is None:
                continue
            tiers = [tuple(t) for t in json.loads(plan.tiers_json)]
            drawdown = float(series.iloc[-1] / series.max() - 1)
            level, send = next_alert(drawdown, tiers, plan.alert_level)
            if send:
                with Repositories(user_id=plan.user_id) as repo:
                    snaps = [h for h in repo.latest_snapshots() if h["quantity"] > 0]
                held = [h for h in snaps if h["symbol"] == plan.symbol]
                stocks = [h for h in snaps if h["symbol"] != "CASH"]
                cost = sum(h["cost_basis"] for h in stocks)
                unrealized = sum(h["market_value"] for h in stocks) / cost - 1 if cost else None
                result = dip_plan(series, plan.budget, tiers, sum(h["quantity"] for h in held), sum(h["cost_basis"] for h in held))
                mailer.send(
                    user.email,
                    f"StockOrbit 大跌提醒：{plan.symbol} 離高點 {drawdown:+.1%}，到了分批加碼第 {level} 階",
                    email_body(plan.symbol, result, analyze(series), unrealized, APP_URL),
                )
                print(f"{plan.symbol} ({user.email}): tier {level} at {drawdown:+.1%}")
            plan.alert_level = level
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
