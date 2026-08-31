import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "csv_import.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "c" * 40

from app.infrastructure.csv_import import (  # noqa: E402
    CsvImportError,
    parse_positions,
    parse_transactions,
)


def _err(fn, text):
    try:
        fn(text)
    except CsvImportError as e:
        return str(e)
    raise AssertionError("expected CsvImportError")


def demo():
    # --- positions: happy path, avg_cost -> cost_basis, derived market_value ---
    rows = parse_positions("symbol,quantity,avg_cost,price\nvoo,10,400,450\nqqq,5,,\n")
    assert rows[0]["symbol"] == "VOO"
    assert rows[0]["cost_basis"] == 4000.0  # 400 * 10
    assert rows[0]["market_value"] == 4500.0  # 450 * 10, derived
    assert rows[0]["account_number"] == "IMPORT"
    assert rows[1]["cost_basis"] == 0.0 and rows[1]["market_value"] == 0.0

    # explicit cost_basis / market_value win over derivation; $ and , tolerated
    rows = parse_positions('symbol,quantity,cost_basis,market_value\nAAPL,"1,000","$50,000","$90,000"\n')
    assert rows[0]["quantity"] == 1000.0 and rows[0]["cost_basis"] == 50000.0 and rows[0]["market_value"] == 90000.0

    # --- positions: errors ---
    assert "缺少必要欄位" in _err(parse_positions, "symbol,price\nvoo,1\n")
    assert "不認得的欄位" in _err(parse_positions, "symbol,quantity,bogus\nvoo,1,x\n")
    assert "第 2 列" in _err(parse_positions, "symbol,quantity\nvoo,abc\n")
    assert "第 3 列：symbol 空白" in _err(parse_positions, "symbol,quantity\nvoo,1\n,5\n")
    assert "沒有任何資料列" in _err(parse_positions, "symbol,quantity\n")

    # --- transactions: type normalisation + amount derivation ---
    rows = parse_transactions(
        "date,type,symbol,quantity,price\n"
        "2026-01-05,buy,VOO,10,400\n"
        "01/06/2026,SOLD,VOO,4,450\n"
        "2026/02/01,dividend,VOO,,\n"
    )
    assert rows[0]["trans_type"] == "BOUGHT" and rows[0]["amount"] == -4000.0
    assert rows[1]["trans_type"] == "SOLD" and rows[1]["amount"] == 1800.0
    assert str(rows[1]["report_date"]) == "2026-01-06"
    assert rows[2]["trans_type"] == "DIV" and rows[2]["amount"] == 0.0 and rows[2]["symbol"] == "VOO"

    # explicit amount is kept as-is (signed)
    rows = parse_transactions("date,type,amount,description\n2026-03-01,deposit,2500,ACH in\n")
    assert rows[0]["trans_type"] == "DEPOSIT" and rows[0]["amount"] == 2500.0 and rows[0]["description"] == "ACH in"

    # unknown type passes through upper-cased
    rows = parse_transactions("date,type\n2026-03-02,reinvest\n")
    assert rows[0]["trans_type"] == "REINVEST"

    # --- transactions: errors ---
    assert "缺少必要欄位" in _err(parse_transactions, "date,symbol\n2026-01-01,VOO\n")
    assert "格式不支援" in _err(parse_transactions, "date,type\n05-01-2026,buy\n")
    assert "第 2 列：quantity" in _err(parse_transactions, "date,type,quantity\n2026-01-01,buy,ten\n")

    # --- round trip through save_refresh ---
    from app.infrastructure.db import Base, SessionLocal, User, engine
    from app.infrastructure.repositories import Repositories

    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(id="u1", email="u1@x.com", password_hash="h"))
    db.commit()
    db.close()

    pos = parse_positions("symbol,quantity,avg_cost,price\nMSFT,3,300,420\n")
    txns = parse_transactions("date,type,symbol,quantity,price\n2026-01-02,buy,MSFT,3,300\n")
    with Repositories("u1") as repo:
        repo.save_refresh(pos, [], None)
        repo.save_refresh([], txns, None)
        latest = repo.latest_snapshots()
        all_txns = repo.all_transactions()
    assert len(latest) == 1 and latest[0]["symbol"] == "MSFT" and latest[0]["market_value"] == 1260.0
    assert len(all_txns) == 1 and all_txns[0]["trans_type"] == "BOUGHT"

    # re-importing the same transactions is idempotent (content-hash dedup)
    with Repositories("u1") as repo:
        repo.save_refresh([], parse_transactions("date,type,symbol,quantity,price\n2026-01-02,buy,MSFT,3,300\n"), None)
        assert len(repo.all_transactions()) == 1


if __name__ == "__main__":
    demo()
    print("OK")
