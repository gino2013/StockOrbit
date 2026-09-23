"""Scheduled price-alert check - see .github/workflows/check-price-alerts.yml
(issue #18). For every un-triggered PriceAlert, fetches each distinct
symbol's current price once (regardless of how many users/alerts watch it),
works out which alerts crossed their threshold via
app.domain.notifications.price_alerts.alerts_to_trigger, marks them
triggered and emails the owning user - reusing app.infrastructure.mailer,
the same channel as the daily summary (issue #17), not a separate
notification path.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.infrastructure import mailer  # noqa: E402
from app.infrastructure.db import PriceAlert, SessionLocal, User, init_db  # noqa: E402
from app.infrastructure.market_data import download_close  # noqa: E402
from app.domain.notifications.price_alerts import alerts_to_trigger  # noqa: E402


def current_prices(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    data = download_close(symbols, period="5d")
    data = data.dropna(how="all").ffill().dropna()
    if data.empty:
        return {}
    return {symbol: float(data[symbol].iloc[-1]) for symbol in symbols if symbol in data.columns}


def main():
    if not mailer.is_enabled():
        print("SMTP_HOST not set - nothing to do.")
        return
    init_db()
    db = SessionLocal()
    try:
        rows = db.query(PriceAlert).filter(PriceAlert.triggered.is_(False)).all()
        if not rows:
            print("No active alerts.")
            return

        symbols = sorted({r.symbol for r in rows})
        prices = current_prices(symbols)
        alerts = [
            {"id": r.id, "symbol": r.symbol, "target_price": r.target_price, "direction": r.direction, "triggered": r.triggered}
            for r in rows
        ]
        to_trigger = alerts_to_trigger(alerts, prices)
        if not to_trigger:
            print(f"Checked {len(rows)} alert(s) across {len(symbols)} symbol(s), none crossed.")
            return

        by_id = {r.id: r for r in rows}
        users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in rows})).all()}
        for t in to_trigger:
            row = by_id[t["id"]]
            row.triggered = True
            row.triggered_at = datetime.now(timezone.utc)
            user = users_by_id.get(row.user_id)
            if not user:
                continue
            direction_text = "漲過" if row.direction == "above" else "跌破"
            price = prices[row.symbol]
            mailer.send(
                user.email,
                f"StockOrbit 價格提醒：{row.symbol}",
                f"{row.symbol} 目前價格 ${price:,.2f}，已{direction_text}你設定的目標價 ${row.target_price:,.2f}。\n\n"
                "純資訊提醒，不是投資建議。這個提醒不會再次觸發，要繼續追蹤請到 StockOrbit 重新設定。",
            )
            print(f"{row.symbol} ({user.email}): triggered at ${price:,.2f}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
