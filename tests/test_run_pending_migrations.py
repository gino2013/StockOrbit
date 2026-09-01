"""Covers app.infrastructure.db.run_pending_migrations() against every DB
state that plausibly exists in the wild - see docs/multi-user-architecture.md.

Each case runs as its own subprocess (matching how the real app boots -
once per process, on Render's free plan often on every cold start) rather
than importing app.infrastructure.db repeatedly in one process: alembic's
env.py caches the imported `engine` at module scope, so swapping
DATABASE_URL and re-importing within a single process silently keeps
touching the *first* case's DB file instead of the current one.
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
    r = subprocess.run(
        [PY, "-c", script],
        cwd=ROOT, capture_output=True, text=True,
        env={**ENV_BASE, "DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    return r.stdout


def _alembic(db_path: Path, *args: str) -> None:
    r = subprocess.run(
        [PY, "-m", "alembic", *args],
        cwd=ROOT, capture_output=True, text=True,
        env={**ENV_BASE, "DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def _sql(db_path: Path, query: str):
    import sqlite3

    return sqlite3.connect(db_path).execute(query).fetchall()


def demo():
    tmp = Path(tempfile.mkdtemp())
    boot = "from app.main import app; print('BOOT_OK', len(app.routes))"

    # --- case A: brand-new empty DB -> runs every migration from scratch ---
    db_a = tmp / "a.db"
    out = _run(db_a, boot)
    assert "BOOT_OK" in out
    cols = {r[1] for r in _sql(db_a, "PRAGMA table_info(position_snapshots)")}
    assert "user_id" in cols
    assert _sql(db_a, "SELECT COUNT(*) FROM users WHERE is_owner=1") == [(1,)]

    # --- case B: 0001-only (position_snapshots exists, no users table) ---
    db_b = tmp / "b.db"
    _alembic(db_b, "upgrade", "0001_baseline")
    out = _run(db_b, boot)
    assert "BOOT_OK" in out
    cols = {r[1] for r in _sql(db_b, "PRAGMA table_info(position_snapshots)")}
    assert "user_id" in cols

    # --- case C: mid-ladder - users/firstrade_credentials already exist
    # (an earlier deploy's create_all made them), all 6 tenancy tables still
    # lack user_id, AND there's real pre-existing data that must survive
    # and get backfilled to the owner, not dropped ---
    db_c = tmp / "c.db"
    setup_c = f"""
from app.infrastructure.db import Base, engine
from sqlalchemy import text
Base.metadata.create_all(engine)
with engine.begin() as conn:
    # position_note_history is introduced together with migration 0005,
    # so no real pre-Alembic deploy could ever have created it - drop the
    # copy create_all() just made so this simulated legacy DB accurately
    # reflects pre-0005 structure, and 0005's own CREATE TABLE runs for
    # real below instead of colliding with an already-present table.
    conn.execute(text("DROP TABLE position_note_history"))
    # position_snapshots/transactions/target_allocations/position_notes/
    # transaction_notes only differ (current models vs this historical
    # shape) in their PK *constraint*, not their columns, so stripping
    # user_id via copy-drop-rename works for them directly.
    for table, cols in [
        ("position_snapshots", "id,account_number,symbol,quantity,cost_basis,market_value,price,raw_json,snapshot_at"),
        ("transactions", "id,account_number,symbol,trans_type,report_date,quantity,trade_price,amount,description,raw_json,fetched_at"),
        ("target_allocations", "symbol,target_weight"),
        ("position_notes", "symbol,note,updated_at"),
        ("transaction_notes", "transaction_id,note,updated_at"),
    ]:
        conn.execute(text(f"CREATE TABLE {{table}}_old AS SELECT {{cols}} FROM {{table}}"))
        conn.execute(text(f"DROP TABLE {{table}}"))
        conn.execute(text(f"ALTER TABLE {{table}}_old RENAME TO {{table}}"))
    # investment_goals lost its `id` column entirely in 0004, so the
    # current model has no `id` to copy from - rebuild the true pre-0003
    # shape (migration 0001's original DDL) from scratch instead.
    conn.execute(text("DROP TABLE investment_goals"))
    conn.execute(text(
        "CREATE TABLE investment_goals (id VARCHAR PRIMARY KEY, target_amount FLOAT NOT NULL, "
        "target_date DATE NOT NULL, updated_at DATETIME)"
    ))
    conn.execute(text(
        "INSERT INTO position_snapshots (id,account_number,symbol,quantity,cost_basis,market_value,price,snapshot_at) "
        "VALUES ('x1','A1','AAPL',10,1000,1200,120,'2026-01-01')"
    ))
    conn.execute(text("INSERT INTO target_allocations (symbol,target_weight) VALUES ('AAPL',1.0)"))
print("SETUP_OK")
"""
    out = _run(db_c, setup_c)
    assert "SETUP_OK" in out
    out = _run(db_c, boot)
    assert "BOOT_OK" in out
    owner_id = _sql(db_c, "SELECT id FROM users WHERE is_owner=1")[0][0]
    assert _sql(db_c, "SELECT symbol, user_id FROM position_snapshots") == [("AAPL", owner_id)]
    assert _sql(db_c, "SELECT symbol, user_id FROM target_allocations") == [("AAPL", owner_id)]

    # --- case D: fully-migrated structure but no alembic_version row ->
    # stamps head; upgrade is then a no-op (no duplicate-column crash) ---
    db_d = tmp / "d.db"
    out = _run(db_d, "from app.infrastructure.db import Base, engine; Base.metadata.create_all(engine); print('SETUP_OK')")
    assert "SETUP_OK" in out
    out = _run(db_d, boot)
    assert "BOOT_OK" in out

    # --- case E: idempotent across repeated boots (Render restarts a lot) ---
    out = _run(db_d, boot)
    assert "BOOT_OK" in out
    out = _run(db_d, boot)
    assert "BOOT_OK" in out


if __name__ == "__main__":
    demo()
    print("OK")
