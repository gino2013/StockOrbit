"""issue #96: latest_snapshots() must group by symbol and sum across
accounts, not return one row per (account, symbol) PositionSnapshot row -
firstrade_client.fetch_positions() fetches per account, so a login with two
accounts both holding the same symbol produces two rows for it.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "latest_snapshots_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def _pos(account, sym, qty, price):
    mv = qty * price
    return {"account_number": account, "symbol": sym, "quantity": qty,
            "cost_basis": mv, "market_value": mv, "price": price, "raw_json": "{}"}


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(id="u1", email="u1@x.com", password_hash="h", is_owner=True))
    db.commit()
    db.close()

    with Repositories("u1") as repo:
        # Same login, two accounts, one shared symbol (AAPL) + one
        # account-exclusive symbol (VOO) each.
        repo.save_refresh(
            positions=[
                _pos("A1", "AAPL", 10, 100.0),
                _pos("A1", "VOO", 5, 400.0),
                _pos("A2", "AAPL", 20, 100.0),
                _pos("A2", "MSFT", 3, 300.0),
            ],
            transactions=[], rate=None,
        )
        snapshots = repo.latest_snapshots()

    by_symbol = {s["symbol"]: s for s in snapshots}
    # grouped, not duplicated: exactly one row per symbol, not one per
    # (account, symbol) pair.
    assert set(by_symbol) == {"AAPL", "VOO", "MSFT"}, by_symbol
    assert len(snapshots) == 3

    aapl = by_symbol["AAPL"]
    assert aapl["quantity"] == 30  # 10 + 20 across the two accounts
    assert aapl["market_value"] == 3000.0  # 1000 + 2000
    assert aapl["cost_basis"] == 3000.0
    assert aapl["price"] == 100.0  # 3000 / 30 - same quote both accounts, so unchanged

    # account-exclusive symbols pass through unaggregated (nothing to sum).
    assert by_symbol["VOO"]["quantity"] == 5
    assert by_symbol["VOO"]["market_value"] == 2000.0
    assert by_symbol["MSFT"]["quantity"] == 3
    assert by_symbol["MSFT"]["market_value"] == 900.0

    # --- different accounts holding the same symbol at different prices
    # (a realistic weighted-average case, not just "same quote twice") ---
    with Repositories("u1") as repo:
        repo.save_refresh(
            positions=[
                _pos("A1", "TSLA", 10, 200.0),  # $2000
                _pos("A2", "TSLA", 30, 240.0),  # $7200
            ],
            transactions=[], rate=None,
        )
        snapshots2 = repo.latest_snapshots()
    tsla = next(s for s in snapshots2 if s["symbol"] == "TSLA")
    assert tsla["quantity"] == 40
    assert tsla["market_value"] == 9200.0
    assert abs(tsla["price"] - 9200.0 / 40) < 1e-9  # weighted average, not either account's raw quote

    # a fresh symbol-per-refresh call also replaces the "latest" snapshot
    # set entirely (save_refresh always snapshots at "now") - the AAPL/VOO/
    # MSFT set from the first refresh should no longer be "latest".
    with Repositories("u1") as repo:
        latest = repo.latest_snapshots()
    assert {s["symbol"] for s in latest} == {"TSLA"}


if __name__ == "__main__":
    demo()
    print("OK")
