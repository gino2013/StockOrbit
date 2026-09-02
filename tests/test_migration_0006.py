"""Migration 0006 (fire_settings: new table only).
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

    # --- fresh DB at exactly 0006: table exists with the columns 0006
    # introduced (pinned to this revision, not "head" - 0007 adds more
    # columns on top and has its own test) ---
    db = tmp / "a.db"
    _alembic(db, "upgrade", "0006_fire_settings")
    rows = _sql(db, "PRAGMA table_info(fire_settings)")
    cols = {r[1] for r in rows}
    assert cols == {"user_id", "annual_expenses", "swr", "updated_at"}, cols
    pk = {r[1] for r in rows if r[5] > 0}
    assert pk == {"user_id"}, pk
    _alembic(db, "upgrade", "head")

    # --- downgrade to 0005 drops the table, upgrade back to head restores it ---
    _alembic(db, "downgrade", "0005_note_history")
    tables = {r[0] for r in _sql(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fire_settings" not in tables
    _alembic(db, "upgrade", "head")
    tables = {r[0] for r in _sql(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fire_settings" in tables

    # --- pre-existing DB at 0005 (simulating prod, already migrated up to
    # the previous head) picks up 0006 on next boot without re-running
    # earlier migrations ---
    db2 = tmp / "b.db"
    _run(db2, "from app.main import app; print('BOOT_OK')")
    _alembic(db2, "downgrade", "0005_note_history")
    _run(db2, "from app.main import app; print('BOOT_OK')")  # re-boot -> upgrades to head again
    tables2 = {r[0] for r in _sql(db2, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fire_settings" in tables2

    # --- untracked DB (no alembic_version row) whose structure already
    # matches head, including fire_settings - _infer_untracked_revision()
    # must recognize this as "0006", not re-run 0006's CREATE TABLE and
    # collide with the table that's already there ---
    db3 = tmp / "c.db"
    _run(db3, "from app.infrastructure.db import Base, engine; Base.metadata.create_all(engine); print('SETUP_OK')")
    out = _run(db3, "from app.main import app; print('BOOT_OK')")
    assert "BOOT_OK" in out
    tables3 = {r[0] for r in _sql(db3, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fire_settings" in tables3


if __name__ == "__main__":
    demo()
    print("OK")
