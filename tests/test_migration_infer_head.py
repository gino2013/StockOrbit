"""A DB with no alembic_version whose structure is already at head (what
scripts/seed_demo_data.py's create_all produces, or a fresh local DB) must
be stamped at head, not at an older revision - otherwise the next boot
re-runs ADD COLUMN migrations and dies with "duplicate column" (issue #396).
Also checks each mid-ladder rung by dropping the newest columns first.
Each case is its own subprocess (alembic's env.py caches `engine`).
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "APP_SECRET_KEY": "k" * 40, "FT_USERNAME": "", "FT_PASSWORD": "", "FT_MFA_SECRET": ""}
ENV.pop("OWNER_EMAIL", None)


def _py(db: Path, code: str) -> None:
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       env={**ENV, "DATABASE_URL": f"sqlite:///{db}"})
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def _fresh_create_all(db: Path) -> None:
    _py(db, "from app.infrastructure.db import Base, engine; Base.metadata.create_all(engine)")


def _cols(db: Path, table: str) -> set[str]:
    return {r[1] for r in sqlite3.connect(db).execute(f"PRAGMA table_info({table})")}


def demo():
    tmp = Path(tempfile.mkdtemp())
    boot = "from app.main import app"
    drops = [  # (case, columns to drop first)
        ("head", []),
        ("no_dip_alert_cols", [("dip_plans", "alert_level"), ("dip_plans", "alert_enabled")]),
        ("no_dip_plans", [("DROP", "dip_plans")]),
        ("no_term", [("liabilities", "term_months")]),
        ("no_currency", [("liabilities", "term_months"), ("liabilities", "currency")]),
        ("no_goal_contrib", [("liabilities", "term_months"), ("liabilities", "currency"),
                             ("investment_goals", "monthly_contribution"), ("investment_goals", "year_end_contribution")]),
    ]
    for name, to_drop in drops:
        db = tmp / f"{name}.db"
        _fresh_create_all(db)
        con = sqlite3.connect(db)
        for table, col in to_drop:
            con.execute(f"DROP TABLE {col}" if table == "DROP" else f"ALTER TABLE {table} DROP COLUMN {col}")
        con.commit()
        con.close()
        _py(db, boot)  # must not raise "duplicate column"
        assert {"currency", "term_months"} <= _cols(db, "liabilities"), name
        assert {"monthly_contribution", "year_end_contribution"} <= _cols(db, "investment_goals"), name
        head = sqlite3.connect(db).execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == "0025_dip_alerts", (name, head)
        assert {"alert_enabled", "alert_level"} <= _cols(db, "dip_plans"), name
        assert "dip_plans" in {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}, name


if __name__ == "__main__":
    demo()
    print("OK")
