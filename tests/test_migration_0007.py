"""Migration 0007 (fire_settings: add nullable retirement_date/
expected_real_return columns for Coast FIRE - no new table, existing rows
unaffected).
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

    # --- fresh DB boots to head: new columns exist, nullable ---
    db = tmp / "a.db"
    _run(db, "from app.main import app; print('BOOT_OK')")
    rows = _sql(db, "PRAGMA table_info(fire_settings)")
    cols = {r[1] for r in rows}
    assert cols == {"user_id", "annual_expenses", "swr", "retirement_date", "expected_real_return", "updated_at"}, cols
    notnull = {r[1]: r[3] for r in rows}
    assert notnull["retirement_date"] == 0
    assert notnull["expected_real_return"] == 0

    # --- a pre-existing fire_settings row (FIRE progress set up before this
    # migration, Coast FIRE never touched) survives untouched - new columns
    # come back NULL, not some fabricated default ---
    owner_id = _sql(db, "SELECT id FROM users WHERE is_owner=1")[0][0]
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO fire_settings (user_id, annual_expenses, swr) VALUES (?, ?, ?)",
        (owner_id, 800000.0, 0.04),
    )
    conn.commit()
    conn.close()
    row = _sql(db, f"SELECT annual_expenses, retirement_date, expected_real_return FROM fire_settings WHERE user_id='{owner_id}'")
    assert row == [(800000.0, None, None)], row

    # --- downgrade to 0006 drops the columns, upgrade back to head restores them ---
    _alembic(db, "downgrade", "0006_fire_settings")
    cols = {r[1] for r in _sql(db, "PRAGMA table_info(fire_settings)")}
    assert "retirement_date" not in cols
    _alembic(db, "upgrade", "head")
    cols = {r[1] for r in _sql(db, "PRAGMA table_info(fire_settings)")}
    assert "retirement_date" in cols

    # --- pre-existing DB at 0006 picks up 0007 on next boot ---
    db2 = tmp / "b.db"
    _run(db2, "from app.main import app; print('BOOT_OK')")
    _alembic(db2, "downgrade", "0006_fire_settings")
    _run(db2, "from app.main import app; print('BOOT_OK')")
    cols2 = {r[1] for r in _sql(db2, "PRAGMA table_info(fire_settings)")}
    assert "retirement_date" in cols2

    # --- untracked DB whose structure already matches head, including the
    # new columns - _infer_untracked_revision() must recognize this as
    # "0007", not re-run 0007's ADD COLUMN and collide with the column
    # that's already there ---
    db3 = tmp / "c.db"
    _run(db3, "from app.infrastructure.db import Base, engine; Base.metadata.create_all(engine); print('SETUP_OK')")
    out = _run(db3, "from app.main import app; print('BOOT_OK')")
    assert "BOOT_OK" in out
    cols3 = {r[1] for r in _sql(db3, "PRAGMA table_info(fire_settings)")}
    assert "retirement_date" in cols3


if __name__ == "__main__":
    demo()
    print("OK")
