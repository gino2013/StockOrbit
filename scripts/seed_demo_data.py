"""Seed a *disposable* DB with fabricated demo data for README screenshots.

Never run against the real DATABASE_URL. Use a throwaway sqlite file:

    DATABASE_URL=sqlite:///./demo.db .venv/bin/python scripts/seed_demo_data.py
    DATABASE_URL=sqlite:///./demo.db .venv/bin/uvicorn app.main:app --port 8000

All holdings / transactions / notes / goal below are invented - not a real
account. Public-market data the dashboard shows (fundamentals, technical
indicators) is fetched live from yfinance for real well-known symbols, which
is not personal financial data.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import (  # noqa: E402
    Base,
    ExchangeRateSnapshot,
    InvestmentGoal,
    PositionNote,
    PositionSnapshot,
    SessionLocal,
    TargetAllocation,
    Transaction,
    engine,
)

ACCOUNT = "DEMO-00000000"
TODAY = date(2026, 8, 29)

# symbol -> (shares, avg cost, current price). market_value / gains derived.
HOLDINGS = {
    "AAPL": (20, 160.00, 190.00),
    "MSFT": (10, 350.00, 420.00),
    "VOO": (8, 500.00, 575.00),
    "QQQ": (6, 466.67, 550.00),
    "NVDA": (15, 185.00, 173.33),  # deliberately underwater: exercises 稅務效率分析
    "CASH": (1, 128.00, 128.00),
}

TARGETS = {"AAPL": 0.30, "VOO": 0.40, "QQQ": 0.30}

NOTES = {
    "AAPL": "組合裡的權值定錨。買進理由：品牌護城河 + 服務業務高毛利，自由現金流穩定，回購持續縮股本。目標佔比 30%，跌破 $150 分批加碼。",
    "MSFT": "雲 + AI 雙引擎：Azure 成長加上 Copilot 開始變現。長期核心持股，不設減碼價，看營運槓桿。",
    "VOO": "整體市場 beta。買進理由：用最低成本一次買下 S&P 500，當組合的壓艙石，抵銷個股選錯的風險。目標佔比 40%。",
    "QQQ": "Nasdaq-100 核心持股。買進理由：一次買到美股大型成長股龍頭，費用率低，長期做組合的成長引擎。目標佔比 30%。",
    "NVDA": "加速運算的「賣鏟人」。買進理由：資料中心 GPU 需求循環還沒到頂。波動大，只用小部位，漲多會分批減碼。",
}

# (days_ago, trans_type, symbol, quantity, trade_price, amount, description)
# amount sign: negative = cash out (buy / deposit), positive = cash in.
TRANSACTIONS = [
    (760, "DEPOSIT", None, 0, 0, -12000.00, "ACH deposit"),
    (735, "BOUGHT", "VOO", 6, 470.00, -2820.00, "Bought 6 VOO @ 470.00"),
    (735, "BOUGHT", "AAPL", 12, 150.00, -1800.00, "Bought 12 AAPL @ 150.00"),
    (720, "BOUGHT", "MSFT", 8, 330.00, -2640.00, "Bought 8 MSFT @ 330.00"),
    (610, "BOUGHT", "QQQ", 4, 430.00, -1720.00, "Bought 4 QQQ @ 430.00"),
    (540, "DEPOSIT", None, 0, 0, -6000.00, "ACH deposit"),
    (520, "BOUGHT", "NVDA", 10, 95.00, -950.00, "Bought 10 NVDA @ 95.00"),
    (400, "DIV", "AAPL", 0, 0, 12.00, "AAPL cash dividend"),
    (400, "DIV", "MSFT", 0, 0, 18.40, "MSFT cash dividend"),
    (395, "DIV", "VOO", 0, 0, 21.60, "VOO cash dividend"),
    (360, "BOUGHT", "AAPL", 8, 175.00, -1400.00, "Bought 8 AAPL @ 175.00"),
    (300, "SOLD", "NVDA", -5, 140.00, 700.00, "Sold 5 NVDA @ 140.00"),
    (290, "DIV", "AAPL", 0, 0, 12.80, "AAPL cash dividend"),
    (280, "DIV", "QQQ", 0, 0, 9.20, "QQQ cash dividend"),
    (210, "BOUGHT", "NVDA", 10, 120.00, -1200.00, "Bought 10 NVDA @ 120.00"),
    (190, "DIV", "MSFT", 0, 0, 19.10, "MSFT cash dividend"),
    (185, "DIV", "VOO", 0, 0, 22.40, "VOO cash dividend"),
    (150, "BOUGHT", "MSFT", 2, 400.00, -800.00, "Bought 2 MSFT @ 400.00"),
    (120, "SOLD", "AAPL", -12, 195.00, 2340.00, "Sold 12 AAPL @ 195.00"),
    (95, "DIV", "AAPL", 0, 0, 13.20, "AAPL cash dividend"),
    (90, "DIV", "QQQ", 0, 0, 10.10, "QQQ cash dividend"),
    (85, "DIV", "MSFT", 0, 0, 20.00, "MSFT cash dividend"),
    (80, "BOUGHT", "QQQ", 2, 520.00, -1040.00, "Bought 2 QQQ @ 520.00"),
    (30, "DIV", "VOO", 0, 0, 23.10, "VOO cash dividend"),
]

# For the allocation / concentration history charts we need several snapshots
# over time. Prices ramp from `factor` of today's price up to today's; a few
# quantities step to line up with the buys/sells above.
SNAPSHOT_MONTHS = 15
QTY_HISTORY = {  # symbol -> list of (months_ago_at_least, quantity)
    "AAPL": [(0, 20), (4, 32), (12, 20), (15, 12)],
    "MSFT": [(0, 10), (5, 8), (15, 8)],
    "VOO": [(0, 8), (15, 6)],
    "QQQ": [(0, 6), (3, 4), (15, 4)],
    "NVDA": [(0, 15), (7, 5), (10, 10), (15, 0)],
    "CASH": [(0, 1), (15, 1)],
}


def _qty_at(symbol: str, months_ago: int) -> float:
    for threshold, qty in QTY_HISTORY[symbol]:
        if months_ago >= threshold:
            return qty
    return QTY_HISTORY[symbol][-1][1]


def _wipe(db):
    for model in (
        PositionSnapshot, TargetAllocation, ExchangeRateSnapshot,
        Transaction, PositionNote, InvestmentGoal,
    ):
        db.query(model).delete()


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        _wipe(db)

        # --- current + historical position snapshots ---
        for m in range(SNAPSHOT_MONTHS, -1, -1):
            snap_at = datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=timezone.utc) - timedelta(days=30 * m)
            factor = 1.0 if m == 0 else 0.70 + 0.30 * (SNAPSHOT_MONTHS - m) / SNAPSHOT_MONTHS
            for symbol, (_, avg_cost, price) in HOLDINGS.items():
                qty = HOLDINGS[symbol][0] if m == 0 else _qty_at(symbol, m)
                if qty <= 0:
                    continue
                px = price if symbol == "CASH" else round(price * factor, 2)
                db.add(PositionSnapshot(
                    account_number=ACCOUNT, symbol=symbol, quantity=qty,
                    cost_basis=round(avg_cost * qty, 2) if symbol != "CASH" else 128.0,
                    market_value=round(px * qty, 2), price=px, snapshot_at=snap_at,
                ))

        for symbol, weight in TARGETS.items():
            db.add(TargetAllocation(symbol=symbol, target_weight=weight))

        db.add(ExchangeRateSnapshot(pair="USDTWD", rate=31.82,
                                    fetched_at=datetime.now(timezone.utc)))

        for days_ago, ttype, symbol, qty, price, amount, desc in TRANSACTIONS:
            row = {
                "account_number": ACCOUNT, "symbol": symbol, "trans_type": ttype,
                "report_date": TODAY - timedelta(days=days_ago), "quantity": qty,
                "trade_price": price, "amount": amount, "description": desc,
            }
            db.add(Transaction(id=Transaction.make_id(row), **row))

        for symbol, note in NOTES.items():
            db.add(PositionNote(symbol=symbol, note=note))

        db.add(InvestmentGoal(id="default", target_amount=100000.0,
                              target_date=date(2032, 1, 1)))

        db.commit()
    finally:
        db.close()


def _check():
    db = SessionLocal()
    try:
        latest = db.query(PositionSnapshot.snapshot_at).order_by(
            PositionSnapshot.snapshot_at.desc()).first()[0]
        rows = db.query(PositionSnapshot).filter(PositionSnapshot.snapshot_at == latest).all()
        total_mv = sum(r.market_value for r in rows)
        total_cost = sum(r.cost_basis for r in rows)
        assert abs(total_mv - 18628.0) < 1.0, total_mv
        assert abs((total_mv - total_cost) / total_cost - 0.1356) < 0.01
        assert db.query(PositionNote).count() == 5
        assert db.query(Transaction).filter(Transaction.trans_type == "SOLD").count() == 2
        assert abs(sum(w for w in TARGETS.values()) - 1.0) < 1e-9
        nvda = next(r for r in rows if r.symbol == "NVDA")
        assert nvda.market_value < nvda.cost_basis, "NVDA should be underwater for 稅務效率分析"
        print(f"OK - {len(rows)} holdings, total MV ${total_mv:,.0f}, "
              f"gain {(total_mv - total_cost) / total_cost:+.1%}, "
              f"{db.query(Transaction).count()} transactions")
    finally:
        db.close()


if __name__ == "__main__":
    if "sqlite" not in os.environ.get("DATABASE_URL", "sqlite:///./stockorbit.db"):
        sys.exit("refusing to seed a non-sqlite DATABASE_URL")
    seed()
    _check()
