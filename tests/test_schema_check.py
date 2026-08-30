import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "schema_check.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"

from sqlalchemy import text  # noqa: E402

from app.infrastructure.db import Base, check_schema_matches_models, engine  # noqa: E402


def demo():
    # a table missing entirely -> create_all's job, not this check's: passes
    Base.metadata.create_all(engine)
    check_schema_matches_models()  # no exception

    # simulate an unmigrated prod DB: drop a column create_all would never
    # add back to an existing table (SQLite: drop_column via legacy rename)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE target_allocations RENAME TO target_allocations_old"))
        conn.execute(text(
            "CREATE TABLE target_allocations (symbol VARCHAR PRIMARY KEY, target_weight FLOAT NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO target_allocations SELECT symbol, target_weight FROM target_allocations_old"
        ))
        conn.execute(text("DROP TABLE target_allocations_old"))

    try:
        check_schema_matches_models()
        assert False, "expected RuntimeError for the missing user_id column"
    except RuntimeError as e:
        assert "target_allocations" in str(e)
        assert "user_id" in str(e)
        assert "alembic upgrade head" in str(e)


if __name__ == "__main__":
    demo()
    print("OK")
