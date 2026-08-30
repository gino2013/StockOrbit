"""Migration 0004 (tighten tenancy: user_id NOT NULL + composite PKs).
Each case its own subprocess - see tests/test_run_pending_migrations.py for
why (alembic's env.py caches `engine` at module scope).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
ENV_BASE = {**os.environ, "APP_SECRET_KEY": "k" * 40, "FT_USERNAME": "", "FT_PASSWORD": "", "FT_MFA_SECRET": ""}
ENV_BASE.pop("OWNER_EMAIL", None)


def _run(db_path: Path, script: str) -> str:
    r = subprocess.run([PY, "-c", script], cwd=ROOT, capture_output=True, text=True,
                       env={**ENV_BASE, "DATABASE_URL": f"sqlite:///{db_path}"})
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    return r.stdout


def _alembic(db_path: Path, *args: str) -> None:
    r = subprocess.run([PY, "-m", "alembic", *args], cwd=ROOT, capture_output=True, text=True,
                       env={**ENV_BASE, "DATABASE_URL": f"sqlite:///{db_path}"})
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def _sql(db_path: Path, query: str):
    import sqlite3

    return sqlite3.connect(db_path).execute(query).fetchall()


def demo():
    tmp = Path(tempfile.mkdtemp())

    # --- fresh DB: PKs land correctly ---
    db_a = tmp / "a.db"
    _run(db_a, "from app.main import app; print('BOOT_OK')")
    for table, expect_pk, has_id in [
        ("position_snapshots", {"id"}, True),
        ("transactions", {"id", "user_id"}, True),
        ("target_allocations", {"symbol", "user_id"}, False),
        ("position_notes", {"symbol", "user_id"}, False),
        ("transaction_notes", {"transaction_id", "user_id"}, False),
        ("investment_goals", {"user_id"}, False),
    ]:
        rows = _sql(db_a, f"PRAGMA table_info({table})")
        pk = {r[1] for r in rows if r[5] > 0}
        cols = {r[1] for r in rows}
        assert pk == expect_pk, (table, pk, expect_pk)
        assert ("id" in cols) == has_id, (table, cols)

    # --- downgrade to 0003 then back to head: round-trips cleanly ---
    _alembic(db_a, "downgrade", "0003_tenancy_cols")
    assert {r[1] for r in _sql(db_a, "PRAGMA table_info(investment_goals)") if r[5] > 0} == {"id"}
    _alembic(db_a, "upgrade", "head")
    assert {r[1] for r in _sql(db_a, "PRAGMA table_info(investment_goals)") if r[5] > 0} == {"user_id"}

    # --- realistic case: step-3-shaped DB (0003 applied, nullable user_id,
    # id-based PKs) with real cross-table data -> auto-migrates on boot,
    # every row survives with the correct owner ---
    db_b = tmp / "b.db"
    _alembic(db_b, "upgrade", "0003_tenancy_cols")
    setup = """
import sqlite3
from app.infrastructure.db import DATABASE_URL
path = DATABASE_URL.split("sqlite:///")[1]
c = sqlite3.connect(path)
oid = c.execute("select id from users where is_owner=1").fetchone()[0]
c.execute("insert into position_snapshots (id,user_id,account_number,symbol,quantity,cost_basis,market_value,price,snapshot_at) values ('x1',?,'A1','AAPL',10,1000,1200,120,'2026-01-01')", (oid,))
c.execute("insert into target_allocations (user_id,symbol,target_weight) values (?,'AAPL',1.0)", (oid,))
c.execute("insert into investment_goals (id,user_id,target_amount,target_date,updated_at) values ('default',?,50000,'2030-01-01','2026-01-01')", (oid,))
c.execute("insert into transactions (id,user_id,account_number,symbol,trans_type,report_date,quantity,trade_price,amount,description) values ('tx1',?,'A1','AAPL','BOUGHT','2026-01-01',10,100,-1000,'buy')", (oid,))
c.commit()
print("SETUP_OK", oid)
"""
    out = _run(db_b, setup)
    assert "SETUP_OK" in out
    owner_id = out.split()[-1]

    out = _run(db_b, "from app.main import app; print('BOOT_OK')")
    assert "BOOT_OK" in out
    assert _sql(db_b, "SELECT symbol, user_id FROM position_snapshots") == [("AAPL", owner_id)]
    assert _sql(db_b, "SELECT symbol, user_id FROM target_allocations") == [("AAPL", owner_id)]
    assert _sql(db_b, "SELECT target_amount, user_id FROM investment_goals") == [(50000.0, owner_id)]
    assert _sql(db_b, "SELECT id, user_id FROM transactions") == [("tx1", owner_id)]

    # --- idempotent across repeated boots ---
    for _ in range(2):
        out = _run(db_b, "from app.main import app; print('BOOT_OK')")
        assert "BOOT_OK" in out


if __name__ == "__main__":
    demo()
    print("OK")
